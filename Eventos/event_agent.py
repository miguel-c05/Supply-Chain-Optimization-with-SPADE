"""
Este módulo implementa um sistema de gestão de eventos baseado em prioridades temporais,
utilizando uma estrutura de min heap para ordenar e processar eventos de forma eficiente.
O agente é responsável por receber, armazenar e distribuir eventos relacionados com
a simulação de uma cadeia de abastecimento, incluindo eventos de chegada de veículos,
alterações de tráfego e outras ocorrências temporais.

Classes:
    Event: Representa um evento individual com tipo, tempo e dados associados.
    EventDrivenAgent: Agente SPADE que gere a heap de eventos e processa periodicamente.

Dependências:
    - asyncio: Operações assíncronas
    - heapq: Estrutura de dados heap para ordenação eficiente
    - json: Serialização de mensagens
    - typing: Anotações de tipo
    - spade: Framework de agentes multi-agente
"""

import asyncio
import heapq
import json
from datetime import datetime
from typing import List, Dict, Any
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.presence import PresenceType, PresenceShow


class Event:
    """
    Representa um evento temporal na simulação.
    
    Esta classe encapsula informações sobre eventos que ocorrem em momentos específicos
    durante a simulação. Os eventos são comparáveis e ordenáveis por tempo, permitindo
    a sua utilização numa estrutura de min heap para processamento por ordem cronológica.
    
    Os eventos podem representar diferentes tipos de ocorrências:
        - "arrival": Chegada de um veículo a um nó (armazém, loja, posto de combustível)
        - "transit": Alteração nas condições de trânsito numa aresta do grafo
        - "updatesimulation": Pedido de actualização da simulação de tráfego
        - Outros tipos personalizados conforme necessário
    
    Attributes:
        event_type (str): Tipo do evento (e.g., "arrival", "transit", "updatesimulation").
        time (float): Momento temporal em que o evento ocorre, em segundos de simulação.
        data (Dict[str, Any]): Dicionário contendo dados específicos do evento.
        sender (str, optional): Identificador JID do agente que enviou o evento.

    Examples:
        >>> # Criar evento de chegada de veículo
        >>> arrival_event = Event(
        ...     event_type="arrival",
        ...     time=15.5,
        ...     data={"location": "warehouse_1"},
        ...     sender="vehicle1@localhost"
        ... )
        >>> 
        >>> # Criar evento de alteração de trânsito
        >>> transit_event = Event(
        ...     event_type="transit",
        ...     time=20.0,
        ...     data={
        ...         "edges": [{
        ...             "node1": 5,
        ...             "node2": 8,
        ...             "weight": 12.3,
        ...             "fuel_consumption": 2.5
        ...         }]
        ...     }
        ... )
        >>> 
        >>> # Comparar eventos por tempo
        >>> arrival_event < transit_event
        True
    
    Note:
        A comparação entre eventos é realizada exclusivamente com base no atributo `time`.
        Eventos com o mesmo tempo são considerados iguais para efeitos de ordenação,
        mas podem ter tipos e dados diferentes.
    """
    
    def __init__(self, event_type: str, time: float, data: Dict[str, Any], 
                 sender: str = None):
        """
        Inicializa um novo evento.
        
        Args:
            event_type (str): Tipo do evento. Valores comuns incluem "arrival", "transit",
                "updatesimulation". Define o comportamento de processamento do evento.
            time (float): Tempo do evento em segundos de simulação. Utilizado para
                ordenação na min heap. Valores menores têm prioridade.
            data (Dict[str, Any]): Dicionário com dados específicos do evento. A estrutura
                varia conforme o tipo de evento:
                - arrival: {"location": str, "vehicle": str}
                - transit: {"edges": List[Dict], "node1": int, "node2": int, "weight": float}
                - updatesimulation: {"action": str}
            sender (str, optional): JID completo do agente remetente (formato: "nome@servidor").
                Se None, o evento é interno ou gerado pelo sistema.
        
        Examples:
            >>> event = Event("arrival", 10.5, {"vehicle": "v1"}, "vehicle1@localhost")
            >>> event.time
            10.5
            >>> event.event_type
            'arrival'
        """
        self.event_type = event_type  # "arrival", "transit", etc.
        self.time = time  # Tempo do evento
        self.data = data  # Dados do evento
        self.sender = sender  # Quem enviou o evento
    
    def __lt__(self, other):
        """
        Operador de comparação menor que (<) para ordenação na min heap.
        
        Args:
            other (Event): Outro evento para comparação.
        
        Returns:
            bool: True se este evento tem tempo menor (maior prioridade), False caso contrário.
        
        Note:
            Este método é essencial para o funcionamento correcto do heapq.
            Eventos com menor tempo são processados primeiro (min heap).
        """
        return self.time < other.time
    
    def __le__(self, other):
        """
        Operador menor ou igual (<=).
        
        Args:
            other (Event): Outro evento para comparação.
        
        Returns:
            bool: True se este evento tem tempo menor ou igual ao outro.
        """
        return self.time <= other.time
    
    def __gt__(self, other):
        """
        Operador maior que (>).
        
        Args:
            other (Event): Outro evento para comparação.
        
        Returns:
            bool: True se este evento tem tempo maior que o outro.
        """
        return self.time > other.time
    
    def __ge__(self, other):
        """
        Operador maior ou igual (>=).
        
        Args:
            other (Event): Outro evento para comparação.
        
        Returns:
            bool: True se este evento tem tempo maior ou igual ao outro.
        """
        return self.time >= other.time
    
    def __eq__(self, other):
        """
        Operador de igualdade (==).
        
        Args:
            other (Event): Outro evento para comparação.
        
        Returns:
            bool: True se os eventos têm o mesmo tempo.
        
        Note:
            Apenas o tempo é comparado. Eventos com mesmo tempo mas tipos
            diferentes são considerados iguais para ordenação.
        """
        return self.time == other.time
    
    def __repr__(self):
        """
        Representação textual do evento para debugging.
        
        Returns:
            str: String formatada com informações principais do evento.
        
        Examples:
            >>> event = Event("arrival", 15.5, {}, "vehicle1@localhost")
            >>> repr(event)
            'Event(type=arrival, time=15.50, sender=vehicle1@localhost)'
        """
        return f"Event(type={self.event_type}, time={self.time:.2f}, sender={self.sender})"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Converte o evento para formato de dicionário para transmissão via mensagens.
        
        Este método serializa o evento num formato adequado para envio através
        do sistema de mensagens SPADE. A estrutura do dicionário varia conforme
        o tipo de evento para optimizar a transmissão de dados.
        
        Returns:
            Dict[str, Any]: Dicionário com campos apropriados ao tipo de evento:
                - arrival: {"type": str, "time": float, "vehicle": str}
                - transit: {"type": str, "time": float, "data": Dict}
                - outros: {"type": str, "time": float, "data": Dict}
        
        Examples:
            >>> arrival_event = Event("arrival", 10.5, {}, "vehicle1@localhost")
            >>> arrival_event.to_dict()
            {'type': 'arrival', 'time': 10.5, 'vehicle': 'vehicle1'}
            >>>
            >>> transit_event = Event("transit", 5.0, {"edges": [...]})
            >>> transit_event.to_dict()
            {'type': 'transit', 'time': 5.0, 'data': {'edges': [...]}}
        
        Note:
            Para eventos de arrival, o nome do veículo é extraído do JID do sender
            (parte antes do '@'). Para eventos de trânsito, todos os dados são incluídos.
        """
        if self.event_type == "arrival":
            return {
                "type": self.event_type,
                "time": self.time,
                "vehicle": self.sender.split('@')[0],
            }
        elif self.event_type == "Transit" or self.event_type == "transit":
            return {
                "type": self.event_type,
                "time": self.time,
                "data": self.data
            }
        else:
            return {
                "type": self.event_type,
                "time": self.time,
                "data": self.data
            }


class EventDrivenAgent(Agent):
    """
    Agente orientado a eventos que gere uma simulação temporal baseada em heap.
    
    Este agente é o núcleo do sistema de gestão de eventos da simulação de cadeia
    de abastecimento. Utiliza uma estrutura de min heap para manter eventos ordenados
    por tempo e processa-os periodicamente em intervalos configuráveis. O agente
    coordena comunicações entre veículos, armazéns, lojas e o agente do mundo,
    garantindo que todos os participantes recebam notificações de eventos relevantes.
    
    Arquitetura:
        - **Min Heap**: Armazena eventos gerais ordenados por tempo
        - **Transit Events**: Lista separada para eventos de alteração de tráfego
        - **Arrival Events**: Lista temporária para chegadas de veículos
        - **Behaviours**: Conjuntos de comportamentos assíncronos que executam
          diferentes funcionalidades (recepção, processamento, notificação)
    
    Fluxo de Trabalho:
        1. **Inicialização**: Subscreve todos os agentes registados e envia sinal inicial
        2. **Recepção Contínua**: Behaviour cíclico recebe eventos de todos os agentes
        3. **Processamento Periódico**: A cada intervalo, processa eventos da heap
        4. **Notificação**: Distribui eventos processados aos agentes apropriados
        5. **Resimulação**: Solicita nova simulação de tráfego quando necessário
    
    Attributes:
        event_heap (List[Event]): Min heap de eventos gerais ordenados por tempo.
        transit_events (List[Event]): Lista de eventos de trânsito activos.
        arrival_events (List[Event]): Buffer temporário para eventos de chegada.
        simulation_interval (float): Intervalo em segundos entre processamentos.
        registered_vehicles (List[str]): JIDs dos veículos registados no sistema.
        registered_warehouses (List[str]): JIDs dos armazéns registados.
        registered_stores (List[str]): JIDs das lojas registadas.
        world_agent (str): JID do agente do mundo para simulação de tráfego.
        world_simulation_time (float): Duração em segundos da simulação de tráfego.
        event_count (int): Contador total de eventos recebidos.
        processed_count (int): Contador total de eventos processados.
        last_simulation_time (float): Timestamp da última simulação processada.
        time_simulated (float): Tempo total de simulação acumulado.
        verbose (bool): Flag para activar logs detalhados.
    
    Behaviours:
        SendInitialSignalBehaviour: Envia sinal inicial aos veículos (OneShotBehaviour).
        RegisterTransitBehaviour: Solicita simulação inicial de tráfego (OneShotBehaviour).
        ReceiveEventsBehaviour: Recebe eventos continuamente (CyclicBehaviour).
        ProcessEventsBehaviour: Processa eventos periodicamente (PeriodicBehaviour).
    
    Examples:
        >>> # Criar agente de eventos com configuração básica
        >>> event_agent = EventDrivenAgent(
        ...     jid="event_agent@localhost",
        ...     password="senha123",
        ...     simulation_interval=5.0,
        ...     registered_vehicles=["vehicle1@localhost", "vehicle2@localhost"],
        ...     registered_warehouses=["warehouse1@localhost"],
        ...     registered_stores=["store1@localhost"],
        ...     world_agent="world@localhost",
        ...     world_simulation_time=10.0,
        ...     verbose=True
        ... )
        >>> 
        >>> # Iniciar o agente
        >>> await event_agent.start()
        >>> 
        >>> # O agente irá:
        >>> # 1. Subscrever todos os agentes registados
        >>> # 2. Enviar sinal inicial aos veículos
        >>> # 3. Solicitar simulação de tráfego ao world agent
        >>> # 4. Receber e processar eventos continuamente
    
    Note:
        O agente utiliza uma estratégia de processamento híbrida:
        - Eventos de trânsito são mantidos separados e têm o seu tempo decrementado
        - Eventos de arrival são agrupados antes do processamento
        - Eventos gerais são processados por ordem temporal estrita
        
        Apenas eventos com o mesmo tempo do primeiro evento na heap são processados
        em cada ciclo, garantindo sincronização temporal correcta.
    
    Warning:
        O agente requer que o servidor XMPP esteja a funcionar antes da inicialização.
        Todos os JIDs registados devem existir e estar acessíveis para comunicação.
    
    """
    
    def __init__(self, jid: str, password: str, simulation_interval: float, registered_vehicles: List[str],
                 registered_warehouses: List[str], registered_stores: List[str] ,registered_suppliers: List[str],
                 world_agent: str, world_simulation_time: float, verbose: bool):
        """
        Inicializa o EventDrivenAgent com configurações de simulação e agentes registados.
        
        Args:
            jid (str): Jabber ID completo do agente (formato: "nome@servidor").
            password (str): Palavra-passe para autenticação no servidor XMPP.
            simulation_interval (float): Intervalo em segundos entre ciclos de processamento
                de eventos. Valores típicos: 1.0 a 10.0 segundos.
            registered_vehicles (List[str]): Lista de JIDs dos veículos que participam
                na simulação. Estes agentes receberão notificações de eventos relevantes.
            registered_warehouses (List[str]): Lista de JIDs dos armazéns registados.
            registered_stores (List[str]): Lista de JIDs das lojas registadas.
            world_agent (str): JID do agente do mundo responsável pela simulação de tráfego.
                Se None, funcionalidades de tráfego são desactivadas.
            world_simulation_time (float): Duração em segundos de cada simulação de tráfego
                solicitada ao world agent. Determina o horizonte temporal de previsão.
            verbose (bool): Se True, activa logs detalhados para debugging e monitorização.
                Se False, apenas mensagens essenciais são exibidas.
        
        Examples:
            >>> # Configuração para simulação pequena com 2 veículos
            >>> agent = EventDrivenAgent(
            ...     jid="events@localhost",
            ...     password="pass123",
            ...     simulation_interval=5.0,
            ...     registered_vehicles=["v1@localhost", "v2@localhost"],
            ...     registered_warehouses=["w1@localhost"],
            ...     registered_stores=["s1@localhost", "s2@localhost"],
            ...     world_agent="world@localhost",
            ...     world_simulation_time=15.0,
            ...     verbose=False
            ... )
            >>> 
            >>> # Configuração para simulação grande com logging detalhado
            >>> agent_verbose = EventDrivenAgent(
            ...     jid="events@localhost",
            ...     password="pass123",
            ...     simulation_interval=2.0,
            ...     registered_vehicles=[f"vehicle{i}@localhost" for i in range(10)],
            ...     registered_warehouses=[f"warehouse{i}@localhost" for i in range(5)],
            ...     registered_stores=[f"store{i}@localhost" for i in range(20)],
            ...     world_agent="world@localhost",
            ...     world_simulation_time=30.0,
            ...     verbose=True
            ... )
        
        Note:
            O construtor apenas inicializa as estruturas de dados. A subscrição aos
            agentes e início dos behaviours ocorre no método setup().
        """
        super().__init__(jid, password)
        self.event_heap = []  # Min heap de eventos (não-trânsito)
        self.transit_events = []  # Lista separada para eventos de trânsito
        self.arrival_events = []  # Lista separada para eventos de arrival
        self.simulation_interval = simulation_interval  # Intervalo de simulação (5s)
        self.registered_vehicles = registered_vehicles  # Veículos registrados
        self.registered_warehouses = registered_warehouses  # Warehouses registrados
        self.registered_stores = registered_stores  # Stores registrados
        self.registered_suppliers = registered_suppliers  # Suppliers registrados
        self.world_agent = world_agent  # Agente do mundo
        self.world_simulation_time = world_simulation_time  # Tempo de simulação do mundo
        self.event_count = 0  # Contador de eventos recebidos
        self.processed_count = 0  # Contador de eventos processados
        self.last_simulation_time = 0.0  # Tempo da última simulação
        self.time_simulated = 0.0  # Tempo total simulado
        self.verbose = verbose  # Modo verboso
        self.first_arrival_received = False  # Flag para indicar se já recebeu o primeiro arrival
        self.initial_signal_behaviour = None  # Referência para o behaviour de sinal inicial
    async def setup(self):
        """
        Configura e inicializa todos os behaviours e subscrições do agente.
        
        Este método é chamado automaticamente pelo framework SPADE quando o agente
        é iniciado. Configura a presença XMPP, subscreve todos os agentes registados,
        e adiciona os behaviours necessários para o funcionamento do sistema.
        
        Sequência de Inicialização:
            1. Define presença como disponível (AVAILABLE/CHAT)
            2. Aprova automaticamente todos os pedidos de subscrição
            3. Subscreve veículos, armazéns, lojas e world agent
            4. Adiciona SendInitialSignalBehaviour (executa uma vez)
            5. Adiciona RegisterTransitBehaviour (solicita simulação inicial)
            6. Adiciona ReceiveEventsBehaviour (recepção contínua)
            7. Adiciona ProcessEventsBehaviour (processamento periódico)
        
        Raises:
            SPADEException: Se houver problemas na conexão XMPP ou subscrição.
        
        Note:
            A ordem de adição dos behaviours é importante. O sinal inicial e o
            pedido de simulação de tráfego devem executar antes do processamento
            começar a funcionar.
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"[{self.name}] Event-Driven Agent iniciado")
            print(f"[{self.name}] Intervalo de simulação: {self.simulation_interval}s")
            print(f"[{self.name}] Tempo de simulação do mundo: {self.world_simulation_time}s")
            print(f"{'='*70}\n")
        else:
            print(f"[{self.name}] Event-Driven Agent iniciado")
        self.presence.approve_all = True
        
        # Subscribe a cada agente individualmente
        all_agents = self.registered_vehicles + self.registered_warehouses + self.registered_stores
        if self.world_agent:
            all_agents.append(self.world_agent)
        
        for agent_jid in all_agents:
            self.presence.subscribe(agent_jid)
        
        self.presence.set_presence(PresenceType.AVAILABLE, PresenceShow.CHAT)
        
        # Behaviour para receber eventos continuamente (deve estar ativo desde o início)
        receive_behaviour = self.ReceiveEventsBehaviour()
        self.add_behaviour(receive_behaviour)
        
        # Behaviour para enviar mensagem sinaleira inicial (periódico até receber arrival)
        self.initial_signal_behaviour = self.SendInitialSignalBehaviour(period=10)  # Envia a cada 2s
        self.add_behaviour(self.initial_signal_behaviour)
        
        # Behaviour para registrar o transito
        transit_registration_behaviour = self.RegisterTransitBehaviour()
        self.add_behaviour(transit_registration_behaviour)
        
        # Behaviour periódico para processar eventos (a cada X segundos)
        # Será iniciado apenas após receber o primeiro arrival
        process_behaviour = self.ProcessEventsBehaviour(period=self.simulation_interval)
        self.add_behaviour(process_behaviour)
    
    class RegisterTransitBehaviour(OneShotBehaviour):
        """
        Behaviour de execução única que solicita simulação inicial de tráfego.
        
        Este behaviour executa apenas uma vez durante a inicialização do EventDrivenAgent,
        envia um pedido ao world agent para simular condições de tráfego por um período
        x. A simulação inicial é crucial para ter dados de trânsito disponíveis
        antes do processamento de eventos começar.
        
        Funcionamento:
            1. Aguarda o agente estar completamente inicializado
            2. Cria mensagem de pedido com performative "request"
            3. Define action como "simulate_traffic"
            4. Envia tempo de simulação e JID do requisitante
            5. World agent responde com eventos de trânsito
        
        Attributes:
            Herda attributes de OneShotBehaviour (sem attributes próprios).
        
        Message Format:
            {
                "simulation_time": float,  # Duração da simulação em segundos
                "requester": str           # JID do event agent
            }
        
        Note:
            A resposta do world agent é processada pelo ReceiveEventsBehaviour,
            que adiciona os eventos de trânsito à lista transit_events.
        """
        
        async def run(self):
            """
            Executa o pedido de simulação de tráfego ao world agent.
            
            Este método envia uma mensagem XMPP ao world agent solicitando a simulação
            de condições de tráfego. O world agent processará o pedido e responderá
            com uma lista de eventos de trânsito que serão recebidos pelo
            ReceiveEventsBehaviour.
            
            Raises:
                SPADEException: Se houver falha no envio da mensagem.
            
            Note:
                Este método executa apenas uma vez. Pedidos subsequentes de simulação
                são geridos por eventos de tipo "updatesimulation" na heap.
            """
            if self.agent.verbose:
                print(f"\n{'='*70}")
                print(f"[{self.agent.name}] 🌍 SOLICITANDO SIMULAÇÃO DE TRÂNSITO AO WORLD AGENT")
                print(f"  Destinatário: {self.agent.world_agent}")
                print(f"  Tempo de simulação: {self.agent.world_simulation_time}s")
                print(f"{'='*70}\n")
            else:
                print(f"[{self.agent.name}] 🌍 SOLICITANDO SIMULAÇÃO DE TRÂNSITO AO WORLD AGENT")
            # Criar mensagem de pedido de simulação
            msg = Message(to=self.agent.world_agent)
            msg.set_metadata("performative", "request")
            msg.set_metadata("action", "simulate_traffic")
            
            data = {
                "simulation_time": self.agent.world_simulation_time,
                "requester": str(self.agent.jid)
            }
            msg.body = json.dumps(data)
            
            await self.send(msg)
            if self.agent.verbose:
                print(f"[{self.agent.name}] ✅ Pedido de simulação de trânsito enviado ao world agent")
        
    class SendInitialSignalBehaviour(PeriodicBehaviour):
        """
        Behaviour de sinalização inicial periódico para activação de veículos.
        
        Este behaviour executa periodicamente (a cada 2 segundos) durante a inicialização,
        enviando mensagens de "arrival" fictícias a todos os veículos registados até que
        o primeiro evento de arrival real seja recebido. O objectivo é garantir que os
        veículos estejam activos e prontos para responder.
        
        Estratégia de Inicialização:
            - Utiliza um nome de veículo fictício ("vehicle_init_signal_999")
            - Tempo do evento é 0.0 (momento inicial)
            - Envia periodicamente até receber primeiro arrival real
            - Termina automaticamente quando first_arrival_received = True
            - Veículos ignoram o evento fictício mas notificam o event agent
        
        Attributes:
            Herda attributes de PeriodicBehaviour.
        
        Message Format:
            {
                "type": "arrival",
                "vehicle": "vehicle_init_signal_999",  # Nome fictício
                "time": 0.0
            }
        
        Examples:
            >>> # Adicionado automaticamente no setup() com período de 2s
            >>> initial_signal = self.SendInitialSignalBehaviour(period=2.0)
            >>> self.add_behaviour(initial_signal)
        
        Note:
            Este mecanismo garante que todos os veículos estejam prontos para
            receber eventos antes da simulação começar efectivamente. O behaviour
            para automaticamente quando o primeiro arrival real é recebido.
        
        Warning:
            Se registered_vehicles estiver vazio, o behaviour termina sem acção
            e emite um aviso no log.
        """
        
        async def run(self):
            """
            Envia sinal de inicialização a todos os veículos registados periodicamente.
            
            Itera sobre a lista de veículos registados e envia a cada um uma
            mensagem de arrival fictícia. Continua a enviar até que o primeiro
            arrival real seja recebido.
            
            Returns:
                None: Executa efeitos colaterais (envio de mensagens).
            
            Note:
                O behaviour verifica a flag first_arrival_received e termina
                quando esta é True. O nome fictício "vehicle_init_signal_999"
                é intencional e não deve corresponder a nenhum veículo real.
            """
            # Verificar se já recebeu o primeiro arrival
            if self.agent.first_arrival_received:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ✅ Primeiro arrival recebido. Parando envio de sinais iniciais.")
                else:
                    print(f"[{self.agent.name}] ✅ Primeiro arrival recebido.")
                self.kill()  # Parar este behaviour
                return
            
            if not self.agent.registered_vehicles:
                print(f"[{self.agent.name}] ⚠️ Nenhum veículo registrado para enviar sinal inicial")
                self.kill()
                return
            
            # Usar nome fictício que não corresponde a nenhum veículo real
            vehicle_name_ficticio = "vehicle_init_signal_999"
            
            # Enviar mensagem para TODOS os veículos registrados
            if self.agent.verbose:
                print(f"\n{'='*70}")
                print(f"[{self.agent.name}] 🚦 ENVIANDO SINAL INICIAL (periódico)")
                print(f"  Destinatários: {len(self.agent.registered_vehicles)} veículos")
                print(f"  Veículo (fictício): {vehicle_name_ficticio}")
                print(f"  Tipo: arrival")
                print(f"  Tempo: 0.1")
                print(f"{'='*70}")
            else:
                print(f"[{self.agent.name}] 🚦 ENVIANDO SINAL INICIAL (aguardando arrival real...)")
            
            for vehicle_jid in self.agent.registered_vehicles:
                # Criar mensagem de arrival inicial com tempo zero
                msg = Message(to=vehicle_jid)
                msg.set_metadata("performative", "inform")
                
                data = {
                    "type": "arrival",
                    "vehicle": vehicle_name_ficticio,  # Nome fictício
                    "time": 0.1
                }
                msg.body = json.dumps(data)
                
                await self.send(msg)
                
                vehicle_name = str(vehicle_jid).split("@")[0]
                if self.agent.verbose:
                    print(f"  → Enviado para: {vehicle_name}")
            
            if self.agent.verbose:
                print(f"{'='*70}\n")
    
    class ReceiveEventsBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico de recepção contínua de eventos de múltiplas fontes.
        
        Este behaviour mantém-se permanentemente activo, recebendo mensagens XMPP
        de todos os agentes registados (veículos, armazéns, lojas, world agent)
        e classificando-as em diferentes categorias de eventos. A recepção é
        não-bloqueante com timeout de 1 segundo para permitir interrupções.
        
        Tipos de Eventos Processados:
            - **Traffic Events**: Eventos de trânsito do world agent (lista completa)
            - **Transit**: Eventos manuais de alteração de trânsito
            - **Arrival**: Eventos de chegada de veículos a nós
            - **UpdateSimulation**: Pedidos de resimulação de tráfego
            - **Outros**: Eventos genéricos adicionados à heap principal
        
        Estratégia de Armazenamento:
            - Transit events → transit_events (lista separada)
            - Arrival events (time > 0) → arrival_events (buffer temporário)
            - Arrival events (time = 0) → descartados (sinal inicial)
            - Outros eventos → event_heap (min heap)
        
        Attributes:
            Herda attributes de CyclicBehaviour.
        
        Message Formats:
            Traffic Events (do world agent):
                {
                    "events": [
                        {
                            "instant": float,
                            "node1_id": int,
                            "node2_id": int,
                            "new_time": float,
                            "new_fuel_consumption": float,
                        },
                        ...
                    ]
                }
            
            Eventos Genéricos:
                {
                    "type": str,
                    "time": float,
                    "data": Dict[str, Any],
                }
        
        Examples:
            >>> # O behaviour executa continuamente após adição
            >>> receive_behaviour = self.ReceiveEventsBehaviour()
            >>> self.add_behaviour(receive_behaviour)
        
        Note:
            O timeout de 1 segundo permite que o behaviour verifique periodicamente
            se deve terminar (e.g., quando o agente é parado). Mensagens recebidas
            são imediatamente processadas e classificadas.
        
        Warning:
            Erros no parsing de JSON são capturados e registados, mas não interrompem
            o behaviour. Eventos malformados são descartados.
        
        See Also:
            ProcessEventsBehaviour: Processa os eventos armazenados.
            Event: Estrutura de dados para representar eventos.
        """
        
        async def run(self):
            """
            Ciclo de recepção e classificação de mensagens de eventos.
            
            Este método executa continuamente, aguardando mensagens com timeout de
            1 segundo. Quando uma mensagem é recebida, identifica o tipo de evento
            e armazena-o na estrutura de dados apropriada.
            
            Fluxo de Processamento:
                1. Aguarda mensagem com timeout de 1s
                2. Verifica se é resposta de traffic events do world agent
                3. Se sim, processa lista completa de eventos de trânsito
                4. Se não, identifica tipo de evento individual
                5. Armazena em transit_events, arrival_events ou event_heap
                6. Incrementa contador de eventos recebidos
            
            Returns:
                None: Executa continuamente até o behaviour ser removido.
            
            Raises:
                Exception: Captura e regista erros de parsing sem interromper.
            
            Note:
                Para eventos de trânsito do world agent, também cria um evento
                de resimulação automático após world_simulation_time.
            """
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    # Verificar se é resposta do world agent com eventos de trânsito
                    if msg.get_metadata("performative") == "inform" and msg.get_metadata("action") == "traffic_events":
                        # Mensagem do world agent com eventos de trânsito
                        data = json.loads(msg.body)
                        events = data.get("events", [])
                        
                        if self.agent.verbose:
                            print(f"\n{'='*70}")
                            print(f"[{self.agent.name}] 🌍 EVENTOS DE TRÂNSITO DO WORLD AGENT RECEBIDOS")
                            print(f"  Total de eventos: {len(events)}")
                            print(f"{'='*70}\n")
                        else:
                            print(f"[{self.agent.name}] 🌍 EVENTOS DE TRÂNSITO DO WORLD AGENT RECEBIDOS")
                        
                        # Processar cada evento de trânsito
                        for event_data in events:
                            # Criar evento de trânsito
                            transit_event = Event(
                                event_type="Transit",
                                time=event_data.get("instant", 0.0),
                                data={
                                    "edges": [{
                                        "node1": event_data.get("node1_id"),
                                        "node2": event_data.get("node2_id"),
                                        "weight": event_data.get("new_time"),
                                        "fuel_consumption": event_data.get("new_fuel_consumption")
                                    }]
                                },
                                sender=str(msg.sender),
                            )
                            
                            # Adicionar à lista de eventos de trânsito
                            self.agent.transit_events.append(transit_event)
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] 📩 Evento de trânsito adicionado: Edge ({event_data.get('node1_id')} → {event_data.get('node2_id')}), time={event_data.get('new_time')}, instant={event_data.get('instant')}")
                        
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] ✅ Total de eventos de trânsito: {len(self.agent.transit_events)}")
                        
                        # Criar evento para solicitar nova simulação após world_simulation_time
                        resimulation_event = Event(
                            event_type="updatesimulation",
                            time=self.agent.world_simulation_time,
                            data={"action": "request_new_simulation"},
                            sender=str(self.agent.jid),
                        )
                        heapq.heappush(self.agent.event_heap, resimulation_event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 🔄 Evento de resimulação adicionado à heap: {resimulation_event}")
                        
                        return
                    
                    # Processar outros eventos normalmente
                    data = json.loads(msg.body)
                    event_type = data.get("type")
                    time = data.get("time", 0.0)
                    event_data = data.get("data", {})
                    
                    # Debug: mostrar dados recebidos
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] 📨 Mensagem recebida:")
                        print(f"   Sender: {msg.sender}")
                        print(f"   Type: {event_type}")
                        print(f"   Time: {time}")
                        print(f"   Data: {event_data}")
                    else:
                        print(f"[{self.agent.name}] 📨 Mensagem recebida de {msg.sender}")
                    
                    # Criar evento
                    event = Event(
                        event_type=event_type,
                        time=time,
                        data=event_data,
                        sender=str(msg.sender),
                    )
                    
                    # Verificar se é evento de trânsito manual (não do world agent)
                    if event_type == "transit" or event_type == "Transit":
                        # Adicionar à lista de trânsito
                        self.agent.transit_events.append(event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 📩 Evento de trânsito manual recebido: {event}")
                            print(f"   Eventos de trânsito: {len(self.agent.transit_events)}")
                    elif event_type == "arrival":
                            if not self.agent.first_arrival_received:
                                self.agent.first_arrival_received = True
                                if self.agent.verbose:
                                    print(f"[{self.agent.name}] ✅ PRIMEIRO ARRIVAL RECEBIDO! Iniciando processamento da heap.")
                                else:
                                    print(f"[{self.agent.name}] ✅ PRIMEIRO ARRIVAL RECEBIDO!")
                            
                            self.agent.arrival_events.append(event)
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] 📩 Evento ARRIVAL adicionado à lista: {event}")
                                print(f"   Eventos de arrival: {len(self.agent.arrival_events)}")
                    else:
                        # Adicionar à heap outros tipos de eventos
                        heapq.heappush(self.agent.event_heap, event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 📩 Evento recebido: {event}")
                            print(f"   Eventos na heap: {len(self.agent.event_heap)}")
                        else:
                            print(f"[{self.agent.name}] 📩 Evento recebido: {event}")    
                    self.agent.event_count += 1
                
                except Exception as e:
                    print(f"[{self.agent.name}] ❌ Erro ao processar mensagem: {e}")
    
    class ProcessEventsBehaviour(PeriodicBehaviour):
        """
        Behaviour periódico responsável pelo processamento temporal de eventos.
        
        Este behaviour é o núcleo do sistema de simulação temporal, executando em
        intervalos regulares (definidos por simulation_interval) para processar
        eventos que ocorrem no mesmo instante temporal. Implementa uma estratégia
        sofisticada de gestão de tempo, garantindo sincronização correcta entre
        todos os eventos e agentes.
        
        Estratégia de Processamento:
            1. **Transferência de Arrivals**: Move eventos de arrival do buffer para a heap
            2. **Integração de Trânsito**: Recoloca eventos de trânsito na heap
            3. **Selecção por Tempo**: Extrai o primeiro evento (menor tempo)
            4. **Agrupamento**: Colecta todos eventos com o mesmo tempo
            5. **Processamento**: Notifica agentes relevantes sobre os eventos
            6. **Actualização de Trânsito**: Decrementa tempo dos eventos de trânsito restantes
            7. **Limpeza**: Esvazia heap (descarta eventos futuros até próximo ciclo)
            8. **Resimulação**: Solicita nova simulação se necessário
        
        Gestão de Tempo:
            - Apenas eventos com tempo igual ao do primeiro evento são processados
            - Eventos de trânsito têm tempo decrementado continuamente
            - Primeiro evento de cada tipo tem tempo real, subsequentes tempo 0
            - Evita simulação duplicada do mesmo intervalo temporal
        
        Attributes:
            period (float): Intervalo em segundos entre execuções (herdado de PeriodicBehaviour).
        
        Fluxo de Notificação:
            - Arrival events → Todos os veículos (mensagem agrupada)
            - Transit events → Veículos + Armazéns + Lojas
            - UpdateSimulation events → World agent
        
        Examples:
            >>> # Criado automaticamente no setup() com período configurável
            >>> process_behaviour = self.ProcessEventsBehaviour(period=5.0)
            >>> self.add_behaviour(process_behaviour)
        
        Note:
            O esvaziamento da heap após processamento é intencional. Garante que
            apenas eventos do próximo instante temporal sejam considerados no
            próximo ciclo, evitando inconsistências temporais.
        
        Warning:
            Se a heap estiver vazia, o ciclo é saltado. Isto é normal quando não
            há eventos pendentes.
        
        See Also:
            notify_events: Método interno para distribuir eventos processados.
            Event: Estrutura de dados dos eventos.
        """
        
        async def run(self):
            """
            Executa um ciclo de processamento de eventos.
            
            Este método é chamado periodicamente pelo framework SPADE no intervalo
            definido por simulation_interval. Coordena todas as etapas de processamento,
            desde a preparação da heap até a notificação dos agentes.
            
            Etapas Detalhadas:
                1. **Preparação da Heap**:
                   - Transfere arrival_events para event_heap
                   - Recoloca transit_events na heap
                   - Esvazia buffers temporários
                
                2. **Verificação de Eventos**:
                   - Se heap vazia, termina ciclo
                   - Regista estado para logging
                
                3. **Extração de Eventos**:
                   - Remove primeiro evento (menor tempo)
                   - Colecta eventos subsequentes com mesmo tempo
                   - Cria lista de eventos a processar
                
                4. **Gestão de Trânsito**:
                   - Remove eventos de trânsito da lista separada
                   - Detecta se foi o último evento de trânsito
                   - Actualiza tempo de eventos restantes
                
                5. **Notificação**:
                   - Chama notify_events() para distribuir aos agentes
                   - Aguarda confirmações de envio
                
                6. **Resimulação**:
                   - Se último evento de trânsito processado
                   - Envia pedido de nova simulação ao world agent
                
                7. **Estatísticas**:
                   - Actualiza contadores
                   - Gera logs detalhados se verbose=True
                
                8. **Limpeza**:
                   - Esvazia event_heap
                   - Prepara para próximo ciclo
            
            Returns:
                None: Executa efeitos colaterais (notificações e actualizações de estado).
            
            Note:
                O decremento do tempo dos eventos de trânsito garante que o tempo
                restante reflicta sempre o intervalo até ao próximo processamento.
                O processamento só começa após receber o primeiro arrival real.
            
            Examples:
                >>> # Exemplo de log verbose durante execução
                [event_agent] 🔄 PROCESSANDO EVENTOS
                [event_agent] Tempo de simulação: 5.0s
                [event_agent] Eventos na heap: 3
                [event_agent] Eventos de trânsito: 5
                
                [event_agent] 📤 Próximo evento: Event(type=arrival, time=10.50, sender=vehicle1@localhost)
                [event_agent] 📋 Total de eventos com tempo 10.50s: 2
                
                [event_agent] 📢 Notificando evento ARRIVAL agrupado para 3 veículos
                   Veículos que chegaram: ['vehicle1', 'vehicle2']
            """
            # Verificar se já recebeu o primeiro arrival antes de processar
            if not self.agent.first_arrival_received:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ⏸️ Aguardando primeiro arrival antes de processar heap...")
                return  # Não processar até receber o primeiro arrival
            
            # Adicionar eventos de arrival à heap e esvaziar a lista
            for arrival_event in self.agent.arrival_events:
                heapq.heappush(self.agent.event_heap, arrival_event)
            if len(self.agent.arrival_events) > 0:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 📥 Adicionados {len(self.agent.arrival_events)} eventos de arrival à heap")
            self.agent.arrival_events = []  # Esvaziar a lista
            
            # Recolocar eventos de trânsito na heap no início
            for transit_event in self.agent.transit_events:
                heapq.heappush(self.agent.event_heap, transit_event)
            
            if self.agent.verbose:
                print(f"\n{'='*70}")
                print(f"[{self.agent.name}] 🔄 PROCESSANDO EVENTOS")
                print(f"[{self.agent.name}] Tempo de simulação: {self.agent.simulation_interval}s")
                print(f"[{self.agent.name}] Eventos na heap: {len(self.agent.event_heap)}")
                print(f"[{self.agent.name}] Eventos de trânsito: {len(self.agent.transit_events)}")
                print(f"{'='*70}\n")
            
            if not self.agent.event_heap:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ℹ️  Nenhum evento para processar\n")
                return
            
            # Tirar o primeiro evento da heap (menor tempo)
            first_event = heapq.heappop(self.agent.event_heap)
            event_time = first_event.time
            events_to_process = [first_event]
            
            print(f"[{self.agent.name}] 📤 Próximo evento: {first_event}")
            
            # Continuar a dar pop enquanto houver eventos com o mesmo tempo
            while self.agent.event_heap and self.agent.event_heap[0].time == event_time:
                next_event = heapq.heappop(self.agent.event_heap)
                events_to_process.append(next_event)
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 📤 Evento adicional (mesmo tempo): {next_event}")
            
            if self.agent.verbose:
                print(f"[{self.agent.name}] 📋 Total de eventos com tempo {event_time:.2f}s: {len(events_to_process)}")
            
            # Processar remoção de eventos de trânsito da lista
            was_last_transit_event = False
            for event in events_to_process:
                if event.event_type == "transit" or event.event_type == "Transit":
                    if event in self.agent.transit_events:
                        self.agent.transit_events.remove(event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 🗑️  Evento de trânsito removido da lista: {event}")
            
            # Verificar se era o último evento de trânsito
            if len(self.agent.transit_events) == 0:
                # Verificar se algum dos eventos processados era de trânsito
                for event in events_to_process:
                    if event.event_type == "transit" or event.event_type == "Transit":
                        was_last_transit_event = True
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] ⚠️  ÚLTIMO EVENTO DE TRÂNSITO REMOVIDO!")
                        break
            
            # Atualizar tempo de todos os eventos de trânsito restantes
            updated_transit_events = []
            for transit_event in self.agent.transit_events:
                transit_event.time -= event_time
                updated_transit_events.append(transit_event)
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 🔄 Trânsito atualizado: {transit_event} (tempo restante: {transit_event.time:.2f}s)")
            
            # Atualizar lista de eventos de trânsito
            self.agent.transit_events = updated_transit_events
            
            # Notificar todos os veículos sobre os eventos processados (sequencialmente)
            await self.notify_events(events_to_process)
            
            self.agent.processed_count += len(events_to_process)
            
            # Atualizar tempo total simulado (soma acumulada de todos os tempos processados)
            self.agent.time_simulated += event_time
            
            # Se foi o último evento de trânsito, solicitar nova simulação
            if was_last_transit_event and self.agent.world_agent:
                if self.agent.verbose:
                    print(f"\n{'='*70}")
                    print(f"[{self.agent.name}] 🔄 SOLICITANDO NOVA SIMULAÇÃO DE TRÂNSITO")
                    print(f"  Motivo: Último evento de trânsito processado")
                    print(f"  Destinatário: {self.agent.world_agent}")
                    print(f"{'='*70}\n")
                else:
                    print(f"[{self.agent.name}] 🔄 SOLICITANDO NOVA SIMULAÇÃO DE TRÂNSITO")
                
                # Enviar pedido de nova simulação
                msg = Message(to=self.agent.world_agent)
                msg.set_metadata("performative", "request")
                msg.set_metadata("action", "simulate_traffic")
                
                data = {
                    "simulation_time": self.agent.world_simulation_time,
                    "requester": str(self.agent.jid)
                }
                msg.body = json.dumps(data)
                
                await self.send(msg)
                print(f"[{self.agent.name}] ✅ Pedido de nova simulação enviado\n")
            if self.agent.verbose:
                print(f"\n[{self.agent.name}] 📊 Estatísticas:")
                print(f"   Eventos processados: {len(events_to_process)}")
                print(f"   Tipos: {', '.join([e.event_type for e in events_to_process])}")
                print(f"   Tempo dos eventos: {event_time:.2f}s")
                print(f"   Trânsitos ativos: {len(self.agent.transit_events)}")
                print(f"   Total recebido: {self.agent.event_count}")
                print(f"   Total processado: {self.agent.processed_count}")
                    
                # Imprimir estado completo da heap restante
                print(f"\n[{self.agent.name}] 📋 ESTADO DA HEAP RESTANTE:")
                if len(self.agent.event_heap) == 0 and len(self.agent.transit_events) == 0:
                    print(f"   ➤ Heap vazia (sem eventos)")
                else:
                    # Mostrar eventos normais na heap
                    if len(self.agent.event_heap) > 0:
                        print(f"   ➤ Eventos normais na heap: {len(self.agent.event_heap)}")
                        for i, event in enumerate(sorted(self.agent.event_heap), 1):
                            print(f"      {i}. {event}")
                    else:
                        print(f"   ➤ Eventos normais na heap: 0")
                    
                    # Mostrar eventos de trânsito
                    if len(self.agent.transit_events) > 0:
                        print(f"   ➤ Eventos de trânsito: {len(self.agent.transit_events)}")
                        for i, event in enumerate(sorted(self.agent.transit_events), 1):
                            print(f"      {i}. {event}")
                    else:
                        print(f"   ➤ Eventos de trânsito: 0")
                
                print(f"{'='*70}\n")

            # Esvaziar a heap (descartar outros eventos)
            discarded_count = len(self.agent.event_heap)
            self.agent.event_heap = []
            
            if discarded_count > 0:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 🗑️  Heap esvaziada: {discarded_count} eventos descartados")
        
        async def notify_events(self, events: List[Event]):
            """
            Notifica agentes apropriados sobre eventos processados com agrupamento inteligente.
            
            Este método distribui eventos aos agentes relevantes, implementando estratégias
            de optimização diferentes para cada tipo de evento. O agrupamento de arrivals
            e o ajuste temporal de trânsito garantem eficiência e consistência temporal.
            
            Estratégias por Tipo:
                1. **Arrival Events**:
                   - Agrupados numa única mensagem por veículo
                   - Lista de todos os veículos que chegaram incluída
                   - Enviada a TODOS os veículos registados
                   - Apenas o tempo do primeiro arrival é usado
                
                2. **Transit Events**:
                   - Enviados individualmente mas sequencialmente
                   - Primeiro evento tem tempo real
                   - Eventos subsequentes têm tempo 0 (evita resimulação)
                   - Enviados a veículos, armazéns e lojas
                
                3. **UpdateSimulation Events**:
                   - Enviados apenas ao world agent
                   - Solicita nova simulação de tráfego
                   - Usa tempo configurado em world_simulation_time
            
            Args:
                events (List[Event]): Lista de eventos a notificar. Podem ser de tipos
                    mistos. O método classifica e processa cada tipo adequadamente.
            
            Returns:
                None: Executa efeitos colaterais (envio de mensagens XMPP).
            
            Message Formats:
                Arrival (agrupado):
                    {
                        "type": "arrival",
                        "time": float,              # Tempo do primeiro arrival
                        "vehicles": List[str]       # Lista de nomes de veículos
                    }
                
                Transit (individual):
                    {
                        "type": "Transit",
                        "time": float,              # Real para primeiro, 0 para restantes
                        "data": {
                            "edges": [
                                {
                                    "node1": int,
                                    "node2": int,
                                    "weight": float,
                                    "fuel_consumption": float
                                }
                            ]
                        }
                    }
                
                UpdateSimulation:
                    {
                        "simulation_time": float,
                        "requester": str            # JID do event agent
                    }
            
            Examples:
                >>> # Processar lista mista de eventos
                >>> events = [
                ...     Event("arrival", 10.5, {}, "vehicle1@localhost"),
                ...     Event("arrival", 10.5, {}, "vehicle2@localhost"),
                ...     Event("transit", 10.5, {"edges": [...]})
                ... ]
                >>> await self.notify_events(events)
                
                # Resultado:
                # - 1 mensagem de arrival para cada veículo registado (lista agrupada)
                # - 1 mensagem de transit para veículos + armazéns + lojas
            
            Note:
                O ajuste de tempo para 0 em eventos subsequentes é crucial para evitar
                que múltiplos eventos causem simulações repetidas do mesmo intervalo
                temporal nos agentes receptores.
            
            Warning:
                Se world_agent não estiver configurado, eventos de updatesimulation
                são ignorados silenciosamente com log de aviso.
            
            See Also:
                Event.to_dict(): Serialização de eventos para mensagens.
                ProcessEventsBehaviour.run(): Método que invoca notify_events.
            """
            # Agrupar eventos por tipo
            arrival_events = []
            transit_events = []
            other_events = []
            
            for event in events:
                if event.event_type == "arrival":
                    arrival_events.append(event)
                elif event.event_type == "transit" or event.event_type == "Transit":
                    transit_events.append(event)
                else:
                    other_events.append(event)
            
            # Processar eventos de arrival agrupados
            if arrival_events:
                # Coletar todos os nomes de veículos
                vehicle_names = [event.sender.split('@')[0] for event in arrival_events]
                # Tempo é do primeiro evento
                event_time = arrival_events[0].time
                
                if self.agent.verbose:
                    print(f"\n[{self.agent.name}] 📢 Notificando evento ARRIVAL agrupado para {len(self.agent.registered_vehicles)} veículos")
                    print(f"   Veículos que chegaram: {vehicle_names}")
                else:
                    print(f"\n[{self.agent.name}] 📢 Notificando evento ARRIVAL agrupado para {len(self.agent.registered_vehicles)} veículos")

                # Enviar uma única mensagem para todos os veículos registrados
                recipients = (self.agent.registered_vehicles + 
                            self.agent.registered_stores
                            ) # TODO + self.agent.registered_warehouses + self.agent.registered_suppliers
                for recipient_jid in recipients:
                    msg = Message(to=recipient_jid)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("event_type", "arrival")
                    
                    # Criar mensagem com lista de veículos
                    event_dict = {
                        "type": "arrival",
                        "time": event_time,
                        "vehicles": vehicle_names  # Lista de veículos
                    }
                    
                    msg.body = json.dumps(event_dict)
                    
                    await self.send(msg)
                    recipient_name = recipient_jid.split('@')[0]
                    
                    if self.agent.verbose:
                        print(f"[{self.agent.name}]   → {recipient_name}: arrival (vehicles={vehicle_names}, time={event_time:.4f}s)")
            
            # Processar eventos de trânsito
            for idx, event in enumerate(transit_events):
                recipients = (self.agent.registered_vehicles + 
                            self.agent.registered_stores
                            ) # TODO + self.agent.registered_warehouses + self.agent.registered_suppliers
                print(recipients)
                if self.agent.verbose:
                    print(f"\n[{self.agent.name}] 📢 Notificando evento TRANSIT para {len(recipients)} agentes")
                
                for recipient_jid in recipients:
                    msg = Message(to=recipient_jid)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("event_type", "Transit")
                    
                    event_dict = event.to_dict()
                    
                    # Apenas o primeiro evento tem o tempo real
                    if idx > 0:
                        original_time = event_dict["time"]
                        event_dict["time"] = 0
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 🔄 Ajustando tempo do evento Transit para 0 (original={original_time:.2f}s) para {recipient_jid.split('@')[0]}")
                    
                    msg.body = json.dumps(event_dict)
                    
                    await self.send(msg)
                    recipient_name = recipient_jid.split('@')[0]
                    if self.agent.verbose:
                        print(f"[{self.agent.name}]   → {recipient_name}: Transit (time={event_dict['time']:.4f}s)")
            
            # Processar outros eventos (updatesimulation, etc)
            for event in other_events:
                if event.event_type == "updatesimulation":
                    if self.agent.world_agent:
                        if self.agent.verbose:
                            print(f"\n[{self.agent.name}] 📢 Processando evento UPDATESIMULATION - Solicitando nova simulação")
                        
                        msg = Message(to=self.agent.world_agent)
                        msg.set_metadata("performative", "request")
                        msg.set_metadata("action", "simulate_traffic")
                        
                        data = {
                            "simulation_time": self.agent.world_simulation_time,
                            "requester": str(self.agent.jid)
                        }
                        msg.body = json.dumps(data)
                        
                        await self.send(msg)
                        print(f"[{self.agent.name}]   → Pedido de re-simulação enviado ao world agent")
                    else:
                        print(f"\n[{self.agent.name}] ⚠️  Agente do mundo não registrado, evento ignorado")
    

async def main():
    """
    Função principal para execução de teste completo do sistema Event-Driven Agent.
    
    Esta função de teste demonstra a integração completa entre o EventDrivenAgent,
    veículos, armazéns e o world agent. Cria um ambiente de simulação realista
    com um mundo gerado proceduralmente, múltiplos veículos, e eventos dinâmicos
    de tráfego e entregas.
    
    Componentes Criados:
        1. **World**: Grafo 10x10 com tráfego dinâmico, highways e localizações
        2. **World Agent**: Simula condições de tráfego e gera eventos
        3. **Event Agent**: Coordena todos os eventos da simulação
        4. **Veículos (3x)**: Agentes móveis que respondem a ordens e eventos
        5. **Warehouse Agent**: Envia ordens de teste aos veículos
    
    Configurações do Mundo:
        - Dimensões: 10x10 nós
        - Modo: "different" (custos variados)
        - Custo máximo de aresta: 4
        - Warehouses: 5
        - Suppliers: 1
        - Stores: 4
        - Highway: Activada
        - Probabilidade de tráfego: 0.5
        - Probabilidade de propagação: 0.8
        - Intervalo de tráfego: 2 segundos
        - Probabilidade de destráfego: 0.4
    
    Parâmetros de Simulação:
        - Intervalo de processamento de eventos: 10.0s
        - Tempo de simulação de tráfego: 10.0s
        - Modo verboso: False (logs reduzidos)
    
    Fluxo de Execução:
        1. **Inicialização**:
           - Cria mundo com configurações especificadas
           - Identifica localizações de stores para veículos
           - Cria 3 veículos com capacidades idênticas
           - Cria event agent com veículos registados
           - Cria world agent com o mundo
           - Cria warehouse de teste
        
        2. **Arranque**:
           - Inicia world agent primeiro (dependência)
           - Inicia veículos sequencialmente
           - Inicia warehouse de teste
           - Inicia event agent (coordenador)
        
        3. **Execução Contínua**:
           - Loop assíncrono aguarda interrupção
           - Utilizador pode parar com Ctrl+C
        
        4. **Encerramento**:
           - Para todos os agentes graciosamente
           - Limpa recursos e conexões XMPP
    
    Raises:
        ValueError: Se o mundo não tiver warehouses ou stores suficientes.
        KeyboardInterrupt: Capturada para encerramento limpo.
    
    Examples:
        >>> # Executar teste completo
        >>> asyncio.run(main())
        
        # Output esperado:
        ======================================================================
        TESTE DO EVENT-DRIVEN AGENT COM WORLD AGENT
        ======================================================================
        
        🌍 Criando o mundo...
        ✓ Mundo criado: 10x10
        ✓ Nós no grafo: 100
        ✓ Arestas no grafo: 180
        
        🚚 Criando veículo...
           Localização inicial: 42
           Capacidade: 1000 kg
           Combustível máximo: 100 L
        
        ⚙️ Criando Event Agent...
        🌍 Criando World Agent...
        📦 Criando Warehouse de teste...
        
        🚀 Iniciando agentes...
        [SISTEMA] ✓ Sistema de teste iniciado!
        [SISTEMA] 🎯 Event Agent processando a cada 10.0s
        [SISTEMA] ⌨️  Pressione Ctrl+C para parar
    
    Note:
        Esta função requer que o servidor XMPP (Openfire/Prosody) esteja em execução
        e acessível em localhost. As credenciais dos agentes devem estar previamente
        configuradas no servidor.
    
    Warning:
        A função executa indefinidamente até receber KeyboardInterrupt (Ctrl+C).
        Certifique-se de parar a execução adequadamente para evitar agentes órfãos.
    
    See Also:
        EventDrivenAgent: Agente coordenador de eventos.
        Veiculo: Agente de veículo móvel.
        WorldAgent: Agente de simulação de tráfego.
        TestWarehouseAgent: Agente de teste de armazém.
        World: Classe de geração de mundo.
    """
    import sys
    import os
    
    # Adicionar diretório pai ao path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from veiculos.veiculos import Veiculo
    from veiculos.test_vehicle_agent import TestWarehouseAgent
    from world.world import World
    from supplier import Supplier
    from store import Store
    from warehouse import Warehouse
    from Eventos.gui_visualizer import start_gui
    # Configurações dos agentes
    EVENT_AGENT_JID = "event_agent@localhost"
    EVENT_AGENT_PASSWORD = "event123"
    WORLD_AGENT_JID = "world@localhost"
    WORLD_AGENT_PASSWORD = "password"
    WAREHOUSE_JID = "warehouse1_test@localhost"
    WAREHOUSE_PASSWORD = "warehouse123"
    WAREHOUSE1_JID = "warehouse2_test@localhost"
    WAREHOUSE1_PASSWORD = "warehouse234"
    STORE_JID = "store1_test@localhost"
    STORE_PASSWORD = "store123"
    STORE_JID_2 = "store2_test@localhost"
    STORE_PASSWORD_2 = "store234"
    SUPLIER_JID = "supplier1_test@localhost"
    SUPLIER_PASSWORD = "supplier123"
    SUPLIER_JID_2 = "supplier2_test@localhost"
    SUPLIER_PASSWORD_2 = "supplier234"
    VEHICLE_JID = "vehicle1@localhost"
    VEHICLE_PASSWORD = "vehicle123"
    VEHICLE_JID_2 = "vehicle2@localhost"
    VEHICLE_PASSWORD_2 = "vehicle234"
    VEHICLE_JID_3 = "vehicle3@localhost"
    VEHICLE_PASSWORD_3 = "vehicle345"
    
    print("="*70)
    print("TESTE DO EVENT-DRIVEN AGENT COM WORLD AGENT E GUI")
    print("="*70)
    
    # Criar o mundo
    print("\n🌍 Criando o mundo...")
    world = World(
        width=5,
        height=5,
        mode="different", 
        max_cost=4, 
        gas_stations=0, 
        warehouses=1,
        suppliers=1, 
        stores=1, 
        highway=True,
        traffic_probability=0.5,
        traffic_spread_probability=0.8,
        traffic_interval=2,
        untraffic_probability=0.4
    )
    
    import matplotlib.pyplot as plt
    #world.plot_graph()
    
    print(f"✓ Mundo criado: {world.width}x{world.height}")
    print(f"✓ Nós no grafo: {len(world.graph.nodes)}")
    print(f"✓ Arestas no grafo: {len(world.graph.edges)}")
    
    # Identificar uma localização inicial para o veículo (primeiro store)
    store_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'store') and node.store:
            store_locations.append(node_id)
    

    warehouse_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'warehouse') and node.warehouse:
            warehouse_locations.append(node_id)

    suplier_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'supplier') and node.supplier:
            suplier_locations.append(node_id)
    if not store_locations:
        print("❌ ERRO: Não foram encontrados stores para localização inicial do veículo!")
        return
    
    
    all_contacts = [WAREHOUSE_JID, STORE_JID, SUPLIER_JID, VEHICLE_JID, VEHICLE_JID_2, VEHICLE_JID_3, WAREHOUSE1_JID, STORE_JID_2, SUPLIER_JID_2]
    # Criar o veículo
    vehicle = Veiculo(
        jid=VEHICLE_JID,
        password=VEHICLE_PASSWORD,
        max_fuel=100,
        capacity=1000,
        max_orders=10,
        map=world.graph,
        weight=1500,
        current_location=store_locations[0],
        event_agent_jid=EVENT_AGENT_JID,
        verbose=False
    )
    vehicle_2 = Veiculo(
        jid=VEHICLE_JID_2,
        password=VEHICLE_PASSWORD_2,
        max_fuel=100,
        capacity=1000,
        max_orders=10,
        map=world.graph,
        weight=1500,
        current_location=store_locations[0],
        event_agent_jid=EVENT_AGENT_JID,
        verbose=False
    )
    vehicle_3 = Veiculo(
        jid=VEHICLE_JID_3,
        password=VEHICLE_PASSWORD_3,
        max_fuel=100,
        capacity=1000,
        max_orders=10,
        map=world.graph,
        weight=1500,
        current_location=store_locations[0],
        event_agent_jid=EVENT_AGENT_JID,
        verbose=False
    )
    warehouse_1= Warehouse(
        jid=WAREHOUSE_JID,
        password=WAREHOUSE_PASSWORD,
        map=world.graph,
        node_id=warehouse_locations[0],
        contact_list=all_contacts
    )
    warehouse_2= Warehouse(
        jid=WAREHOUSE1_JID,
        password=WAREHOUSE1_PASSWORD,
        map=world.graph,
        node_id=warehouse_locations[0],
        contact_list=all_contacts
    )

    store_1= Store(
        jid=STORE_JID,
        password=STORE_PASSWORD,
        map=world.graph,
        node_id=store_locations[0],
        contact_list=[WAREHOUSE_JID],
        verbose=False
    )
    store_2= Store(
        jid=STORE_JID_2,
        password=STORE_PASSWORD_2,
        map=world.graph,
        node_id=store_locations[0],
        contact_list=[WAREHOUSE1_JID],
        verbose=False
    )
    
    supplier_1= Supplier(
        jid=SUPLIER_JID,
        password=SUPLIER_PASSWORD,
        map=world.graph,
        node_id=suplier_locations[0],
        contact_list=[WAREHOUSE_JID, VEHICLE_JID, VEHICLE_JID_2, VEHICLE_JID_3]
    )
    
    # Criar event agent com lista de veículos registrados e world agent
    print(f"\n⚙️ Criando Event Agent...")
    event_agent = EventDrivenAgent(
        jid=EVENT_AGENT_JID,
        password=EVENT_AGENT_PASSWORD,
        simulation_interval=10.0,
        registered_vehicles=[VEHICLE_JID, VEHICLE_JID_2, VEHICLE_JID_3],
        registered_warehouses=[WAREHOUSE_JID],
        registered_stores=[STORE_JID],
        registered_suppliers=[SUPLIER_JID],
        world_agent=WORLD_AGENT_JID,
        world_simulation_time=10.0,
        verbose=True
    )
    
    # Criar world agent com o world já instanciado
    print(f"\n🌍 Criando World Agent...")
    from world_agent import WorldAgent
    world_agent = WorldAgent(WORLD_AGENT_JID, WORLD_AGENT_PASSWORD, world=world)
    '''
    # Criar warehouse de teste
    print(f"\n📦 Criando Warehouse de teste...")
    try:
        warehouse = TestWarehouseAgent(
            jid=WAREHOUSE_JID,
            password=WAREHOUSE_PASSWORD,
            vehicle_jids=[VEHICLE_JID, VEHICLE_JID_2, VEHICLE_JID_3],
            world=world
        )
    except ValueError as e:
        print(f"\n❌ ERRO: {e}")
        print("Certifique-se de que o mundo tem warehouses e stores suficientes!")
        return'''
    
    print("\n" + "="*70)
    print(f"Event Agent JID: {EVENT_AGENT_JID}")
    print(f"Warehouse JID: {WAREHOUSE_JID}")
    print(f"Vehicle JID: {VEHICLE_JID}")
    print("="*70)
    
    # Iniciar todos os agentes
    print("\n🚀 Iniciando agentes...")
    
    # Iniciar world agent primeiro
    print(f"🌍 Iniciando World Agent...")
    await world_agent.start()
    print(f"✓ World Agent iniciado: {WORLD_AGENT_JID}")
    
    await vehicle.start()
    print(f"✓ Veículo iniciado: {VEHICLE_JID}")

    await vehicle_2.start()
    print(f"✓ Veículo iniciado: {VEHICLE_JID_2}")
    
    await vehicle_3.start()
    print(f"✓ Veículo iniciado: {VEHICLE_JID_3}")
    
    await warehouse_1.start()
    print(f"✓ Warehouse iniciado: {WAREHOUSE_JID}")

    await supplier_1.start()
    print(f"✓ Supplier iniciado: {SUPLIER_JID}")

    await store_1.start()
    print(f"✓ Store iniciado: {STORE_JID}")

    await event_agent.start(auto_register=True)
    print(f"✓ Event Agent iniciado: {EVENT_AGENT_JID}")

    # Iniciar GUI Visualizer
    print(f"\n🖥️ Iniciando GUI Visualizer...")
    gui_thread = start_gui(
        world=world,
        event_agent=event_agent,
        vehicles=[vehicle, vehicle_2, vehicle_3],
        warehouses=[warehouse_1],
        stores=[store_1],
        suppliers=[supplier_1]
    )
    print(f"✓ GUI iniciada em thread separada")
    
    print(f"\n[SISTEMA] ✓ Sistema de teste iniciado!")
    print(f"[SISTEMA] 🎯 Event Agent processando a cada {event_agent.simulation_interval}s")
    print(f"[SISTEMA] 🚦 Event Agent solicitando simulação de tráfego ao World Agent")
    print(f"[SISTEMA] 🖥️ GUI disponível para visualização em tempo real")
    print(f"[SISTEMA] 📦 Enviando ordens aleatórias a cada 5 segundos...")
    print(f"[SISTEMA] ⌨️  Pressione Ctrl+C para parar\n")
    
    try:
        # Manter os agentes rodando
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[SISTEMA] Parando agentes...")
    finally:
        await event_agent.stop()
        await warehouse_1.stop()
        await supplier_1.stop()
        await store_1.stop()
        await vehicle.stop()
        await vehicle_2.stop()
        await vehicle_3.stop()
        await world_agent.stop()
        print("[SISTEMA] ✓ Agentes parados!")



if __name__ == "__main__":
    """
    Ponto de entrada do script de teste do Event-Driven Agent.
    
    Este bloco de documentação fornece informação completa sobre o propósito,
    funcionamento e utilização do script de teste. Serve como guia de referência
    para programadores que pretendam compreender ou modificar o sistema.
    
    Descrição Geral:
        Script de teste e demonstração das capacidades do Event-Driven Agent
        integrado com múltiplos agentes num ambiente de simulação de cadeia de
        abastecimento. Demonstra interacções complexas entre veículos, armazéns,
        lojas e simulação de tráfego dinâmico.
    
    Características do Teste:
        - **Mundo Realista**: Grafo 10x10 com tráfego probabilístico
        - **Múltiplos Veículos**: 3 veículos competindo por entregas
        - **Ordens Dinâmicas**: Warehouse envia ordens aleatórias periodicamente
        - **Tráfego Simulado**: World agent actualiza condições de tráfego
        - **Processamento Temporal**: Event agent coordena eventos cronologicamente
        - **Comunicação XMPP**: Sistema multi-agente distribuído
    
    Agentes Criados no Teste:
        1. **EventDrivenAgent** (event_agent@localhost):
           - Coordenador central de eventos
           - Gere heap de eventos por tempo
           - Notifica agentes sobre ocorrências
           - Solicita simulações de tráfego
        
        2. **WorldAgent** (world@localhost):
           - Simula condições de tráfego
           - Gera eventos de alteração de arestas
           - Responde a pedidos de simulação
        
        3. **Veículos** (vehicle1/2/3@localhost):
           - Recebem ordens de armazéns
           - Calculam rotas optimizadas
           - Enviam eventos de chegada (arrival)
           - Actualizam mapas com informação de tráfego
        
        4. **TestWarehouseAgent** (warehouse_test@localhost):
           - Simula armazém enviando ordens
           - Aceita 80% das propostas de veículos
           - Gera eventos de teste (arrival/transit)
    
    Fluxo de Teste Detalhado:
        **Fase 1 - Inicialização (0-5s)**:
            1. Event agent envia sinal inicial fictício aos veículos
            2. Veículos activam seus behaviours de recepção
            3. Event agent solicita primeira simulação de tráfego
            4. World agent processa e retorna eventos de trânsito
        
        **Fase 2 - Operação Normal (5s+)**:
            1. Warehouse envia ordens a veículos (a cada 5s)
            2. Veículos calculam rotas e propõem entregas
            3. Warehouse aceita propostas (80%)
            4. Veículos confirmam e planeiam rotas
            5. Veículos enviam eventos de arrival ao event agent
            6. Event agent processa eventos a cada 10s
            7. World agent actualiza tráfego continuamente
        
        **Fase 3 - Processamento de Eventos**:
            1. Event agent colecta eventos de arrival
            2. Agrupa arrivals do mesmo momento
            3. Processa eventos de trânsito
            4. Notifica todos os veículos
            5. Veículos actualizam mapas e recalculam rotas
        
        **Fase 4 - Resimulação de Tráfego**:
            1. Último evento de trânsito é processado
            2. Event agent solicita nova simulação
            3. World agent gera novos eventos futuros
            4. Ciclo recomeça
    
    Eventos Testados:
        - **arrival**: Chegada de veículo a warehouse/store/gas_station
          - Enviado por veículos ao event agent
          - Agrupado por momento temporal
          - Distribuído a todos os veículos
        
        - **Transit**: Alteração de peso/consumo em aresta do grafo
          - Gerado pelo world agent
          - Enviado a veículos, warehouses e stores
          - Primeiro tem tempo real, subsequentes tempo 0
        
        - **updatesimulation**: Pedido de nova simulação de tráfego
          - Gerado automaticamente pelo event agent
          - Enviado ao world agent
          - Desencadeia nova simulação
    
    Configuração XMPP Necessária:
        - Servidor: localhost (Openfire/Prosody/ejabberd)
        - Porta: 5222 (padrão XMPP)
        - Contas criadas:
          * event_agent@localhost (senha: event123)
          * world@localhost (senha: password)
          * warehouse_test@localhost (senha: warehouse123)
          * vehicle1@localhost (senha: vehicle123)
          * vehicle2@localhost (senha: vehicle234)
          * vehicle3@localhost (senha: vehicle345)
    
    Estrutura de Dados Principais:
        - **event_heap**: Min heap ordenada por tempo
        - **transit_events**: Lista de eventos de trânsito activos
        - **arrival_events**: Buffer temporário para arrivals
        - **registered_vehicles**: Lista de JIDs de veículos
    
    Padrões de Mensagem XMPP:
        Todas as mensagens seguem formato JSON com metadados XMPP:
        
        ```python
        msg = Message(to=recipient_jid)
        msg.set_metadata("performative", "inform|request")
        msg.set_metadata("action", "simulate_traffic|event_notification")
        msg.body = json.dumps({...})
        ```
    
    Como Executar:
        1. **Iniciar Servidor XMPP**:
           ```bash
           # Openfire (Windows)
           openfire.exe start
           
           # Prosody (Linux)
           sudo systemctl start prosody
           ```
        
        2. **Criar Contas XMPP**:
           Aceder à interface admin do servidor e criar as 6 contas listadas acima.
        
        3. **Executar Script**:
           ```bash
           cd Eventos
           python event_agent.py
           ```
        
        4. **Observar Logs**:
           Monitorizar interacções entre agentes através dos prints.
        
        5. **Parar Execução**:
           Pressionar Ctrl+C para encerramento limpo.
    
    Registo de Veículos:
        Veículos são registados estaticamente no construtor do EventDrivenAgent.
        Para adicionar mais veículos:
        
        ```python
        # Criar novo veículo
        new_vehicle = Veiculo(
            jid="vehicle4@localhost",
            password="vehicle456",
            max_fuel=100,
            capacity=1000,
            max_orders=10,
            map=world.graph,
            weight=1500,
            current_location=initial_location,
            event_agent_jid=EVENT_AGENT_JID
        )
        
        # Adicionar à lista de registados
        event_agent = EventDrivenAgent(
            ...,
            registered_vehicles=[..., "vehicle4@localhost"],
            ...
        )
        ```
    
    Observações de Implementação:
        - **Min Heap**: Garante processamento em ordem temporal O(log n)
        - **Agrupamento de Arrivals**: Reduz overhead de comunicação
        - **Ajuste Temporal**: Evita simulação duplicada do mesmo intervalo
        - **Listas Separadas**: Transit events geridos independentemente
        - **Resimulação Automática**: Mantém dados de tráfego actualizados
    
    Limitações Conhecidas:
        - Apenas um evento de cada tempo é processado por ciclo
        - Eventos futuros na heap são descartados (design intencional)
        - Requer servidor XMPP local (não suporta servidores remotos)
        - Não persiste estado entre execuções
    
    Extensões Futuras Possíveis:
        - [ ] Persistência de eventos em base de dados
        - [ ] Interface web para visualização em tempo real
        - [ ] Métricas de desempenho e estatísticas
        - [ ] Suporte para múltiplos event agents (federação)
        - [ ] Replay de simulações a partir de logs
        - [ ] Integração com sistemas externos via REST API
    
    Troubleshooting:
        **Problema**: Agentes não se conectam
        **Solução**: Verificar se servidor XMPP está em execução e contas existem
        
        **Problema**: Heap vazia constantemente
        **Solução**: Verificar se veículos estão a enviar eventos correctamente
        
        **Problema**: Eventos não são processados
        **Solução**: Verificar simulation_interval e presence subscriptions
        
        **Problema**: Duplicação de eventos
        **Solução**: Verificar lógica de agrupamento e ajuste temporal
    
    Referências:
        - SPADE Framework: https://spade-mas.readthedocs.io/
        - XMPP Protocol: https://xmpp.org/
        - FIPA ACL: http://www.fipa.org/repository/aclspecs.html
        - Python heapq: https://docs.python.org/3/library/heapq.html
    
    Autores:
        Equipa de Desenvolvimento Supply Chain Optimization
    
    Licença:
        Consultar ficheiro LICENSE na raiz do projecto
    
    Versão:
        1.0.0 (2025)
    """
    
    asyncio.run(main())
