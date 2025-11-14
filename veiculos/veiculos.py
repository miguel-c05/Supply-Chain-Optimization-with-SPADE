import copy
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, FSMBehaviour, State,PeriodicBehaviour
from spade.message import Message
from spade.presence import PresenceType, PresenceShow
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
        Estado para receber e agendar ordens do MiddleMan.
        Verifica se consegue encaixar a ordem na rota atual ou se precisa esperar.
        """

        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                order_data = json.loads(msg.body)
                order = Order(
                    product=order_data["product"],
                    quantity=order_data["quantity"],
                    orderid=order_data["orderid"],
                    sender=order_data["sender"],
                    receiver=order_data["receiver"],
                    sender_location=order_data["sender_location"],
                    receiver_location=order_data["receiver_location"],
                )
                
                print(f"[{self.agent.name}] Ordem recebida: {order}")
                
                # Calcular informações da ordem (rota, tempo, combustível)
                await order.deliver_time(sender_location=order.sender_location,receiver_location=order.receiver_location ,map=self.agent.map,weight=self.agent.weight)
                
                # Verificar se consegue encaixar na rota atual
                can_fit, delivery_time = await self.can_fit_in_current_route(order)
                
                response_msg = Message(to=msg.sender)
                response_msg.set_metadata("performative", "inform")
                response_msg.set_metadata("orderid", str(order.orderid))
                
                if can_fit:
                    # Consegue encaixar na rota atual
                    self.agent.orders.append(order)
                    
                    # Recalcular a rota com a nova ordem
                    await self.recalculate_route()
                    
                    response_data = {
                        "status": "accepted_current",
                        "orderid": order.orderid,
                        "delivery_time": delivery_time,
                        "message": f"Ordem aceite na rota atual. Tempo de entrega: {delivery_time}"
                    }
                    print(f"[{self.agent.name}] Ordem {order.orderid} encaixada na rota atual")
                else:
                    # Não consegue encaixar - calcular tempo após rota atual
                    future_time = await self.calculate_future_delivery_time(order)
                    
                    response_data = {
                        "status": "pending_confirmation",
                        "orderid": order.orderid,
                        "delivery_time": future_time,
                        "message": f"Não consegue encaixar agora. Tempo após rota atual: {future_time}"
                    }
                    print(f"[{self.agent.name}] Ordem {order.orderid} aguarda confirmação. Tempo estimado: {future_time}")
                    
                    # Aguardar confirmação do warehouse
                    confirmation = await self.wait_for_confirmation(msg.sender, order.orderid)
                    
                    if confirmation:
                        self.agent.pending_orders.append(order)
                        response_data["status"] = "accepted_pending"
                        response_data["message"] = "Ordem aceite para execução após rota atual"
                        print(f"[{self.agent.name}] Ordem {order.orderid} confirmada para pending_orders")
                    else:
                        response_data["status"] = "rejected"
                        response_data["message"] = "Ordem rejeitada pelo warehouse"
                        print(f"[{self.agent.name}] Ordem {order.orderid} rejeitada")
                
                response_msg.body = json.dumps(response_data)
                await self.send(response_msg)
                
            else:
                print(f"[{self.agent.name}] Nenhuma ordem recebida no tempo limite.")
        
        async def calculate_order_info(self, order: Order):
            """Calcula a rota, tempo e combustível necessários para a ordem"""
            path, fuel, time = await self.agent.map.djikstra(
                int(order.sender), 
                int(order.receiver)
            )
            order.route = path
            order.deliver_time = time
            order.fuel = fuel
            order.sender_location = int(order.sender)
            order.receiver_location = int(order.receiver)
        
        async def can_fit_in_current_route(self, new_order: Order) -> tuple[bool, float]:
            """
            Verifica se a ordem pode ser encaixada na rota atual sem overload.
            A rota é uma lista de tuplos (node_id, order_id).
            
            Retorna (pode_encaixar, tempo_de_entrega)
            """
            # Se não há ordens, pode sempre encaixar
            if self.agent.presence.get_presence() == PresenceType.AVAILABLE:
                return True, new_order.deliver_time
            
            # Criar um dicionário com as ordens atuais para acesso rápido
            orders_dict = {order.orderid: order for order in self.agent.orders}
            
            # Verificar se a nova ordem passa por algum ponto da rota atual
            route_nodes = [node_id for node_id, _ in self.agent.actual_route]
            passes_through_sender = new_order.sender_location in route_nodes
            
            # Se não passa pelo sender, calcular tempo com pending orders
            if not passes_through_sender:
                future_time = await self.calculate_future_delivery_time(new_order)
                return False, future_time
            
            # Simular a adição da ordem na rota
            # Percorrer o path atual e simular a carga
            current_load = self.agent.current_load
            new_order_picked = False
            new_order_delivered = False
            delivery_time = 0
            cumulative_time = 0
            
            for i, (node_id, order_id) in enumerate(self.agent.actual_route):
                # Calcular tempo até este ponto
                if i > 0:
                    prev_node_id = self.agent.actual_route[i - 1][0]
                    _, _, segment_time = self.agent.map.djikstra(prev_node_id, node_id)
                    cumulative_time += segment_time
                
                # Verificar se é pickup ou delivery da nova ordem
                if node_id == new_order.sender_location and not new_order_picked:
                    # Tentar fazer pickup da nova ordem
                    test_load = current_load + new_order.quantity
                    
                    if test_load > self.agent.capacity:
                        # Overflow - calcular tempo com pending orders
                        future_time = await self.calculate_future_delivery_time(new_order)
                        return False, future_time
                    
                    current_load = test_load
                    new_order_picked = True
                
                elif node_id == new_order.receiver_location and new_order_picked and not new_order_delivered:
                    # Fazer delivery da nova ordem
                    current_load -= new_order.quantity
                    new_order_delivered = True
                    delivery_time = cumulative_time
                    # Entregou o item - pode parar de simular
                    return True, delivery_time
                
                # Processar a ordem existente neste ponto
                if order_id and order_id in orders_dict:
                    existing_order = orders_dict[order_id]
                    
                    # Verificar se é pickup ou delivery
                    if node_id == existing_order.sender_location:
                        # Pickup
                        test_load = current_load + existing_order.quantity
                        if test_load > self.agent.capacity:
                            # Overflow ao processar ordem existente
                            future_time = await self.calculate_future_delivery_time(new_order)
                            return False, future_time
                        current_load = test_load
                    elif node_id == existing_order.receiver_location:
                        # Delivery
                        current_load -= existing_order.quantity
            
            # Se chegou aqui e não entregou, significa que não passou pelo receiver
            # Calcular tempo com pending orders
            if not new_order_delivered:
                future_time = await self.calculate_future_delivery_time(new_order)
                return False, future_time
            
            # Se entregou, retornar sucesso (não deveria chegar aqui pois retorna no loop)
            return True, delivery_time
        
        async def calculate_future_delivery_time(self, order: Order) -> float:
            """
            Calcula o tempo necessário para executar a ordem após terminar a rota atual.
            Usa A* para calcular a rota ótima com pending_orders + nova ordem.
            """
            # Determinar onde o veículo estará quando terminar a rota atual
            if self.agent.actual_route:
                final_location = self.agent.actual_route[-1][0]  # Último node_id da rota
            else:
                final_location = self.agent.current_location
            
            # Criar lista com pending_orders + nova ordem
            future_orders = self.agent.pending_orders.copy()
            future_orders.append(order)
            
            # Calcular rota ótima com A* desde o último ponto
            
            route, total_time, _ = A_star_task_algorithm(
                self.agent.map,
                final_location,
                future_orders,
                self.agent.capacity,
                self.agent.max_fuel
            )
            
            # Adicionar o tempo que falta para terminar a rota atual
            current_route_time = self.agent.time_to_finish_task
            
            return current_route_time + total_time
        
        async def wait_for_confirmation(self, sender_jid: str, orderid: int, timeout: float = 30.0) -> bool:
            """
            Aguarda confirmação do warehouse para uma ordem pendente.
            Retorna True se confirmado, False se rejeitado ou timeout.
            """
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                msg = await self.receive(timeout=5)
                
                if msg and msg.sender == sender_jid:
                    try:
                        data = json.loads(msg.body)
                        if data.get("orderid") == orderid:
                            return data.get("confirmed", False)
                    except:
                        continue
            
            return False
        
        async def recalculate_route(self):
            """Recalcula a rota com todas as ordens atuais"""
            if self.agent.orders:
                route, fuel, time = await A_star_task_algorithm(
                    self.agent.map,
                    self.agent.current_location,
                    self.agent.orders,
                    self.agent.capacity,
                    self.agent.max_fuel
                )
                self.agent.actual_route = route
                self.agent.time_to_finish_task = time
    class MovementBehaviour(CyclicBehaviour):
        """
        Comportamento que move o veículo ao longo de sua rota a cada tick.
        """

        async def run(self):
            msg = await self.receive(timeout=0.3)
            if msg:
                type = msg.body.get("type")
                time = msg.body.get("time")
                veiculo = None
                if type == "arrival":
                    veiculo = msg.body.get("vehicle")
                if veiculo == self.agent.name:
                    self.agent.current_location = self.agent.actual_route.pop(0)
                    #TODO Verificar se acabou a rota pela order id e warehouse id e se começou alterar a order para iniciou
                    if not self.agent.actual_route:
                        if self.agent.pending_orders==0:
                            self.agent.presence.set_presence(presence_type=PresenceType.AVAILABLE, show=PresenceShow.CHAT)
                            return
                        self.agent.actual_route, _, _ = await A_star_task_algorithm( self.agent.map, self.agent.current_location,self.agent.pending_orders,self.agent.capacity,self.agent.max_fuel)
                    
                    _, _, self.agent.time_to_finish_task = await self.agent.map.djikstra(self.agent.current_location,self.agent.next_node)
                else: 
                    self.agent.current_location = await self.update_location_and_time(time)
                    
                if type == "Transit":
                    await self.agent.update_map(self,msg.body.get("data"))
                _ , _ , time_left = await self.agent.map.djikstra(self.agent.current_location,self.agent.next_node)
                # TODO notificar event agent quanto tempo falta 
                

        async def update_location_and_time(self, time_left):
            """
            Atualiza a localização do veículo baseado no tempo disponível.
            Move-se ao longo da rota enquanto houver tempo.
            Se o tempo acabar a meio de dois vértices, volta para o vértice inicial.
            """
            next_node = self.agent.actual_route[0]
            route, _ , _ = await self.agent.map.djikstra(self.agent.current_location, next_node)
            remaining_time = time_left
            current_pos = self.agent.current_location
            route_index = 0
            
            # Percorre a rota enquanto houver tempo
            while route_index < len(route) and remaining_time > 0:
                next_node = route[route_index]
                
                # Obter a aresta entre o nó atual e o próximo
                edge = await self.agent.map.get_edge(current_pos, next_node)
                
                if edge is None:
                    # Se não há aresta, para
                    break
                
                # Tempo necessário para atravessar esta aresta
                edge_time = edge.weight  # assumindo que weight é o tempo
                
                if remaining_time >= edge_time:
                    # Tempo suficiente para chegar ao próximo nó
                    current_pos = next_node
                    remaining_time -= edge_time
                    route_index += 1
                else:
                    # Tempo insuficiente - fica no nó atual
                    break
            
            return current_pos

                                     