import copy
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, FSMBehaviour, State,PeriodicBehaviour
from spade.message import Message
import asyncio
from datetime import datetime
#from clock_utils import ClockSyncMixin
import random
import json

from veiculos.algoritmo_tarefas import A_star_task_algorithm
#from MiddleManAgent import MiddleManAgent
from ..world.graph import Graph


class Order:
    def __init__(self, product:str, quantity:int, orderid:int, sender:str, receiver:str, tick_received:int):
        self.product = product
        self.quantity = quantity
        self.sender = sender
        self.receiver = receiver
        self.tick_received = tick_received

        self.deliver_time = None
        self.route = None
        self.sender_location = None
        self.receiver_location = None
        self.orderid = orderid
        self.fuel = None
        

    def __str__(self):
        return f"Order({self.orderid}, {self.product}, {self.quantity}, {self.sender}, {self.receiver}, {self.tick_received})"
    def time_to_deliver(self,sender_location:int,receiver_location:int ,map: Graph,weight: float):
        #calcula o tempo de entrega baseado no mapa
        path, fuel, time = map.djikstra(int(sender_location), int(receiver_location))
        self.route = path
        self.deliver_time = time
        self.fuel = fuel
        self.sender_location = sender_location
        self.receiver_location = receiver_location

class Veiculo(Agent):


    def __init__(self, jid:str, password:str, clock_jid:str, max_fuel:int, capacity:int, max_orders:int, map: Graph, weight: float,current_location:int):
        super().__init__(jid, password)
        self.clock_jid = clock_jid

        self.max_fuel = max_fuel
        self.capacity = capacity
        self.current_fuel = max_fuel
        self.current_load = 0
        self.max_orders = max_orders
        self.weight = weight
        #uma queue de ordens
        self.orders = []
        self.map = map
        self.current_location = current_location 
        self.next_node= None
        self.fuel_to_next_node= 0
        self.actual_route = []
        self.pending_orders = []
        self.time_to_finish_task = 0


    async def setup(self):
        self.presence.approve_all=True
        self.presence.subscribe(self.clock_jid)
        # Criar FSM para Communication Phase
        fsm = FSMBehaviour()
        fsm.add_state(name="RECEIVE_ORDERS", state=self.ReceiveOrdersState(), initial=True)
        fsm.add_state(name="CONFIRM_ORDER", state=self.CommunicationState())
        self.add_behaviour(fsm)
        self.add_behaviour()


    class ReceiveOrdersState(State):
        """
        Estado para receber ordens do MiddleMan.
        """

        async def run(self):
            msg = await self.receive(timeout=10)
            if msg:
                order_data = json.loads(msg.body)
                order = Order(
                    product=order_data["product"],
                    quantity=order_data["quantity"],
                    orderid=order_data["orderid"],
                    sender=order_data["sender"],
                    receiver=order_data["receiver"],
                    tick_received=order_data["tick_received"]
                )
                print(f"[{self.agent.name}] Ordem recebida: {order}")
                self.set_next_state("CONFIRM_ORDER")
            else:
                print(f"[{self.agent.name}] Nenhuma ordem recebida no tempo limite.")
    class MovementBehaviour(CyclicBehaviour):
        """
        Comportamento que move o veículo ao longo de sua rota a cada tick.
        """

        async def run(self):
            msg = await self.receive(timeout=0.3)
            if msg:
                type = msg.body.get("type")
                tempo = msg.body.get("time")
                veiculo = None
                if type == "arrival":
                    veiculo = msg.body.get("vehicle")
                if veiculo == self.agent.name:
                    self.agent.current_location = self.agent.actual_route.pop(0)
                    self.agent.actual_route,  , _ = A_star_task_algorithm(self.agent.map, self.agent.current_location, self.agent.pending_orders, self.agent.capacity, self.agent.max_fuel)
                if type == "Transito":
                    update = await self.update_map(self,msg.body.get("data"))
                    if update:
                        _,_,tempo= self.graph.dijkstra(self.agent.current_location,self.agent.next_node)

        async def update_location_and_time(self,time_left):
                    """
                    Atualiza a localização atual do veículo e o tempo restante para o próximo nó.
                    O veículo move-se o quanto conseguir durante o tick_time.
                    
                    Estados do veículo:
                    - Direcionando-se para uma tarefa (início da rota)
                    - Finalizando a tarefa (fim da rota)
                    """
                    
                    while time_left > 0:
                        # Se não há rota atual e há ordens pendentes, criar rota para a primeira ordem
                        if not self.agent.actual_route and len(self.agent.orders) > 0:

                            start_location = self.agent.orders[0].sender_location
                            if self.agent.current_location != start_location:
                                # Usar Dijkstra para encontrar caminho até o início
                                route,_,_ = self.agent.map.dijkstra(
                                    self.agent.current_location, 
                                    start_location
                                )
                                # Remover o primeiro nó (nó atual) pois já estamos nele
                                self.agent.actual_route = route[1:] if len(route) > 1 else []
                            else:

                                order_route = copy.deepcopy(self.agent.orders[0].route)
                                self.agent.actual_route = order_route
                        
                        # Se não há rota e não há ordens, o veículo está parado
                        if not self.agent.actual_route:
                            break
                        
                        # Se há tempo restante de uma aresta anterior, continuar
                        if self.agent.time_left_to_next_node > 0:
                            if time_left >= self.agent.time_left_to_next_node:
                                # Consegue completar o movimento para o próximo nó
                                time_left -= self.agent.time_left_to_next_node
                                self.agent.current_location = self.agent.next_node
                                self.agent.time_left_to_next_node = 0
                                self.agent.current_fuel -= self.agent.fuel_to_next_node
                                self.agent.next_node = None
                                
                                # Verificar se chegou a um ponto importante (início ou fim)
                                await self.check_arrival()
                            else:
                                # Não consegue completar, apenas reduzir o tempo
                                self.agent.time_left_to_next_node -= time_left
                                time_left = 0
                                break
                        
                        # Processar próximo nó na rota
                        if self.agent.actual_route and time_left > 0:
                            next_node = self.agent.actual_route.pop(0)
                            
                            # TODO Obter custo da aresta (tempo e combustível)
                            if (self.agent.current_location != next_node):  
                                time,fuel = self.agent.map.get_edge(
                                    self.agent.current_location, 
                                    next_node
                                )
                                
                                # Verificar se tem combustível suficiente
                                if self.agent.current_fuel < fuel:
                                    print(f"[{self.agent.name}] Combustível insuficiente! A parar.")
                                    break
                                
                                self.agent.next_node = next_node
                                self.agent.time_left_to_next_node = time
                                self.agent.fuel_to_next_node = fuel
                            else: continue
                            
                
        async def check_arrival(self):
            """
            Verifica se o veículo chegou ao início ou fim de uma ordem.
            Atualiza carga e combustível conforme necessário.
            """
            if not self.agent.orders:
                return
            
            current_order = self.agent.orders[0]
            
            # Verificar se chegou ao início da rota (pickup)
            if self.agent.current_location == current_order.route[0]:
                print(f"[{self.agent.name}] Chegou ao ponto de coleta: {current_order}")
                self.agent.current_load += current_order.quantity
                self.agent.current_fuel = self.agent.max_fuel
                order_route = copy.deepcopy(current_order.route)
                self.agent.actual_route = order_route[1:] if len(order_route) > 1 else []
                
            # Verificar se chegou ao fim da rota (delivery)
            elif self.agent.current_location == current_order.route[-1]:
                print(f"[{self.agent.name}] Chegou ao ponto de entrega: {current_order}")

                self.agent.current_load -= current_order.quantity
                self.agent.current_fuel = self.agent.max_fuel
                self.agent.orders.pop(0)
                self.agent.actual_route = []                