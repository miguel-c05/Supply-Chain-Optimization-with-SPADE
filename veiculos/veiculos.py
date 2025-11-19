"""
Módulo de Veículos para Simulação de Supply Chain com SPADE.

Este módulo implementa agentes de veículos autônomos que operam em um sistema de 
supply chain orientado a eventos. Os veículos recebem ordens de warehouses, calculam 
rotas ótimas, gerenciam capacidade de carga e combustível, e executam entregas de 
forma assíncrona.

Classes:
    Order: Representa uma ordem de entrega com origem, destino e produtos.
    Veiculo: Agente SPADE que gerencia a execução de ordens e navegação no mapa.

Exemplo de uso:
    >>> from world.graph import Graph
    >>> mapa = Graph()
    >>> veiculo = Veiculo(
    ...     jid="vehicle1@localhost",
    ...     password="pass123",
    ...     max_fuel=100,
    ...     capacity=50,
    ...     max_orders=10,
    ...     map=mapa,
    ...     weight=1.0,
    ...     current_location=0
    ... )
    >>> await veiculo.start()

Notas:
    - Usa algoritmo A* para otimização de rotas com múltiplas ordens
    - Comunica com warehouses via protocolo FIPA-ACL
    - Integra com event agent para simulação de tempo e trânsito
    - Presença XMPP indica disponibilidade (CHAT=livre, AWAY=ocupado)
"""

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

from veiculos.algoritmo_tarefas import A_star_task_algorithm
from world.graph import Graph


class Order:
    """
    Representa uma ordem de entrega no sistema de supply chain.
    
    Uma ordem encapsula todas as informações necessárias para o transporte de 
    produtos entre dois pontos (sender → receiver). Inclui cálculos de rota,
    tempo de entrega, consumo de combustível e estado de execução.
    
    Attributes:
        product (str): Nome ou identificador do produto a ser entregue.
        quantity (int): Quantidade do produto (afeta capacidade do veículo).
        orderid (int): Identificador único da ordem no sistema.
        sender (str): JID do agente remetente (warehouse de origem).
        receiver (str): JID do agente destinatário (store ou warehouse de destino).
        deliver_time (float | None): Tempo estimado de entrega calculado via Dijkstra.
        route (list[Node] | None): Caminho de nós do sender ao receiver.
        sender_location (int | None): ID do nó de origem no grafo.
        receiver_location (int | None): ID do nó de destino no grafo.
        fuel (float | None): Combustível necessário para completar a rota.
        comecou (bool): Indica se o veículo já fez pickup da ordem (False = pendente, True = em trânsito).
    
    Exemplo:
        >>> order = Order(
        ...     product="Widget",
        ...     quantity=10,
        ...     orderid=42,
        ...     sender="warehouse1@localhost",
        ...     receiver="store5@localhost"
        ... )
        >>> order.time_to_deliver(sender_location=3, receiver_location=7, map=graph, weight=1.0)
        >>> print(f"Tempo de entrega: {order.deliver_time}s")
    """
    
    def __init__(self, product:str, quantity:int, orderid:int, sender:str, receiver:str):
        """
        Inicializa uma nova ordem de entrega.
        
        Args:
            product: Nome ou código do produto.
            quantity: Quantidade de unidades a transportar (afeta load do veículo).
            orderid: Identificador numérico único da ordem.
            sender: JID XMPP do warehouse/agente remetente.
            receiver: JID XMPP do store/agente destinatário.
        
        Note:
            Os atributos de rota (deliver_time, route, fuel) são inicializados como
            None e devem ser calculados posteriormente com time_to_deliver().
        """
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
        
    def __str__(self):
        return (f"Order(id={self.orderid}, product={self.product}, qty={self.quantity}, "
                f"sender={self.sender}, receiver={self.receiver}, "
                f"sender_loc={self.sender_location}, receiver_loc={self.receiver_location}, "
                f"time={self.deliver_time}, fuel={self.fuel}, started={self.comecou})")
        
    def time_to_deliver(self,sender_location:int,receiver_location:int ,map: Graph,weight: float):
        """
        Calcula o tempo de entrega, rota e combustível necessário usando Dijkstra.
        
        Executa o algoritmo de Dijkstra no grafo fornecido para determinar o caminho
        mais curto entre sender e receiver. Atualiza os atributos da ordem com os
        resultados do cálculo (rota, tempo, fuel, localizações).
        
        Args:
            sender_location: ID do nó de origem no grafo (warehouse).
            receiver_location: ID do nó de destino no grafo (store).
            map: Instância de Graph contendo a topologia da rede.
            weight: Peso do veículo (afeta consumo de combustível).
        
        Side Effects:
            Modifica os seguintes atributos da instância:
            - self.route: Lista de objetos Node representando o caminho.
            - self.deliver_time: Tempo total de viagem em segundos.
            - self.fuel: Quantidade de combustível necessária.
            - self.sender_location: Cópia do argumento sender_location.
            - self.receiver_location: Cópia do argumento receiver_location.
        
        Exemplo:
            >>> order = Order("Product", 5, 1, "w1@localhost", "s1@localhost")
            >>> order.time_to_deliver(3, 7, graph, 1.5)
            >>> print(order.route)  # [Node(3), Node(5), Node(7)]
            >>> print(order.deliver_time)  # 45.2
        
        Note:
            O parâmetro weight não é usado na implementação atual, mas está 
            disponível para extensões futuras que considerem peso do veículo.
        """
        #calcula o tempo de entrega baseado no mapa
        path, fuel, time = map.djikstra(int(sender_location), int(receiver_location))
        self.route = path
        self.deliver_time = time
        self.fuel = fuel
        self.sender_location = sender_location
        self.receiver_location = receiver_location

