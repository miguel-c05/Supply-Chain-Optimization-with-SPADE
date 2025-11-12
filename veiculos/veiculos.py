import copy
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, FSMBehaviour, State
from spade.message import Message
import asyncio
from datetime import datetime
from clock_utils import ClockSyncMixin
import random
import json
from MiddleManAgent import MiddleManAgent
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
    async def time_to_deliver(self,sender_location:int,receiver_location:int ,map: Graph,weight: float):
        #calcula o tempo de entrega baseado no mapa
        route, time, fuel= map.get_route_time(sender_location,receiver_location,weight)
        self.route = route
        self.deliver_time = time
        self.fuel = fuel
        self.sender_location = sender_location
        self.receiver_location = receiver_location

class Veiculo(Agent):


    def __init__(self, jid:str, password:str, clock_jid:str, max_fuel:int, capacity:int, max_orders:int, map: Graph, weight: float,current_location:int,tick_time:int):
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
        self.time_left_to_next_node= 0 
        self.next_node= None
        self.tick_time = tick_time
        self.fuel_to_next_node= 0
        self.actual_route = []



    async def setup(self):
        print(f"[{self.name}] Agente de teste inicializado")
        self.middleman = MiddleManAgent(f"middleman_{self.jid}", "password", self.clock_jid, self.jid)
        await self.middleman.start()
        
        # Criar FSM para Communication Phase
        fsm = FSMBehaviour()
        fsm.add_state(name="COMMUNICATION_STATE", state=self.CommunicationState(), initial=True)
        fsm.add_state(name="ACTION_STATE", state=self.ActionState(), initial=False)

        fsm.add_transition(source="COMMUNICATION_STATE", dest="COMMUNICATION_STATE")
        fsm.add_transition(source="COMMUNICATION_STATE", dest="ACTION_STATE")
        fsm.add_transition(source="ACTION_STATE", dest="ACTION_STATE")
        fsm.add_transition(source="ACTION_STATE", dest="COMMUNICATION_STATE")

        self.add_behaviour(fsm)

    class CommunicationState(State):
        """
        Estado cíclico de comunicação.
        Permanece neste estado até receber confirmação do middleman para mudar de fase.
        """

        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                # Verificar se é mensagem do middleman mudando para fase de comunicação
                if msg.sender == str(self.agent.middleman.jid) and msg.metadata.get("phase") == "action":
                    self.set_next_state("ACTION_STATE")
                    return
                
                # Se estiver na fase de comunicação, processar mensagens
                
                tick = msg.metadata.get("tick")
                if msg.type == "order":
                    order = Order(msg.metadata.get("product"), msg.metadata.get("quantity"),
                                    msg.metadata.get("sender"), msg.metadata.get("receiver"))
                    await order.time_route_to_deliver(msg.metadata.get("sender_location"),
                                                        msg.metadata.get("receiver_location"),
                                                        self.agent.map)

                    if (order.fuel <= self.agent.max_fuel and 
                        order.quantity <= self.agent.capacity and 
                        len(self.agent.orders) < self.agent.max_orders):
                        
                        self.agent.orders.append(order)
                        await self.confirm_order(msg.sender)
                        print(f"[{self.agent.name}] Ordem aceita: {order}")
                    else:
                        await self.confirm_order(msg.sender, rejected=True)
                        print(f"[{self.agent.name}] Ordem rejeitada: {order}")

                # Notificar middleman que terminou processamento de comunicação
                mensagem = Message(to=str(self.agent.middleman.jid))
                mensagem.metadata = {
                    "phase": "communication",
                    "tick": tick
                }
                await self.send(mensagem)
            
            # Retorna ao mesmo estado (comportamento cíclico)
            self.set_next_state("COMMUNICATION_STATE")
                    
        async def confirm_order(self, to: str, rejected: bool = False):
            mensagem = Message(to=to)
            mensagem.metadata = {
                "phase": "communication",
                "tick": self.agent.tick if hasattr(self.agent, 'tick') else 0,
                "offer": not rejected
            }
            await self.send(mensagem)

    class ActionState(State):
        """
        Estado cíclico de ação.
        Permanece neste estado até receber confirmação do middleman para mudar de fase.
        """

        async def run(self):
            # Atualizar posição e tempo do veículo durante o tick
            await self.update_location_and_time()
            
            msg = await self.receive(timeout=0.1)

            if msg:
                # Verificar se é mensagem do middleman mudando para fase de ação
                if msg.sender == str(self.agent.middleman.jid) and msg.metadata.get("phase") == "communication":
                    self.set_next_state("COMMUNICATION_STATE")
                    return
            
            # Retorna ao mesmo estado (comportamento cíclico)
            self.set_next_state("ACTION_STATE")
        async def update_location_and_time(self):
            """
            Atualiza a localização atual do veículo e o tempo restante para o próximo nó.
            O veículo move-se o quanto conseguir durante o tick_time.
            
            Estados do veículo:
            - Direcionando-se para uma tarefa (início da rota)
            - Finalizando a tarefa (fim da rota)
            """
            time_left = self.agent.tick_time
            
            while time_left > 0:
                # Se não há rota atual e há ordens pendentes, criar rota para a primeira ordem
                if not self.agent.actual_route and len(self.agent.orders) > 0:

                    start_location = self.agent.orders[0].sender_location
                    if self.agent.current_location != start_location:
                        # Usar Dijkstra para encontrar caminho até o início
                        route = self.agent.map.dijkstra(
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


async def main():
    """
    Exemplo de execução do agente de teste com o relógio.
    """
    from Relogio import ClockAgent
    
    # Criar relógio
    clock = ClockAgent("clock@localhost", "password", tick_duration_seconds=2.0)
    await clock.start()
    print("Relógio iniciado\n")
    
    # Criar agente de teste
    test_agent = Veiculo("testagent@localhost", "password", "clock@localhost", max_fuel=100, capacity=50, max_orders=5, map=None, weight=10.0)
    test_agent2 = Veiculo("testagent2@localhost", "password", "clock@localhost", max_fuel=100, capacity=50, max_orders=5, map=None, weight=10.0)

    await test_agent2.start()
    await test_agent.start()

    print("Iniciando simulação...\n")
    clock.start_simulation()
    
    # Deixar rodar por 10 segundos
    await asyncio.sleep(10)
    
    # Parar simulação
    print("\n Parando simulação...")
    clock.stop_simulation()
    
    # Aguardar um pouco antes de desligar
    await asyncio.sleep(2)
    
    # Parar agentes
    await test_agent.stop()
    await test_agent.middleman.stop()
    await test_agent2.stop()
    await test_agent2.middleman.stop()
    await clock.stop()
    
    print("\n Teste concluído!")


if __name__ == "__main__":
    asyncio.run(main())
