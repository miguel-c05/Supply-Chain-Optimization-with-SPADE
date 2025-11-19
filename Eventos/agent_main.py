async def main():
    """Main function for complete Event-Driven Agent system test execution.
    
    This test function demonstrates complete integration between EventDrivenAgent,
    vehicles, warehouses, stores, suppliers, and the world agent. It creates a realistic
    simulation environment with a procedurally generated world, multiple vehicles, and
    dynamic traffic and delivery events.
    
    Components Created:
        1. **World**: 5x5 graph with dynamic traffic, highways, and locations
        2. **World Agent**: Simulates traffic conditions and generates events
        3. **Event Agent**: Coordinates all simulation events
        4. **Vehicles (3x)**: Mobile agents that respond to orders and events
        5. **Warehouse(s)**: Warehouse agents for order management
        6. **Store(s)**: Store agents for delivery requests
        7. **Supplier(s)**: Supplier agents for supply coordination
    
    World Configuration:
        - Dimensions: 5x5 nodes
        - Mode: "different" (varied costs)
        - Maximum edge cost: 4
        - Warehouses: 1
        - Suppliers: 1
        - Stores: 1
        - Highway: Enabled
        - Traffic probability: 0.5
        - Spread probability: 0.8
        - Traffic interval: 2 seconds
        - Untraffic probability: 0.4
    
    Simulation Parameters:
        - Event processing interval: 10.0s
        - Traffic simulation time: 10.0s
        - Verbose mode: False (reduced logs)
    
    Execution Flow:
        1. **Initialization**:
           - Create world with specified configuration
           - Identify store locations for vehicles
           - Create 3 vehicles with identical capacities
           - Create event agent with registered vehicles
           - Create world agent with the world
           - Create warehouse, store, and supplier agents
        
        2. **Startup**:
           - Start world agent first (dependency)
           - Start vehicles sequentially
           - Start warehouse, store, and supplier agents
           - Start event agent (coordinator)
        
        3. **Continuous Execution**:
           - Asynchronous loop awaits interruption
           - User can stop with Ctrl+C
        
        4. **Shutdown**:
           - Stop all agents gracefully
           - Clean up resources and XMPP connections
    
    Raises:
        ValueError: If the world doesn't have sufficient warehouses or stores.
        KeyboardInterrupt: Caught for clean shutdown.
    
    Examples:
        >>> # Run complete test
        >>> asyncio.run(main())
        
        # Expected output:
        ======================================================================
        EVENT-DRIVEN AGENT WITH WORLD AGENT TEST
        ======================================================================
        
        🌍 Creating world...
        ✓ World created: 5x5
        ✓ Graph nodes: 25
        ✓ Graph edges: 40
        
        🚚 Creating vehicle...
           Initial location: 12
           Capacity: 1000 kg
           Maximum fuel: 100 L
        
        ⚙️ Creating Event Agent...
        🌍 Creating World Agent...
        📦 Creating Warehouse for testing...
        
        🚀 Starting agents...
        [SYSTEM] ✓ Test system started!
        [SYSTEM] 🎯 Event Agent processing every 10.0s
        [SYSTEM] ⌨️  Press Ctrl+C to stop
    
    Note:
        This function requires a running XMPP server (Openfire/Prosody) accessible
        at localhost. Agent credentials must be previously configured on the server.
    
    FIPA Compliance:
        Demonstrates a complete FIPA-compliant multi-agent system with:
        - Multiple interacting agents using FIPA ACL
        - Presence-based discovery (XMPP)
        - Request-response and inform protocols
        - Distributed event coordination
    
    Warning:
        The function executes indefinitely until receiving KeyboardInterrupt (Ctrl+C).
        Ensure proper shutdown to avoid orphan agents.
    
    See Also:
        EventDrivenAgent: Event coordinator agent.
        Veiculo: Mobile vehicle agent.
        WorldAgent: Traffic simulation agent.
        Warehouse: Warehouse management agent.
        Store: Store delivery agent.
        Supplier: Supply coordination agent.
        World: World generation class.
    """
    import sys
    import os
    
    # Add parent directory to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from veiculos.veiculos import Veiculo
    from veiculos.test_vehicle_agent import TestWarehouseAgent
    from world.world import World
    from supplier import Supplier
    from store import Store
    from warehouse import Warehouse
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
    print("TESTE DO EVENT-DRIVEN AGENT COM WORLD AGENT")
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
        verbose=False
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

    
    
    print(f"\n[SISTEMA] ✓ Sistema de teste iniciado!")
    print(f"[SISTEMA] 🎯 Event Agent processando a cada {event_agent.simulation_interval}s")
    print(f"[SISTEMA] 🚦 Event Agent solicitando simulação de tráfego ao World Agent")
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
