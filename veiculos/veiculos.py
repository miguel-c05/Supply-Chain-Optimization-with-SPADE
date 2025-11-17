import copy
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.presence import PresenceType, PresenceShow
import asyncio
from datetime import datetime
import random
import json
import sys
import os

# Adicionar o diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from algoritmo_tarefas import A_star_task_algorithm
from world.graph import Graph


class Order:
    def __init__(self, product:str, quantity:int, orderid:int, sender:str, receiver:str):
        self.product = product
        self.quantity = quantity
        self.sender = sender
        self.receiver = receiver

        self.deliver_time = None
        self.route = None
        self.sender_location = None
        self.receiver_location = None
        self.orderid = orderid
        self.fuel = None
        self.comecou = False
        

    def time_to_deliver(self,sender_location:int,receiver_location:int ,map: Graph,weight: float):
        #calcula o tempo de entrega baseado no mapa
        path, fuel, time = map.djikstra(int(sender_location), int(receiver_location))
        self.route = path
        self.deliver_time = time
        self.fuel = fuel
        self.sender_location = sender_location
        self.receiver_location = receiver_location

class Veiculo(Agent):


    def __init__(self, jid:str, password:str, max_fuel:int, capacity:int, max_orders:int, map: Graph, weight: float,current_location:int):
        super().__init__(jid, password)

        self.max_fuel = max_fuel
        self.capacity = capacity
        self.current_fuel = max_fuel
        self.current_load = 0
        self.max_orders = max_orders
        self.weight = weight
        self.orders = []
        self.map = map
        self.current_location = current_location 
        self.next_node= None
        self.fuel_to_next_node= 0
        self.actual_route = [] # lista de tuplos (node_id, order_id)
        self.pending_orders = []
        self.time_to_finish_task = 0
        
        # Dicionário para armazenar múltiplas ordens aguardando confirmação
        # Key: orderid, Value: dict com order, can_fit, delivery_time, sender_jid
        self.pending_confirmations = {}


    async def setup(self):
        from spade.template import Template
        
        self.presence.approve_all=True
        self.presence.set_presence(PresenceType.AVAILABLE, PresenceShow.CHAT)
        # TODO: dar presence no event agent 
        # self.presence.subscribe(self.clock_jid)
        
        # Template para receber propostas de ordens dos warehouses
        order_template = Template()
        order_template.set_metadata("performative", "order-proposal")
        
        # Template para receber confirmações dos warehouses
        confirmation_template = Template()
        confirmation_template.set_metadata("performative", "order-confirmation")
        
        # Template para receber mensagens do event agent (tick, arrival, transit)
        # Não tem performative específico, então vamos filtrar por ausência dos performatives acima
        event_template = Template()
        event_template.set_metadata("performative", "inform")
        
        # Adicionar comportamentos cíclicos com templates
        self.add_behaviour(self.ReceiveOrdersBehaviour(), template=order_template)
        self.add_behaviour(self.WaitConfirmationBehaviour(), template=confirmation_template)
        self.add_behaviour(self.MovementBehaviour(), template=event_template)


    class ReceiveOrdersBehaviour(CyclicBehaviour):
        """
        Comportamento para receber e agendar ordens dos warehouses.
        Verifica se consegue encaixar a ordem na rota atual ou se precisa esperar.
        """

        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                order_data = json.loads(msg.body)
                
                # Validar campos obrigatórios
                required_fields = ["product", "quantity", "orderid", "sender", "receiver", 
                                    "sender_location", "receiver_location"]
                if not all(field in order_data for field in required_fields):
                    print(f"[{self.agent.name}] Mensagem inválida - campos faltando: {order_data}")
                    return
                
                order = Order(
                    product=order_data["product"],
                    quantity=order_data["quantity"],
                    orderid=order_data["orderid"],
                    sender=order_data["sender"],
                    receiver=order_data["receiver"]
                )
                order.sender_location = order_data["sender_location"]
                order.receiver_location = order_data["receiver_location"]
                
                print(f"[{self.agent.name}] Ordem recebida: {order}")
                
                # Calcular informações da ordem (rota, tempo, combustível)
                order.time_to_deliver(
                    sender_location=order.sender_location,
                    receiver_location=order.receiver_location,
                    map=self.agent.map,
                    weight=self.agent.weight
                )
                
                # Verificar se consegue encaixar na rota atual
                can_fit, delivery_time = await self.can_fit_in_current_route(order)
                
                # Enviar proposta ao warehouse
                proposal_msg = Message(to=msg.sender)
                proposal_msg.set_metadata("performative", "vehicle-proposal")
                
                proposal_data = {
                    "orderid": order.orderid,
                    "can_fit": can_fit,
                    "delivery_time": delivery_time,
                    "vehicle_id": str(self.agent.jid)
                }
                proposal_msg.body = json.dumps(proposal_data)
                await self.send(proposal_msg)
                
                print(f"[{self.agent.name}] Proposta enviada - Ordem {order.orderid}: can_fit={can_fit}, tempo={delivery_time}")
                    
                # Guardar informações no dicionário de confirmações pendentes
                self.agent.pending_confirmations[order.orderid] = {
                    "order": order,
                    "can_fit": can_fit,
                    "delivery_time": delivery_time,
                    "sender_jid": str(msg.sender)
                }
                
                print(f"[{self.agent.name}] Ordem {order.orderid} adicionada às confirmações pendentes. Total: {len(self.agent.pending_confirmations)}")
        
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
            # Verificar o estado de presença do agente
            # CHAT = disponível (sem tarefas), AWAY = ocupado (com tarefas)
            presence_show = self.agent.presence.get_show()
            
            print(f"Presence atual - Show: {presence_show}")
            
            # Se está em CHAT (disponível), não tem tarefas ativas
            if presence_show == PresenceShow.CHAT:
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
                    print(f"Debug1")
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
            print(f"Debug2")
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
        
        async def recalculate_route(self):
            """Recalcula a rota com todas as ordens atuais"""
            if self.agent.orders:
                route, time , _ = A_star_task_algorithm(
                    self.agent.map,
                    self.agent.current_location,
                    self.agent.orders,
                    self.agent.capacity,
                    self.agent.max_fuel
                )
                self.agent.actual_route = route
                self.agent.time_to_finish_task = time
    
    class WaitConfirmationBehaviour(CyclicBehaviour):
        """
        Comportamento que aguarda confirmação do warehouse para aceitar/rejeitar a ordem.
        """
        
        async def run(self):
            # Só processa se houver confirmações pendentes
            if not self.agent.pending_confirmations:
                await asyncio.sleep(0.1)
                return
            
            # Tentar receber confirmação do warehouse
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    orderid = data.get("orderid")
                    
                    # Verificar se esta ordem está nas confirmações pendentes
                    if orderid not in self.agent.pending_confirmations:
                        print(f"[{self.agent.name}] Confirmação recebida para ordem desconhecida: {orderid}")
                        return
                    
                    # Obter informações da ordem pendente
                    pending_info = self.agent.pending_confirmations[orderid]
                    order = pending_info["order"]
                    can_fit = pending_info["can_fit"]
                    sender_jid = pending_info["sender_jid"]
                    
                    # Verificar se o sender é o correto
                    if str(msg.sender) != sender_jid:
                        print(f"[{self.agent.name}] Confirmação de sender incorreto para ordem {orderid}")
                        return
                    
                    confirmation = data.get("confirmed", False)
                    print(f"[{self.agent.name}] Confirmação recebida para ordem {orderid}: {confirmation}")
                    
                    # Processar confirmação
                    if confirmation:
                        if can_fit:
                            # Adiciona às orders (rota atual)
                            self.agent.orders.append(order)
                            await self.recalculate_route()
                            print(f"[{self.agent.name}] Ordem {order.orderid} aceite e adicionada às orders")
                        else:
                            # Adiciona às pending_orders (executar depois)
                            self.agent.pending_orders.append(order)
                            print(f"[{self.agent.name}] Ordem {order.orderid} aceite e adicionada às pending_orders")
                        
                        # Atualizar presença para AWAY (ocupado com tarefas)
                        self.agent.presence.set_presence(
                            presence_type=PresenceType.AVAILABLE, 
                            show=PresenceShow.AWAY, 
                            status="Ocupado com tarefas"
                        )
                        print(f"[{self.agent.name}] Status alterado para AWAY - tem tarefas pendentes")
                        print(f"Rota recalculada: {self.agent.actual_route}")
                        print(f"Orders pendentes: {self.agent.pending_orders}")
                    else:
                        print(f"[{self.agent.name}] Ordem {order.orderid} rejeitada pelo warehouse")
                    
                    # Remover do dicionário de confirmações pendentes
                    del self.agent.pending_confirmations[orderid]
                    print(f"[{self.agent.name}] Ordem {orderid} removida das confirmações pendentes. Restantes: {len(self.agent.pending_confirmations)}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Erro ao processar confirmação: {e}")
        
        async def recalculate_route(self):
            """Recalcula a rota com todas as ordens atuais"""
            if self.agent.orders:
                route, time , _ = A_star_task_algorithm(
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
            # Verificar se o veículo está ocupado (AWAY = tem tarefas)

            
            msg = await self.receive(timeout=5)  # Timeout maior para não perder mensagens

            presence_show = self.agent.presence.get_show()
            
            if presence_show == PresenceShow.CHAT:
                # Veículo disponível (sem tarefas) - não processa mensagens de movimento
                return
            if msg:
                # print a mensagem recebida
                print(f"[{self.agent.name}] Mensagem recebida no MovementBehaviour")
                print(f"  Body: {msg.body}")
                print(f"  Metadata: {msg.metadata}")
                
                data = json.loads(msg.body)
                type = data.get("type")
                time = data.get("time")
                veiculo = data.get("vehicle", None)
                
                print(f"  Type: {type}, Vehicle: {veiculo}, Agent name: {self.agent.name}")
                
                if type == "arrival" and veiculo == self.agent.name:
                    # Chegou a um nó - processar chegada
                    self.agent.current_location, order_id = self.agent.actual_route.pop(0)
                    
                    # Processar a primeira tarefa no nó
                    await self.process_node_arrival(self.agent.current_location, order_id)
                    
                    # Processar todos os nós consecutivos iguais (múltiplas tarefas no mesmo local)
                    while self.agent.actual_route and self.agent.actual_route[0][0] == self.agent.current_location:
                        # Próximo item na rota é no mesmo nó - processar imediatamente
                        next_location, next_order_id = self.agent.actual_route.pop(0)
                        await self.process_node_arrival(next_location, next_order_id)
                    
                    # Verificar se acabou a rota atual
                    if not self.agent.actual_route:
                        if len(self.agent.pending_orders) == 0:
                            # Sem mais tarefas - ficar disponível
                            self.agent.presence.set_presence(
                                presence_type=PresenceType.AVAILABLE,
                                show=PresenceShow.CHAT,
                                status="Disponível para novas ordens"
                            )
                            print(f"[{self.agent.name}] Status alterado para AVAILABLE - sem tarefas")
                            return
                        
                        # Há pending orders - calcular nova rota
                        self.agent.actual_route, _, _ = A_star_task_algorithm(
                            self.agent.map, 
                            self.agent.current_location,
                            self.agent.pending_orders,
                            self.agent.capacity,
                            self.agent.max_fuel
                        )
                        # Mover pending orders para orders
                        self.agent.orders = self.agent.pending_orders.copy()
                        self.agent.pending_orders = []
                    
                    # Calcular próximo nó e tempo restante
                    if self.agent.actual_route:
                        self.agent.next_node = self.agent.actual_route[0][0]
                        _, _ , self.agent.time_to_finish_task = self.agent.map.djikstra(
                            self.agent.current_location,
                            self.agent.next_node
                        )
                        
                        # Notificar event agent do tempo restante para próximo nó
                        await self.notify_event_agent(self.agent.time_to_finish_task, self.agent.next_node)
                else: 
                    # Movimento durante o trânsito
                    print(f"[{self.agent.name}] Movimento durante o trânsito")
                    print(f"[{self.agent.name}] Tempo disponível para mover: {time}")
                    print(f"[{self.agent.name}] localização atual antes de mover: {self.agent.current_location}")
                    temp_location = self.agent.current_location
                    self.agent.current_location = await self.update_location_and_time(time)
                    print(f"[{self.agent.name}] localização atual após mover: {self.agent.current_location}")
                    _, _, tempo_simulado = self.agent.map.djikstra(temp_location, self.agent.current_location)
                    print(f"[{self.agent.name}] Tempo simulado para mover: {tempo_simulado}")
                    
                if type == "Transit":
                    # Atualizar mapa com novas informações de trânsito
                    await self.update_map(data.get("data"))
                
                # Calcular e notificar tempo restante
                if self.agent.next_node:
                    _, _, time_left = self.agent.map.djikstra(
                        self.agent.current_location,
                        self.agent.next_node
                    )
                    await self.notify_event_agent(time_left, self.agent.next_node)
        
        async def process_node_arrival(self, node_id: int, order_id: int):
            """
            Processa a chegada a um nó - verifica se é pickup ou delivery.
            Atualiza carga do veículo e estado das ordens.
            """
            if not order_id:
                return
            
            # Encontrar a ordem correspondente
            order = None
            for o in self.agent.orders:
                if o.orderid == order_id:
                    order = o
                    break
            
            if not order:
                return
            
            # Verificar se é pickup (sender_location)
            if node_id == order.sender_location and not order.comecou:
                print(f"[{self.agent.name}] PICKUP - Ordem {order.orderid} em {node_id}")
                
                # Atualizar carga
                self.agent.current_load += order.quantity
                
                # Reabastecer combustível
                self.agent.current_fuel = self.agent.max_fuel
                
                # Marcar ordem como iniciada
                order.comecou = True
                
                # Mudar status para AWAY (ocupado com tarefa)
                self.agent.presence.set_presence(
                    presence_type=PresenceType.AVAILABLE,
                    show=PresenceShow.AWAY,
                    status=f"Entregando ordem {order.orderid}"
                )
                print(f"[{self.agent.name}] Status alterado para AWAY - processando ordem {order.orderid}")
                
                # Notificar warehouse que começou a entrega
                await self.notify_warehouse_start(order)
                
            # Verificar se é delivery (receiver_location)
            elif node_id == order.receiver_location and order.comecou:
                print(f"[{self.agent.name}] DELIVERY - Ordem {order.orderid} em {node_id}")
                
                # Atualizar carga
                self.agent.current_load -= order.quantity
                
                # Reabastecer combustível
                self.agent.current_fuel = self.agent.max_fuel
                
                # Remover ordem da lista
                self.agent.orders.remove(order)
                
                # Notificar warehouse que completou a entrega
                await self.notify_warehouse_complete(order)
        
        async def notify_warehouse_start(self, order: Order):
            """Notifica o warehouse que a ordem começou a ser processada"""
            msg = Message(to=order.sender)
            msg.set_metadata("performative", "inform")
            msg.set_metadata("type", "order-started")
            
            data = {
                "orderid": order.orderid,
                "vehicle_id": str(self.agent.jid),
                "status": "started",
                "location": self.agent.current_location
            }
            msg.body = json.dumps(data)
            await self.send(msg)
            print(f"[{self.agent.name}] Notificado warehouse: ordem {order.orderid} iniciada")
        
        async def notify_warehouse_complete(self, order: Order):
            """Notifica o warehouse que a ordem foi completada"""
            msg = Message(to=order.receiver)
            msg.set_metadata("performative", "inform")
            msg.set_metadata("type", "order-completed")
            
            data = {
                "orderid": order.orderid,
                "vehicle_id": str(self.agent.jid),
                "status": "completed",
                "location": self.agent.current_location
            }
            msg.body = json.dumps(data)
            await self.send(msg)
            print(f"[{self.agent.name}] Notificado warehouse: ordem {order.orderid} completada")
        
        async def notify_event_agent(self, time_left: float, next_node: int):
            """Notifica o event agent sobre o tempo restante até o próximo nó"""
            if not hasattr(self.agent, 'event_agent_jid'):
                return
            
            msg = Message(to=self.agent.event_agent_jid)
            msg.set_metadata("performative", "inform")
            msg.set_metadata("type", "time-update")
            
            data = {
                "vehicle_id": str(self.agent.jid),
                "current_location": self.agent.current_location,
                "next_node": next_node,
                "time_left": time_left,
            }
            msg.body = json.dumps(data)
            await self.send(msg)
        
        async def update_map(self, traffic_data: dict):
            """Atualiza o mapa com novos dados de trânsito"""
            if not traffic_data:
                return
            
            # Atualizar pesos das arestas com base nos dados de trânsito
            for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge = self.agent.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight
            
            print(f"[{self.agent.name}] Mapa atualizado com novos dados de trânsito") 
                

        async def update_location_and_time(self, time_left):
            """
            Atualiza a localização do veículo baseado no tempo disponível.
            Move-se ao longo da rota enquanto houver tempo.
            Se o tempo acabar a meio de dois vértices, volta para o vértice inicial.
            """
            next_node_id, order = self.agent.actual_route[0]
            if order is None:
                next_node_id = self.agent.actual_route[1][0]
            route_nodes, _ , _ = self.agent.map.djikstra(self.agent.current_location, next_node_id)
            
            # Converter rota de objetos Node para IDs
            route = [node.id for node in route_nodes] if route_nodes else []
            
            remaining_time = time_left
            current_pos = self.agent.current_location
            route_index = 0
            
            # Percorre a rota enquanto houver tempo
            while route_index < len(route) and remaining_time > 0:
                next_node_id = route[route_index]
                print(f"[{self.agent.name}] Rota atual: {route}")
                print(f"[{self.agent.name}] Tentando mover para o nó {next_node_id} com tempo restante {remaining_time}")
                if current_pos == next_node_id:
                    route_index += 1
                    continue
                
                # Obter a aresta entre current_pos e next_node_id
                edge = self.agent.map.get_edge(current_pos, next_node_id)
                
                if edge is None:
                    # Se não há aresta, para
                    break
                
                # Tempo necessário para atravessar esta aresta
                edge_time = edge.weight  # assumindo que weight é o tempo
                print(f"[{self.agent.name}] Tempo necessário para ir de {current_pos} para {next_node_id}: {edge_time}")
                
                if remaining_time >= edge_time:
                    # Tempo suficiente para chegar ao próximo nó
                    current_pos = next_node_id
                    remaining_time -= edge_time
                    route_index += 1
                else:
                    # Tempo insuficiente - fica no nó atual
                    break
            
            return current_pos

                                     