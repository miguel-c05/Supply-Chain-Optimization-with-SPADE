"""
Simulação principal do sistema de cadeia de abastecimento com SPADE.

Este módulo cria e inicializa todos os agentes necessários para a simulação
da cadeia de abastecimento, incluindo veículos, armazéns, lojas, fornecedores,
agente de eventos e agente do mundo. Utiliza configurações do ficheiro config.py.
"""

import asyncio
import sys
import os

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

# Importar configurações
import config


async def main():
    """
    Função principal que configura e executa a simulação.
    
    Workflow:
        1. Cria o mundo com as configurações
        2. Extrai localizações de warehouses, stores e suppliers
        3. Cria todos os agentes dinamicamente baseado nas quantidades do config
        4. Inicia os agentes pela ordem correta
        5. Mantém a simulação em execução
    """
    
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
    
    # ========================================
    # CRIAR O MUNDO
    # ========================================
    print("\n🌍 Criando o mundo...")
    world = World(
        width=config.WORLD_WIDTH,
        height=config.WORLD_HEIGHT,
        mode=config.WORLD_MODE,
        max_cost=config.WORLD_MAX_COST,
        gas_stations=config.WORLD_GAS_STATIONS,
        warehouses=config.WORLD_WAREHOUSES,
        suppliers=config.WORLD_SUPPLIERS,
        stores=config.WORLD_STORES,
        highway=config.WORLD_HIGHWAY,
        traffic_probability=config.WORLD_TRAFFIC_PROBABILITY,
        traffic_spread_probability=config.WORLD_TRAFFIC_SPREAD_PROBABILITY,
        traffic_interval=config.WORLD_TRAFFIC_INTERVAL,
        untraffic_probability=config.WORLD_UNTRAFFIC_PROBABILITY
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
    if len(store_locations) < config.NUM_STORES:
        print(f"⚠️ AVISO: Mundo tem apenas {len(store_locations)} stores, mas config pede {config.NUM_STORES}")
        print(f"   Ajustando para criar {len(store_locations)} stores")
        num_stores = len(store_locations)
    else:
        num_stores = config.NUM_STORES
    
    if len(warehouse_locations) < config.NUM_WAREHOUSES:
        print(f"⚠️ AVISO: Mundo tem apenas {len(warehouse_locations)} warehouses, mas config pede {config.NUM_WAREHOUSES}")
        print(f"   Ajustando para criar {len(warehouse_locations)} warehouses")
        num_warehouses = len(warehouse_locations)
    else:
        num_warehouses = config.NUM_WAREHOUSES
    
    if len(supplier_locations) < config.NUM_SUPPLIERS:
        print(f"⚠️ AVISO: Mundo tem apenas {len(supplier_locations)} suppliers, mas config pede {config.NUM_SUPPLIERS}")
        print(f"   Ajustando para criar {len(supplier_locations)} suppliers")
        num_suppliers = len(supplier_locations)
    else:
        num_suppliers = config.NUM_SUPPLIERS
    
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
    print(f"  - Veículos a criar: {config.NUM_VEHICLES}")
    
    # ========================================
    # GERAR JIDs E PASSWORDS DINAMICAMENTE
    # ========================================
    vehicle_configs = []
    for i in range(1, config.NUM_VEHICLES + 1):
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
    print(f"\n🚗 Criando {config.NUM_VEHICLES} veículos...")
    vehicles = []
    for i, v_config in enumerate(vehicle_configs):
        # Distribuir veículos entre as localizações de stores disponíveis
        initial_location = store_locations[i % len(store_locations)]
        
        vehicle = Veiculo(
            jid=v_config['jid'],
            password=v_config['password'],
            max_fuel=config.VEHICLE_MAX_FUEL,
            capacity=config.VEHICLE_CAPACITY,
            max_orders=config.VEHICLE_MAX_ORDERS,
            map=world.graph,
            weight=config.VEHICLE_WEIGHT,
            current_location=initial_location,
            event_agent_jid=EVENT_AGENT_JID,
            verbose=False
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
            verbose=False
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
        simulation_interval=config.EVENT_AGENT_SIMULATION_INTERVAL,
        registered_vehicles=[v['jid'] for v in vehicle_configs],
        registered_warehouses=[w['jid'] for w in warehouse_configs],
        registered_stores=[s['jid'] for s in store_configs],
        registered_suppliers=[sup['jid'] for sup in supplier_configs],
        world_agent=WORLD_AGENT_JID,
        world_simulation_time=config.EVENT_AGENT_WORLD_SIMULATION_TIME,
        verbose=False
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