class Veiculo(Agent):
    """
    Agente SPADE que representa um veículo autônomo de entrega.
    
    O Veiculo é um agente inteligente que gerencia ordens de entrega, calcula rotas
    ótimas usando A*, comunica com warehouses e stores, e simula movimento no grafo.
    Integra-se com um event agent para simulação temporal e responde a eventos de
    trânsito.
    
    Arquitetura de Behaviours:
        - ReceiveOrdersBehaviour: Recebe propostas de ordens de warehouses.
        - WaitConfirmationBehaviour: Aguarda confirmação de ordens aceitas.
        - MovementBehaviour: Processa eventos de movimento e chegada a nós.
    
    Protocolo de Comunicação:
        1. Warehouse envia "order-proposal" → Veículo analisa viabilidade
        2. Veículo responde "vehicle-proposal" (can_fit + delivery_time)
        3. Warehouse envia "order-confirmation" → Veículo aceita/rejeita
        4. Event agent envia "arrival"/"Transit" → Veículo move-se
    
    Attributes:
        max_fuel (int): Capacidade máxima do tanque de combustível.
        capacity (int): Capacidade máxima de carga (unidades de produto).
        current_fuel (int): Combustível atual disponível.
        current_load (int): Carga atual sendo transportada.
        max_orders (int): Número máximo de ordens simultâneas permitidas.
        weight (float): Peso do veículo (afeta consumo de combustível).
        orders (list[Order]): Ordens ativas sendo executadas na rota atual.
        map (Graph): Grafo representando a rede de transporte.
        current_location (int): ID do nó onde o veículo está atualmente.
        next_node (int | None): ID do próximo nó de destino na rota.
        fuel_to_next_node (float): Combustível necessário até o próximo nó.
        actual_route (list[tuple[int, int]]): Rota atual como lista de (node_id, order_id).
        pending_orders (list[Order]): Ordens aceitas mas ainda não iniciadas.
        time_to_finish_task (float): Tempo estimado para completar a rota atual.
        pending_confirmations (dict): Ordens aguardando confirmação do warehouse.
    
    Exemplo:
        >>> from world.graph import Graph
        >>> graph = Graph()
        >>> veiculo = Veiculo(
        ...     jid="vehicle1@localhost",
        ...     password="pass123",
        ...     max_fuel=100,
        ...     capacity=50,
        ...     max_orders=10,
        ...     map=graph,
        ...     weight=1.0,
        ...     current_location=0
        ... )
        >>> await veiculo.start()
        >>> # Veículo aguarda ordens de warehouses e processa autonomamente
    
    Note:
        - Presença XMPP: CHAT = disponível, AWAY = executando ordens
        - Usa A* para otimização multi-ordem (minimize tempo total)
        - Reabastecer combustível automático em pickups/deliveries
        - Suporta atualização dinâmica de trânsito via event agent
    """


    def __init__(self, jid:str, password:str, max_fuel:int, capacity:int, max_orders:int, map: Graph, weight: float,current_location:int,event_agent_jid, verbose : bool = False):
        """
        Inicializa um novo agente veículo.
        
        Args:
            jid: Jabber ID (XMPP) do agente no formato "vehicle@domain".
            password: Senha para autenticação XMPP.
            max_fuel: Capacidade máxima do tanque (unidades arbitrárias).
            capacity: Capacidade máxima de carga (unidades de produto).
            max_orders: Máximo de ordens simultâneas (não implementado atualmente).
            map: Instância de Graph com a topologia da rede.
            weight: Peso do veículo para cálculo de combustível.
            current_location: ID do nó inicial do veículo no grafo.
        
        Note:
            O veículo inicia com tanque cheio (current_fuel = max_fuel) e sem carga.
        """
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
        self.event_agent_jid = event_agent_jid
        self.verbose = verbose
        
        # Dicionário para armazenar múltiplas ordens aguardando confirmação
        # Key: orderid, Value: dict com order, can_fit, delivery_time, sender_jid
        self.pending_confirmations = {}


    async def setup(self):
        """
        Configura e inicia os behaviours do agente veículo.
        
        Método chamado automaticamente pelo SPADE quando o agente inicia. Configura:
        - Presença XMPP (aceita todos os contacts, status AVAILABLE/CHAT)
        - Templates de mensagens para filtrar tipos de comunicação
        - Três behaviours cíclicos com templates específicos
        
        Templates criados:
            - order_template: Filtra mensagens "order-proposal" de warehouses.
            - confirmation_template: Filtra mensagens "order-confirmation".
            - event_template: Filtra mensagens "inform" do event agent.
        
        Side Effects:
            - Adiciona ReceiveOrdersBehaviour para receber propostas.
            - Adiciona WaitConfirmationBehaviour para processar confirmações.
            - Adiciona MovementBehaviour para processar eventos de tempo/movimento.
            - Configura presença como AVAILABLE/CHAT (disponível).
        
        Note:
            O template filtering evita que behaviours processem mensagens incorretas.
        """
        from spade.template import Template
        
        self.presence.approve_all=True
        self.presence.set_presence(presence_type=PresenceType.AVAILABLE,
                                   show=PresenceShow.CHAT)
        
        print(f"[{self.name}] Vehicle agent setup complete. Presence: AVAILABLE/CHAT")
        
        # Template para receber propostas de ordens dos warehouses
        order_template = Template()
        order_template.set_metadata("performative", "order-proposal")
        #dd
        # Template para receber confirmações dos warehouses
        confirmation_template = Template()
        confirmation_template.set_metadata("performative", "order-confirmation")
        
        # Template para receber mensagens do event agent (tick, arrival, transit)
        # Não tem performative específico, então vamos filtrar por ausência dos performatives acima
        event_template = Template()
        event_template.set_metadata("performative", "inform")

        inform_template = Template()
        inform_template.set_metadata("performative", "presence-info")
        
        # Template para receber confirmações de pickup dos suppliers
        pickup_confirm_template = Template()
        pickup_confirm_template.set_metadata("performative", "pickup-confirm")
        
        # Template para receber confirmações de delivery dos warehouses/stores
        delivery_confirm_template = Template()
        delivery_confirm_template.set_metadata("performative", "delivery-confirm")
        
        # Adicionar comportamentos cíclicos com templates
        self.add_behaviour(self.ReceiveOrdersBehaviour(), template=order_template)
        self.add_behaviour(self.WaitConfirmationBehaviour(), template=confirmation_template)
        self.add_behaviour(self.MovementBehaviour(), template=event_template)
        self.add_behaviour(self.PresenceInfoBehaviour(),template=inform_template)
        self.add_behaviour(self.ReceivePickupConfirmation(),template=pickup_confirm_template)
        self.add_behaviour(self.ReceiveDeliveryConfirmation(),template=delivery_confirm_template)


    class ReceiveOrdersBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico para receber e processar propostas de ordens.
        
        Este behaviour aguarda continuamente mensagens de warehouses com propostas
        de ordens. Para cada ordem recebida:
        1. Valida campos obrigatórios
        2. Calcula rota e tempo usando time_to_deliver()
        3. Verifica se pode encaixar na rota atual (can_fit_in_current_route)
        4. Envia proposta ao warehouse (can_fit + delivery_time)
        5. Armazena ordem em pending_confirmations aguardando resposta
        
        Formato da Mensagem Recebida:
            - Metadata: performative="order-proposal"
            - Body (JSON): {
                "product": str,
                "quantity": int,
                "orderid": int,
                "sender": str (JID),
                "receiver": str (JID),
                "sender_location": int,
                "receiver_location": int
              }
        
        Formato da Resposta Enviada:
            - Metadata: performative="vehicle-proposal"
            - Body (JSON): {
                "orderid": int,
                "can_fit": bool,
                "delivery_time": float,
                "vehicle_id": str (JID)
              }
        
        Note:
            - Não aceita ordens aqui - apenas analisa e propõe
            - WaitConfirmationBehaviour processa a decisão final
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
                

                proposal_msg= Message(to=order.sender)
                proposal_msg.set_metadata("performative", "vehicle-proposal")
                
                proposal_data = {
                    "orderid": order.orderid,
                    "can_fit": can_fit,
                    "delivery_time": delivery_time,
                    "vehicle_id": str(self.agent.jid)
                }
                proposal_msg.body = json.dumps(proposal_data)
                await self.send(proposal_msg)
                
                print(f"[{self.agent.name}] Proposta enviada de volta para {msg.sender} - Ordem {order.orderid}: can_fit={can_fit}, tempo={delivery_time}, order route={order.route}")
                    
                # Guardar informações no dicionário de confirmações pendentes
                self.agent.pending_confirmations[order.orderid] = {
                    "order": order,
                    "can_fit": can_fit,
                    "delivery_time": delivery_time,
                    "sender_jid": str(msg.sender)
                }
                
                print(f"[{self.agent.name}] Ordem {order.orderid} adicionada às confirmações pendentes. Total: {len(self.agent.pending_confirmations)}")
        
        async def calculate_order_info(self, order: Order):
            """
            Calcula a rota, tempo e combustível necessários para a ordem.
            
            Este método é um wrapper assíncrono para o método time_to_deliver da Order.
            Chama o algoritmo de Dijkstra para calcular o caminho mais curto.
            
            Args:
                order: Instância de Order a calcular.
            
            Side Effects:
                Modifica os atributos da ordem:
                - order.route: Caminho de nós
                - order.deliver_time: Tempo de viagem
                - order.fuel: Combustível necessário
                - order.sender_location: Origem
                - order.receiver_location: Destino
            
            Note:
                Método não utilizado no código atual (cálculo feito diretamente em run()).
            """
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
            Verifica se a nova ordem pode ser encaixada na rota atual sem sobrecarga.
            
            Este método é o núcleo da lógica de scheduling do veículo. Simula a execução
            da rota atual adicionando a nova ordem e verifica:
            1. Se o veículo está disponível (CHAT) → aceita imediatamente
            2. Se a rota passa pelo sender da ordem → simula pickup/delivery
            3. Se há overflow de capacidade em algum ponto → rejeita para pending
            4. Calcula tempo de entrega considerando rota atual
            
            Algoritmo:
                - Verifica presença XMPP (CHAT = livre, AWAY = ocupado)
                - Se livre: retorna (True, tempo_direto)
                - Se ocupado: percorre actual_route simulando carga
                - Para cada nó: processa pickup/delivery de ordens existentes
                - Tenta inserir pickup/delivery da nova ordem
                - Se overflow: calcula tempo com A* após rota atual
            
            Args:
                new_order: Ordem a verificar se pode ser inserida.
            
            Returns:
                Tupla (pode_encaixar, tempo_de_entrega) onde:
                - pode_encaixar (bool): True se cabe na rota atual sem overflow.
                - tempo_de_entrega (float): Tempo estimado de entrega em segundos.
            
            Exemplo:
                >>> can_fit, time = await self.can_fit_in_current_route(order)
                >>> if can_fit:
                ...     print(f"Ordem cabe na rota atual, entrega em {time}s")
                ... else:
                ...     print(f"Ordem vai para pending, entrega em {time}s")
            
            Note:
                - A rota é uma lista de (node_id, order_id)
                - Simula carga sem modificar estado real do veículo
                - Se não passa pelo sender, calcula tempo com pending_orders
            """
            # Verificar o estado de presença do agente
            # CHAT = disponível (sem tarefas), AWAY = ocupado (com tarefas)
            presence_show = self.agent.presence.get_show()
            
            
            # Se está em CHAT (disponível), não tem tarefas ativas
            if presence_show == PresenceShow.CHAT:
                _ , order_time, _= A_star_task_algorithm(
                self.agent.map,
                self.agent.current_location,
                [new_order],
                self.agent.capacity,
                self.agent.max_fuel)
                return True, order_time
            
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
            Calcula o tempo de entrega para ordem que não cabe na rota atual.
            
            Quando uma ordem não pode ser encaixada na rota atual (por overflow ou
            porque não passa pelo sender), este método estima quanto tempo levará
            para entregá-la após completar todas as tarefas atuais.
            
            Estratégia:
                1. Determina localização final da rota atual (último nó)
                2. Cria lista com pending_orders + nova ordem
                3. Executa A* desde a localização final com todas as ordens
                4. Adiciona tempo restante da rota atual ao tempo do A*
            
            Args:
                order: Ordem a calcular tempo de entrega futuro.
            
            Returns:
                Tempo total em segundos = tempo_rota_atual + tempo_A*_futuro
            
            Exemplo:
                >>> future_time = await self.calculate_future_delivery_time(order)
                >>> print(f"Ordem será entregue em {future_time}s (após tarefas atuais)")
            
            Note:
                - Usa A* para otimizar rota futura com múltiplas ordens
                - Considera capacidade e combustível na otimização
                - Se actual_route vazia, usa current_location como início
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
    
    class WaitConfirmationBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico que aguarda confirmação de warehouses para aceitar ordens.
        
        Após enviar uma proposta (vehicle-proposal), o veículo aguarda a decisão do
        warehouse. Este behaviour processa a resposta e:
        - Se confirmado + can_fit: adiciona à rota atual (orders) e recalcula
        - Se confirmado + !can_fit: adiciona a pending_orders para execução futura
        - Se rejeitado: descarta a ordem
        - Atualiza presença para AWAY quando aceita primeira ordem
        
        Formato da Mensagem Esperada:
            - Metadata: performative="order-confirmation"
            - Body (JSON): {
                "orderid": int,
                "confirmed": bool
              }
        
        Validações:
            - Verifica se orderid está em pending_confirmations
            - Verifica se sender é o warehouse correto
        
        Side Effects:
            - Modifica self.agent.orders ou self.agent.pending_orders
            - Atualiza self.agent.actual_route via recalculate_route()
            - Muda presença para AWAY (ocupado com tarefas)
            - Remove ordem de pending_confirmations
        
        Note:
            - Só processa se há pending_confirmations (evita loops vazios)
            - Timeout de 1s + sleep(0.1) para economizar CPU
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
                        if not self.agent.next_node and self.agent.actual_route:
                            self.agent.next_node = self.agent.actual_route[1][0]
                        
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] Status alterado para AWAY - tem tarefas pendentes")
                            print(f"[{self.agent.name}] Rota atual: {self.agent.actual_route}")
                    else:
                        print(f"[{self.agent.name}] Ordem {order.orderid} rejeitada pelo warehouse")
                    
                    # Remover do dicionário de confirmações pendentes
                    del self.agent.pending_confirmations[orderid]
                    print(f"[{self.agent.name}] Ordem {orderid} removida das confirmações pendentes. Restantes: {len(self.agent.pending_confirmations)}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Erro ao processar confirmação: {e}")
            else:
                pass  # Nenhuma mensagem recebida, aguardar próximo ciclo
        
        async def recalculate_route(self):
            """
            Recalcula a rota otimizada com todas as ordens atuais usando A*.
            
            Idêntico ao método em ReceiveOrdersBehaviour. Recalcula o caminho ótimo
            para minimizar tempo total considerando todas as ordens aceitas.
            
            Side Effects:
                - self.agent.actual_route: Atualizado com nova sequência
                - self.agent.time_to_finish_task: Atualizado com tempo total
            
            Note:
                Código duplicado - considerar refatorar para método da classe Veiculo.
            """
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
    
    class ReceivePickupConfirmation(CyclicBehaviour):
        """
        Comportamento para receber confirmações de pickup dos suppliers.
        """
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    orderid = data.get("orderid")
                    
                    print(f"[{self.agent.name}] ✅ Confirmação de pickup recebida do supplier {msg.sender} para ordem {orderid}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Erro ao processar confirmação de pickup: {e}")
    
    class ReceiveDeliveryConfirmation(CyclicBehaviour):
        """
        Comportamento para receber confirmações de delivery dos warehouses/stores.
        """
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    orderid = data["orderid"]
                    print(f"[{self.agent.name}] ✅ Confirmação de delivery recebida de {msg.sender} para ordem {orderid}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Erro ao processar confirmação de delivery: {e}")
    
    class MovementBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico que processa eventos de movimento e chegada do event agent.
        
        Este é o behaviour mais complexo, responsável por:
        - Processar eventos "arrival" (chegada a um nó)
        - Processar eventos "Transit" (atualização de trânsito)
        - Simular movimento durante intervalos de tempo
        - Gerenciar pickup e delivery de ordens
        - Recalcular rotas quando necessário
        - Notificar warehouses sobre status das ordens
        
        Tipos de Eventos Processados:
            1. "arrival" + vehicle match:
                - Processa chegada ao nó (pickup ou delivery)
                - Remove nó da actual_route
                - Processa múltiplas tarefas no mesmo nó consecutivamente
                - Se rota vazia: move pending_orders para orders ou fica CHAT
                - Notifica event agent do tempo até próximo nó
            
            2. "Transit":
                - Atualiza pesos das arestas no grafo com novos dados de trânsito
                - Recalcula tempos considerando novo tráfego
            
            3. Outros (movimento durante trânsito):
                - Simula movimento ao longo da rota com tempo disponível
                - Atualiza current_location baseado em quanto tempo passou
        
        Fluxo de Processamento de Arrival:
            1. Pop primeiro nó da actual_route
            2. Chama process_node_arrival() para pickup/delivery
            3. Loop: processa nós consecutivos iguais (múltiplas tarefas)
            4. Se rota vazia → verifica pending_orders ou fica disponível
            5. Calcula próximo nó e notifica event agent
        
        Formato de Mensagem Esperada:
            - Metadata: performative="inform"
            - Body (JSON): {
                "type": "arrival" | "Transit" | outros,
                "time": float,
                "vehicle": str (para arrival),
                "data": {...} (para Transit)
              }
        
        Note:
            - Só processa se presença = AWAY (ocupado)
            - Timeout de 5s para não perder eventos importantes
            - Reabastecer automático em pickups/deliveries
        """

        async def run(self):
            # Verificar se o veículo está ocupado (AWAY = tem tarefas)

            
            msg = await self.receive(timeout=5)  # Timeout maior para não perder mensagens

            presence_show = self.agent.presence.get_show()
            
            if presence_show == PresenceShow.CHAT:
                print(f"[{self.agent.name}] Veículo disponível - ignorando mensagens de movimento")
                # Veículo disponível (sem tarefas) - não processa mensagens de movimento
            if msg:
                # print a mensagem recebida
                print(f"[{self.agent.name}] Mensagem recebida no MovementBehaviour")
                if self.agent.verbose:
                    print(f"  Body: {msg.body}")
                    print(f"  Metadata: {msg.metadata}")
                    
                data = json.loads(msg.body)
                type = data.get("type")
                time = data.get("time")
                veiculo = data.get("vehicle", None)  # Compatibilidade com mensagens antigas
                veiculos = data.get("vehicles", [])  # Nova lista de veículos
                
                # Se não houver lista de veículos mas houver veículo único, usar o antigo formato
                if not veiculos and veiculo:
                    veiculos = [veiculo]
                
                if self.agent.verbose:
                    print(f"  Type: {type}, Vehicle: {veiculo}, Agent name: {self.agent.name}")
                
                # Verificar se este veículo está na lista de veículos
                is_for_this_vehicle = self.agent.name in veiculos
                
                if type == "arrival" and is_for_this_vehicle:
                    # Chegou a um nó - processar chegada
                    self.agent.current_location, order_id = self.agent.actual_route.pop(0)
                    if not order_id:
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
                            if self.agent.verbose:
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
                        self.agent.next_node = self.agent.actual_route[1][0]
                    else:
                        # Definir próximo nó
                        if self.agent.actual_route[0][0] == None:
                            self.agent.next_node = self.agent.actual_route[1][0]
                        else:
                            self.agent.next_node = self.agent.actual_route[0][0]
                elif presence_show == PresenceShow.AWAY: 
                    # Movimento durante o trânsito
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Movimento durante o trânsito")
                        print(f"[{self.agent.name}] Tempo disponível para mover: {time}")
                        print(f"[{self.agent.name}] localização atual antes de mover: {self.agent.current_location}")
                    temp_location = self.agent.current_location
                    self.agent.current_location = await self.update_location_and_time(time)
                    
                    print(f"[{self.agent.name}] localização atual após mover: {self.agent.current_location}")
                    _, _, tempo_simulado = self.agent.map.djikstra(temp_location, self.agent.current_location)
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Tempo simulado para mover: {tempo_simulado}")
                    
                if type == "Transit":
                    if self.agent.verbose:
                        print("Atualizar transito")
                    # Atualizar mapa com novas informações de trânsito
                    await self.update_map(data.get("data"))
                
                # Calcular e notificar tempo restante
                # NÃO notificar se:
                # 1. Tempo simulado é 0 E (evento é Transit OU não está na lista de veículos)
                should_notify = True
                if time == 0:
                    if type == "Transit" or not is_for_this_vehicle:
                        should_notify = False
                        print(f"[{self.agent.name}] ⚠️  Notificação ignorada (time=0 e tipo={type}, is_for_this_vehicle={is_for_this_vehicle})")
                
                if should_notify and self.agent.next_node:
                    _, _, time_left = self.agent.map.djikstra(
                        self.agent.current_location,
                        self.agent.next_node
                    )
                    print(f"[{self.agent.name}] Notificando event agent de {self.agent.current_location}- tempo até próximo nó ({self.agent.next_node}): {time_left}")
                    await self.notify_event_agent(time_left, self.agent.next_node)
        
        async def process_node_arrival(self, node_id: int, order_id: int):
            """
            Processa a chegada do veículo a um nó - pickup ou delivery.
            
            Determina se o nó corresponde ao sender (pickup) ou receiver (delivery)
            da ordem. Atualiza carga do veículo, combustível, estado da ordem e
            presença XMPP. Notifica o warehouse sobre mudanças de status.
            
            Lógica de Decisão:
                - Se node_id == sender_location e !comecou → PICKUP
                  * Incrementa current_load
                  * Marca ordem.comecou = True
                  * Muda presença para AWAY com status específico
                  * Notifica warehouse com "order-started"
                
                - Se node_id == receiver_location e comecou → DELIVERY
                  * Decrementa current_load
                  * Remove ordem de self.agent.orders
                  * Notifica warehouse com "order-completed"
                
                - Ambos casos: Reabastecer combustível (current_fuel = max_fuel)
            
            Args:
                node_id: ID do nó onde o veículo chegou.
                order_id: ID da ordem associada a este nó na rota.
            
            Side Effects:
                - Modifica self.agent.current_load
                - Modifica self.agent.current_fuel (reabastecer)
                - Modifica order.comecou
                - Remove ordem de self.agent.orders (em delivery)
                - Atualiza presença XMPP
                - Envia mensagens ao warehouse
            
            Exemplo:
                >>> await self.process_node_arrival(node_id=5, order_id=42)
                # Se nó 5 é sender da ordem 42:
                # [vehicle1] PICKUP - Ordem 42 em 5
                # [vehicle1] Status alterado para AWAY - processando ordem 42
            
            Note:
                - Se order_id é None ou ordem não existe em orders, retorna sem ação
                - Reabastecimento é instantâneo em ambos os casos
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
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Status alterado para AWAY - processando ordem {order.orderid}")
                
                # Notificar supplier que fez pickup
                await self.notify_supplier_pickup(order)
                
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
        
        async def notify_supplier_pickup(self, order: Order):
            """Notifica o supplier que o veículo fez pickup da ordem"""
            # O sender da ordem é o warehouse, mas o pickup é no supplier
            # Precisamos identificar o supplier pela localização
            supplier_location = order.sender_location
            
            # Construir JID do supplier baseado na localização
            supplier_jid = f"supplier{supplier_location}@localhost"
            
            msg = Message(to=supplier_jid)
            msg.set_metadata("performative", "vehicle-pickup")
            msg.set_metadata("supplier_id", supplier_jid)
            msg.set_metadata("vehicle_id", str(self.agent.jid))
            msg.set_metadata("order_id", str(order.orderid))
            
            order_dict = {
                "product": order.product,
                "quantity": order.quantity,
                "orderid": order.orderid,
                "sender": order.sender,
                "receiver": order.receiver,
                "sender_location": order.sender_location,
                "receiver_location": order.receiver_location
            }
            msg.body = json.dumps(order_dict)
            await self.send(msg)
            print(f"[{self.agent.name}] Notificado supplier {supplier_jid}: pickup ordem {order.orderid}")
        
        async def notify_warehouse_start(self, order: Order):
            """
            Notifica o warehouse que a ordem começou a ser processada (pickup realizado).
            
            Envia mensagem FIPA-ACL ao warehouse remetente informando que o veículo
            fez o pickup da carga e iniciou a entrega.
            
            Args:
                order: Ordem que foi iniciada.
            
            Mensagem Enviada:
                - To: order.sender (warehouse JID)
                - Metadata: performative="inform", type="order-started"
                - Body (JSON): {
                    "orderid": int,
                    "vehicle_id": str,
                    "status": "started",
                    "location": int
                  }
            """
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
            print(f"[{self.agent.name}] Notificado {order.sender}: ordem {order.orderid} iniciada")
        
        async def notify_warehouse_complete(self, order: Order):
            """
            Notifica o warehouse que a ordem foi completada (delivery realizado).
            
            Envia mensagem FIPA-ACL ao warehouse/store destinatário informando que
            a entrega foi concluída com sucesso.
            
            Args:
                order: Ordem que foi completada.
            
            Mensagem Enviada:
                - To: order.receiver (store/warehouse JID)
                - Metadata: performative="inform", type="order-completed"
                - Body (JSON): {
                    "orderid": int,
                    "vehicle_id": str,
                    "status": "completed",
                    "location": int
                  }
            """
            msg = Message(to=order.receiver)
            msg.set_metadata("performative", "vehicle-delivery")
            
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
            """
            Notifica o event agent sobre o tempo restante até o próximo nó.
            
            Informa ao event agent quanto tempo o veículo levará para chegar ao
            próximo nó da rota. O event agent usa essa informação para escalonar
            eventos de "arrival" na simulação.
            
            Args:
                time_left: Tempo em segundos até chegar ao próximo nó.
                next_node: ID do próximo nó de destino.
            
            Mensagem Enviada:
                - To: self.agent.event_agent_jid
                - Metadata: performative="inform", type="time-update"
                - Body (JSON): {
                    "vehicle_id": str,
                    "current_location": int,
                    "next_node": int,
                    "time_left": float
                  }
            
            Note:
                - Só envia se event_agent_jid estiver configurado
                - Retorna silenciosamente se atributo não existir
            """
            
            msg = Message(to=self.agent.event_agent_jid)
            msg.set_metadata("performative", "inform")
            msg.set_metadata("type", "time-update")
            
            data = {
                "type": "arrival",
                "vehicle_id": str(self.agent.jid),
                "current_location": self.agent.current_location,
                "next_node": next_node,
                "time": time_left,
            }
            msg.body = json.dumps(data)
            await self.send(msg)
        
        async def update_map(self, traffic_data: dict):
            """
            Atualiza o grafo com novos dados de trânsito recebidos do event agent.
            
            Processa eventos "Transit" que contêm informações sobre mudanças de peso
            nas arestas (representando congestionamento, obras, etc.). Atualiza os
            pesos das arestas no grafo do veículo.
            
            Args:
                traffic_data: Dicionário com estrutura:
                  {
                      "edges": [
                          {
                              "node1": int,
                              "node2": int,
                              "weight": float (novo peso)
                          },
                          ...
                      ]
                  }
            
            Side Effects:
                Modifica self.agent.map.edges - atualiza pesos das arestas.
            
            Exemplo:
                >>> traffic_data = {
                ...     "edges": [
                ...         {"node1": 3, "node2": 7, "weight": 25.5},
                ...         {"node1": 7, "node2": 9, "weight": 18.3}
                ...     ]
                ... }
                >>> await self.update_map(traffic_data)
                # [vehicle1] Mapa atualizado com novos dados de trânsito
            
            Note:
                - Se traffic_data for None ou vazio, retorna sem ação
                - Usa map.get_edge() para encontrar aresta bidirecional
                - Não recalcula rota automaticamente (considerar implementar)
            """

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
            Atualiza a localização do veículo baseado no tempo disponível de movimento.
            
            Simula o movimento do veículo ao longo da rota entre current_location e
            next_node durante um intervalo de tempo. Se o tempo disponível for
            suficiente, o veículo avança para o próximo nó; caso contrário, fica
            no nó atual (movimento discreto entre vértices).
            
            Algoritmo:
                1. Calcula rota de current_location até next_node usando Dijkstra
                2. Converte rota de objetos Node para lista de IDs
                3. Percorre rota sequencialmente:
                   - Para cada aresta, obtém tempo necessário (edge.weight)
                   - Se remaining_time >= edge_time: move para próximo nó
                   - Se remaining_time < edge_time: fica no nó atual
                4. Retorna nova localização
            
            Args:
                time_left: Tempo disponível para movimento (em segundos).
            
            Returns:
                ID do nó onde o veículo está após simular o movimento.
            
            Exemplo:
                >>> # Veículo em nó 3, next_node = 7, tempo disponível = 15s
                >>> # Rota: 3 → 5 (10s) → 7 (8s)
                >>> new_location = await self.update_location_and_time(15.0)
                >>> print(new_location)  # 5 (chegou ao nó 5, mas não ao 7)
            
            Side Effects:
                Nenhum - método é puro, não modifica estado do veículo.
                O chamador (run) é responsável por atualizar current_location.
            
            Note:
                - Movimento é discreto (só para em vértices, não em arestas)
                - Se tempo insuficiente para qualquer aresta, fica no nó atual
                - Considera next_node da actual_route[0] ou actual_route[1] se [0] tem order=None
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

    class PresenceInfoBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico que responde a pedidos de informação de presença.
        
        Este behaviour aguarda mensagens com performative="presence-info" e responde
        com a informação atual de presença do veículo (status e disponibilidade).
        
        Formato da Mensagem Recebida:
            - Metadata: performative="presence-info"
            - Body: Qualquer conteúdo (ignorado)
        
        Formato da Resposta Enviada:
            - Metadata: performative="presence-response"
            - Body (JSON): {
                "vehicle_id": str (JID do veículo),
                "presence_type": str (AVAILABLE, UNAVAILABLE, etc.),
                "presence_show": str (CHAT, AWAY, DND, XA),
                "status": str (mensagem de status),
                "current_location": int,
                "current_load": int,
                "current_fuel": int,
                "active_orders": int,
                "pending_orders": int
              }
        
        Note:
            - Sempre responde ao remetente da mensagem
            - Timeout de 1s para evitar uso excessivo de CPU
        """
        
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                print(f"[{self.agent.name}] 📩 Pedido de presença recebido de {msg.sender}")
                
                # Obter informações de presença atuais
                presence_type = self.agent.presence.get_presence().type
                presence_show = self.agent.presence.get_show()
                presence_status = self.agent.presence.get_status()
                
                # Criar resposta com informações de presença e estado do veículo
                reply = msg.make_reply()
                reply.set_metadata("performative", "presence-response")
                reply.set_metadata("vehicle_id", str(self.agent.jid))
                
                response_data = {
                    "vehicle_id": str(self.agent.jid),
                    "presence_type": str(presence_type),
                    "presence_show": str(presence_show),
                    "status": presence_status if presence_status else "Sem status",
                    "current_location": self.agent.current_location,
                    "current_load": self.agent.current_load,
                    "current_fuel": self.agent.current_fuel,
                    "active_orders": len(self.agent.orders),
                    "pending_orders": len(self.agent.pending_orders)
                }
                
                reply.body = json.dumps(response_data)
                
                await self.send(reply)
                print(f"[{self.agent.name}] ✅ Resposta de presença enviada para {msg.sender}")
                print(f"  Status: {presence_show}, Localização: {self.agent.current_location}, Ordens ativas: {len(self.agent.orders)}")

                                     