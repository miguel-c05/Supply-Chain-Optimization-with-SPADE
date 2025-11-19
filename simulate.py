"""
Simulação principal do sistema de cadeia de abastecimento com SPADE.

Este módulo cria e inicializa todos os agentes necessários para a simulação
da cadeia de abastecimento, incluindo veículos, armazéns, lojas, fornecedores,
agente de eventos e agente do mundo. Utiliza configurações do ficheiro config.py.
"""

import asyncio
import sys
import os
import argparse

# Adicionar diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importar classes de agentes
from veiculos.veiculos import Veiculo
from warehouse import Warehouse
from supplier import Supplier
from store import Store
from Eventos.event_agent import EventDrivenAgent
from world_agent import WorldAgent
from world.world import World

# Importar configurações e logging
import config
from logger_utils import initialize_loggers


def parse_arguments():
    """
    Parse command line arguments for simulation configuration.
    
    All arguments are optional. If not provided, values from config.py are used as defaults.
    This allows flexible simulation configuration either through config.py or command line.
    
    Returns:
        argparse.Namespace: Parsed arguments with all simulation configuration parameters.
    
    Configuration Categories:
        - Agent Quantities: Number of vehicles, warehouses, stores, suppliers
        - World Configuration: Grid dimensions, mode, traffic parameters
        - Vehicle Configuration: Capacity, fuel, weight
        - Warehouse Configuration: Product capacity, resupply threshold
        - Store Configuration: Buy quantity, frequency, probability
        - Event Agent Configuration: Simulation intervals
    
    Example:
        python simulate.py --num-vehicles 5 --world-width 10 --world-height 10
        python simulate.py --world-mode uniform --num-stores 3
        python simulate.py  # Uses all defaults from config.py
    """
    parser = argparse.ArgumentParser(
        description='Supply Chain Optimization Simulation with SPADE',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Agent Quantities
    agent_group = parser.add_argument_group('Agent Quantities')
    agent_group.add_argument('--num-vehicles', type=int, default=config.NUM_VEHICLES,
                            help='Number of vehicles in the simulation')
    agent_group.add_argument('--num-warehouses', type=int, default=config.NUM_WAREHOUSES,
                            help='Number of warehouses in the simulation')
    agent_group.add_argument('--num-stores', type=int, default=config.NUM_STORES,
                            help='Number of stores in the simulation')
    agent_group.add_argument('--num-suppliers', type=int, default=config.NUM_SUPPLIERS,
                            help='Number of suppliers in the simulation')
    
    # World Configuration
    world_group = parser.add_argument_group('World Configuration')
    world_group.add_argument('--world-width', type=int, default=config.WORLD_WIDTH,
                            help='Width of the world grid')
    world_group.add_argument('--world-height', type=int, default=config.WORLD_HEIGHT,
                            help='Height of the world grid')
    world_group.add_argument('--world-mode', type=str, default=config.WORLD_MODE,
                            choices=['uniform', 'different'],
                            help='World generation mode')
    world_group.add_argument('--world-max-cost', type=int, default=config.WORLD_MAX_COST,
                            help='Maximum edge cost in the world graph')
    world_group.add_argument('--world-gas-stations', type=int, default=config.WORLD_GAS_STATIONS,
                            help='Number of gas stations in the world')
    world_group.add_argument('--world-highway', type=bool, default=config.WORLD_HIGHWAY,
                            help='Enable highways in the world')
    world_group.add_argument('--world-traffic-probability', type=float, default=config.WORLD_TRAFFIC_PROBABILITY,
                            help='Probability of traffic occurring')
    world_group.add_argument('--world-traffic-spread-probability', type=float, default=config.WORLD_TRAFFIC_SPREAD_PROBABILITY,
                            help='Probability of traffic spreading to adjacent edges')
    world_group.add_argument('--world-traffic-interval', type=int, default=config.WORLD_TRAFFIC_INTERVAL,
                            help='Interval for traffic updates')
    world_group.add_argument('--world-untraffic-probability', type=float, default=config.WORLD_UNTRAFFIC_PROBABILITY,
                            help='Probability of traffic clearing')
    
    # Vehicle Configuration
    vehicle_group = parser.add_argument_group('Vehicle Configuration')
    vehicle_group.add_argument('--vehicle-capacity', type=int, default=config.VEHICLE_CAPACITY,
                              help='Maximum cargo capacity of vehicles')
    vehicle_group.add_argument('--vehicle-max-fuel', type=int, default=config.VEHICLE_MAX_FUEL,
                              help='Maximum fuel capacity of vehicles')
    vehicle_group.add_argument('--vehicle-max-orders', type=int, default=config.VEHICLE_MAX_ORDERS,
                              help='Maximum number of orders per vehicle')
    vehicle_group.add_argument('--vehicle-weight', type=int, default=config.VEHICLE_WEIGHT,
                              help='Weight of the vehicle')
    
    # Warehouse Configuration
    warehouse_group = parser.add_argument_group('Warehouse Configuration')
    warehouse_group.add_argument('--warehouse-max-capacity', type=int, default=config.WAREHOUSE_MAX_PRODUCT_CAPACITY,
                                help='Maximum product capacity per warehouse')
    warehouse_group.add_argument('--warehouse-resupply-threshold', type=int, default=config.WAREHOUSE_RESUPPLY_THRESHOLD,
                                help='Inventory threshold to trigger resupply')
    
    # Store Configuration
    store_group = parser.add_argument_group('Store Configuration')
    store_group.add_argument('--store-max-buy-quantity', type=int, default=config.STORE_MAX_BUY_QUANTITY,
                            help='Maximum quantity stores can buy per order')
    store_group.add_argument('--store-buy-frequency', type=int, default=config.STORE_BUY_FREQUENCY,
                            help='Frequency of store buying cycles (seconds)')
    store_group.add_argument('--store-buy-probability', type=float, default=config.STORE_BUY_PROBABILITY,
                            help='Probability of store making a purchase')
    
    # Event Agent Configuration
    event_group = parser.add_argument_group('Event Agent Configuration')
    event_group.add_argument('--event-simulation-interval', type=float, default=config.EVENT_AGENT_SIMULATION_INTERVAL,
                            help='Interval for event agent simulation cycles (seconds)')
    event_group.add_argument('--event-world-simulation-time', type=float, default=config.EVENT_AGENT_WORLD_SIMULATION_TIME,
                            help='World simulation time per event cycle (seconds)')
    
    # Verbosity
    parser.add_argument('--verbose', action='store_true', default=False,
                       help='Enable verbose output from agents')
    
    return parser.parse_args()


async def main():
    """
    Função principal que configura e executa a simulação.
    
    Workflow:
        1. Parse command line arguments (or use config.py defaults)
        2. Cria o mundo com as configurações
        3. Extrai localizações de warehouses, stores e suppliers
        4. Cria todos os agentes dinamicamente baseado nas quantidades
        5. Inicia os agentes pela ordem correta
        6. Mantém a simulação em execução
    
    Configuration:
        All simulation parameters can be configured via command line arguments.
        If no arguments are provided, defaults from config.py are used.
    """
    
    # ========================================
    # PARSE ARGUMENTS
    # ========================================
    args = parse_arguments()
    
    # ========================================
    # INITIALIZE LOGGING SYSTEM
    # ========================================
    loggers = initialize_loggers()
    
    # ========================================
    # CONFIGURAÇÕES BASE
    # ========================================
    EVENT_AGENT_JID = "event_agent@localhost"
    EVENT_AGENT_PASSWORD = "event123"
    WORLD_AGENT_JID = "world@localhost"
    WORLD_AGENT_PASSWORD = "password"
    
    print("="*70)
    print("SIMULAÇÃO DO SISTEMA DE CADEIA DE ABASTECIMENTO")
    print("="*70)
    
    # Display configuration
    print("\n📋 Configuração da Simulação:")
    print(f"  Veículos: {args.num_vehicles}")
    print(f"  Warehouses: {args.num_warehouses}")
    print(f"  Stores: {args.num_stores}")
    print(f"  Suppliers: {args.num_suppliers}")
    print(f"  Mundo: {args.world_width}x{args.world_height} (modo: {args.world_mode})")
    print(f"  Verbose: {args.verbose}")
    
    # ========================================
    # CRIAR O MUNDO
    # ========================================
    print("\n🌍 Criando o mundo...")
    world = World(
        width=args.world_width,
        height=args.world_height,
        mode=args.world_mode,
        max_cost=args.world_max_cost,
        gas_stations=args.world_gas_stations,
        warehouses=args.num_warehouses,  # Use parsed value
        suppliers=args.num_suppliers,    # Use parsed value
        stores=args.num_stores,          # Use parsed value
        highway=args.world_highway,
        traffic_probability=args.world_traffic_probability,
        traffic_spread_probability=args.world_traffic_spread_probability,
        traffic_interval=args.world_traffic_interval,
        untraffic_probability=args.world_untraffic_probability
    )
    print(f"✓ Mundo criado: {world.width}x{world.height}")
    print(f"✓ Nós no grafo: {len(world.graph.nodes)}")
    print(f"✓ Arestas no grafo: {len(world.graph.edges)}")
    
    # ========================================
    # EXTRAIR LOCALIZAÇÕES
    # ========================================
    store_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'store') and node.store:
            store_locations.append(node_id)
    
    warehouse_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'warehouse') and node.warehouse:
            warehouse_locations.append(node_id)
    
    supplier_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'supplier') and node.supplier:
            supplier_locations.append(node_id)
    
    # Validar que temos localizações suficientes
    if len(store_locations) < args.num_stores:
        print(f"⚠️ AVISO: Mundo tem apenas {len(store_locations)} stores, mas config pede {args.num_stores}")
        print(f"   Ajustando para criar {len(store_locations)} stores")
        num_stores = len(store_locations)
    else:
        num_stores = args.num_stores
    
    if len(warehouse_locations) < args.num_warehouses:
        print(f"⚠️ AVISO: Mundo tem apenas {len(warehouse_locations)} warehouses, mas config pede {args.num_warehouses}")
        print(f"   Ajustando para criar {len(warehouse_locations)} warehouses")
        num_warehouses = len(warehouse_locations)
    else:
        num_warehouses = args.num_warehouses
    
    if len(supplier_locations) < args.num_suppliers:
        print(f"⚠️ AVISO: Mundo tem apenas {len(supplier_locations)} suppliers, mas config pede {args.num_suppliers}")
        print(f"   Ajustando para criar {len(supplier_locations)} suppliers")
        num_suppliers = len(supplier_locations)
    else:
        num_suppliers = args.num_suppliers
    
    if not store_locations:
        print("❌ ERRO: Não foram encontrados stores no mundo!")
        return
    
    if not warehouse_locations:
        print("❌ ERRO: Não foram encontrados warehouses no mundo!")
        return
    
    if not supplier_locations:
        print("❌ ERRO: Não foram encontrados suppliers no mundo!")
        return
    
    print(f"\n✓ Localizações encontradas:")
    print(f"  - Stores: {len(store_locations)} disponíveis → criando {num_stores}")
    print(f"  - Warehouses: {len(warehouse_locations)} disponíveis → criando {num_warehouses}")
    print(f"  - Suppliers: {len(supplier_locations)} disponíveis → criando {num_suppliers}")
    print(f"  - Veículos a criar: {args.num_vehicles}")
    
    # ========================================
    # GERAR JIDs E PASSWORDS DINAMICAMENTE
    # ========================================
    vehicle_configs = []
    for i in range(1, args.num_vehicles + 1):
        vehicle_configs.append({
            'jid': f"vehiclee{i}@localhost",
            'password': f"vehicle{100+i}{20+i}{3}"
        })
    
    warehouse_configs = []
    for i in range(1, num_warehouses + 1):
        warehouse_configs.append({
            'jid': f"warehousee{i}_test@localhost",
            'password': f"warehouse{100+i}{20+i}{3}"
        })
    
    store_configs = []
    for i in range(1, num_stores + 1):
        store_configs.append({
            'jid': f"storee{i}_test@localhost",
            'password': f"store{100+i}{20+i}{3}"
        })
    
    supplier_configs = []
    for i in range(1, num_suppliers + 1):
        supplier_configs.append({
            'jid': f"supplierr{i}_test@localhost",
            'password': f"supplier{100+i}{20+i}{3}"
        })
    
    # Lista de todos os contatos para subscrição
    all_contacts = []
    all_contacts.extend([v['jid'] for v in vehicle_configs])
    all_contacts.extend([w['jid'] for w in warehouse_configs])
    all_contacts.extend([s['jid'] for s in store_configs])
    all_contacts.extend([sup['jid'] for sup in supplier_configs])
    
    print(f"\n✓ Configurações de JIDs geradas:")
    print(f"  - Veículos: {[v['jid'] for v in vehicle_configs]}")
    print(f"  - Warehouses: {[w['jid'] for w in warehouse_configs]}")
    print(f"  - Stores: {[s['jid'] for s in store_configs]}")
    print(f"  - Suppliers: {[sup['jid'] for sup in supplier_configs]}")
    
    # ========================================
    # CRIAR VEÍCULOS DINAMICAMENTE
    # ========================================
    print(f"\n🚗 Criando {args.num_vehicles} veículos...")
    vehicles = []
    for i, v_config in enumerate(vehicle_configs):
        # Distribuir veículos entre as localizações de stores disponíveis
        initial_location = store_locations[i % len(store_locations)]
        
        vehicle = Veiculo(
            jid=v_config['jid'],
            password=v_config['password'],
            max_fuel=args.vehicle_max_fuel,
            capacity=args.vehicle_capacity,
            max_orders=args.vehicle_max_orders,
            map=world.graph,
            weight=args.vehicle_weight,
            current_location=initial_location,
            event_agent_jid=EVENT_AGENT_JID,
            verbose=args.verbose
        )
        vehicles.append(vehicle)
        print(f"  ✓ {v_config['jid']} (localização inicial: {initial_location})")
    
    # ========================================
    # CRIAR WAREHOUSES DINAMICAMENTE
    # ========================================
    print(f"\n📦 Criando {num_warehouses} warehouses...")
    warehouses = []
    for i, w_config in enumerate(warehouse_configs):
        warehouse = Warehouse(
            jid=w_config['jid'],
            password=w_config['password'],
            map=world.graph,
            node_id=warehouse_locations[i % len(warehouse_locations)],
            contact_list=all_contacts
        )
        warehouses.append(warehouse)
        print(f"  ✓ {w_config['jid']} (nó: {warehouse_locations[i % len(warehouse_locations)]})")
    
    # ========================================
    # CRIAR STORES DINAMICAMENTE
    # ========================================
    print(f"\n🏪 Criando {num_stores} stores...")
    stores = []
    for i, s_config in enumerate(store_configs):
        # Cada store contacta warehouses (pode ser customizado)
        store_contacts = [w['jid'] for w in warehouse_configs]
        
        store = Store(
            jid=s_config['jid'],
            password=s_config['password'],
            map=world.graph,
            node_id=store_locations[i % len(store_locations)],
            contact_list=store_contacts,
            verbose=args.verbose
        )
        stores.append(store)
        print(f"  ✓ {s_config['jid']} (nó: {store_locations[i % len(store_locations)]})")
    
    # ========================================
    # CRIAR SUPPLIERS DINAMICAMENTE
    # ========================================
    print(f"\n🏭 Criando {num_suppliers} suppliers...")
    suppliers = []
    for i, sup_config in enumerate(supplier_configs):
        # Suppliers contactam warehouses e veículos
        supplier_contacts = [w['jid'] for w in warehouse_configs] + [v['jid'] for v in vehicle_configs]
        
        supplier = Supplier(
            jid=sup_config['jid'],
            password=sup_config['password'],
            map=world.graph,
            node_id=supplier_locations[i % len(supplier_locations)],
            contact_list=supplier_contacts
        )
        suppliers.append(supplier)
        print(f"  ✓ {sup_config['jid']} (nó: {supplier_locations[i % len(supplier_locations)]})")
    
    # ========================================
    # CRIAR EVENT AGENT
    # ========================================
    print("\n⚙️ Criando Event Agent...")
    event_agent = EventDrivenAgent(
        jid=EVENT_AGENT_JID,
        password=EVENT_AGENT_PASSWORD,
        simulation_interval=args.event_simulation_interval,
        registered_vehicles=[v['jid'] for v in vehicle_configs],
        registered_warehouses=[w['jid'] for w in warehouse_configs],
        registered_stores=[s['jid'] for s in store_configs],
        registered_suppliers=[sup['jid'] for sup in supplier_configs],
        world_agent=WORLD_AGENT_JID,
        world_simulation_time=args.event_world_simulation_time,
        verbose=args.verbose
    )
    
    print(f"✓ Event Agent criado: {EVENT_AGENT_JID}")
    
    # ========================================
    # CRIAR WORLD AGENT
    # ========================================
    print("\n🌍 Criando World Agent...")
    world_agent = WorldAgent(WORLD_AGENT_JID, WORLD_AGENT_PASSWORD, world=world)
    
    print(f"✓ World Agent criado: {WORLD_AGENT_JID}")
    
    # ========================================
    # INICIAR TODOS OS AGENTES
    # ========================================
    print("\n" + "="*70)
    print("🚀 Iniciando agentes...")
    print("="*70)
    
    # Iniciar world agent primeiro
    print(f"\n🌍 Iniciando World Agent...")
    await world_agent.start(auto_register=True)
    print(f"✓ World Agent iniciado: {WORLD_AGENT_JID}")


    
    # Iniciar veículos
    print(f"\n🚗 Iniciando {len(vehicles)} veículos...")
    for vehicle in vehicles:
        await vehicle.start(auto_register=True)
        print(f"  ✓ {vehicle.jid}")
    
    # Iniciar warehouses
    print(f"\n📦 Iniciando {len(warehouses)} warehouses...")
    for warehouse in warehouses:
        await warehouse.start(auto_register=True)
        print(f"  ✓ {warehouse.jid}")
    
    # Iniciar suppliers
    print(f"\n🏭 Iniciando {len(suppliers)} suppliers...")
    for supplier in suppliers:
        await supplier.start(auto_register=True)
        print(f"  ✓ {supplier.jid}")
    
    # Iniciar stores
    print(f"\n🏪 Iniciando {len(stores)} stores...")
    for store in stores:
        await store.start(auto_register=True)
        print(f"  ✓ {store.jid}")
    
    # Iniciar event agent por último
    print(f"\n⚙️ Iniciando Event Agent...")
    await event_agent.start(auto_register=True)
    print(f"✓ Event Agent iniciado: {EVENT_AGENT_JID}")
    
    # ========================================
    # INFORMAÇÕES DO SISTEMA
    # ========================================
    print("\n" + "="*70)
    print("✅ SISTEMA INICIADO COM SUCESSO!")
    print("="*70)
    print(f"\n[SISTEMA] 🎯 Event Agent processando a cada {event_agent.simulation_interval}s")
    print(f"[SISTEMA] 🌍 Mundo: {world.width}x{world.height}")
    print(f"[SISTEMA] 🚗 Veículos: {len(vehicles)}")
    print(f"[SISTEMA] 📦 Warehouses: {len(warehouses)}")
    print(f"[SISTEMA] 🏪 Stores: {len(stores)}")
    print(f"[SISTEMA] 🏭 Suppliers: {len(suppliers)}")
    print(f"[SISTEMA] ⌨️  Pressione Ctrl+C para parar\n")
    
    # ========================================
    # MANTER SIMULAÇÃO EM EXECUÇÃO
    # ========================================
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[SISTEMA] 🛑 Parando agentes...")
    finally:
        # Parar todos os agentes na ordem inversa
        await event_agent.stop()
        
        for store in stores:
            await store.stop()
        
        for supplier in suppliers:
            await supplier.stop()
        
        for warehouse in warehouses:
            await warehouse.stop()
        
        for vehicle in vehicles:
            await vehicle.stop()
        
        await world_agent.stop()
        print("[SISTEMA] ✓ Todos os agentes parados!")


if __name__ == "__main__":
    """
    Ponto de entrada do script de simulação.
    
    Descrição:
        Este script configura e executa uma simulação completa da cadeia de
        abastecimento com múltiplos agentes SPADE. Todos os parâmetros são
        lidos do ficheiro config.py.
    
    Requisitos:
        - Servidor XMPP em execução (localhost:5222)
        - Contas XMPP criadas para todos os agentes
        - Ficheiro config.py com todas as configurações necessárias
    
    Como executar:
        1. Iniciar servidor XMPP (Openfire/Prosody/ejabberd)
        2. Criar as contas XMPP necessárias
        3. Configurar o ficheiro config.py
        4. Executar: python simulate.py
        5. Para parar: Ctrl+C
    """
    asyncio.run(main())
