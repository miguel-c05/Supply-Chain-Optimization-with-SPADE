if __name__ == "__main__":
    from world.world import World
    import random
    
    # Criar o mundo com 3 warehouses e 4 lojas
    print("Criando o mundo...")
    w = World(
        width=8,
        height=8,
        mode="different", 
        max_cost=4, 
        gas_stations=2, 
        warehouses=5,
        suppliers=2, 
        stores=6, 
        highway=True,
        traffic_probability=0.3,
        traffic_spread_probability=0.7,
        traffic_interval=3,
        untraffic_probability=0.4
    )
    graph = w.graph
    w.tick()  # Atualizar o mundo uma vez para gerar o grafo
    # Obter as localizações dos warehouses e stores do mundo
    print("\nIdentificando warehouses e stores no mapa...")
    warehouse_locations = []
    store_locations = []
    
    # Procurar por warehouses e stores nos nós do grafo
    for node_id, node in graph.nodes.items():
        if hasattr(node, 'warehouse') and node.warehouse:
            warehouse_locations.append(node_id)
        if hasattr(node, 'store') and node.store:
            store_locations.append(node_id)
    
    print(f"Warehouses encontrados: {warehouse_locations}")
    print(f"Stores encontrados: {store_locations}")
    
    if not warehouse_locations or not store_locations:
        print("ERRO: Não foram encontrados warehouses ou stores suficientes!")
        exit(1)
    
    # Criar 6 ordens de teste
    print("\nCriando 6 ordens de teste...")
    orders = []
    products = ["Electronics", "Food", "Clothing", "Books", "Toys", "Furniture"]
    
    for i in range(4):
        # Selecionar warehouse e store aleatoriamente
        warehouse = random.choice(warehouse_locations)
        store = random.choice(store_locations)
        quantity = random.randint(50, 800)
        
        order = Order(
            product=products[max(i % len(products), 0)],
            quantity=quantity,
            orderid=i + 1,
            sender=f"Warehouse{warehouse_locations.index(warehouse) + 1}",
            receiver=f"Store{store_locations.index(store) + 1}",
            tick_received=0
        )
        
        # Calcular tempo de entrega
        order.time_to_deliver(warehouse, store, graph, 0)
        orders.append(order)
        
        print(f"  Ordem {i+1}: {order.sender} ({warehouse}) -> {order.receiver} ({store})")
        print(f"    Produto: {order.product}, Quantidade: {quantity}")
        print(f"    Tempo: {order.deliver_time}, Combustível: {order.fuel}")
    
    # Configurar parâmetros do veículo
    start_location = store_locations[0]  # Começa no primeiro store
    capacity = 800 # Capacidade suficiente para múltiplas ordens
    max_fuel = 10  # Combustível máximo
    
    print(f"\nParâmetros do veículo:")
    print(f"  Localização inicial: {start_location}")
    print(f"  Capacidade: {capacity}")
    print(f"  Combustível máximo: {max_fuel}")
    
    # Executar o algoritmo A*
    print("\nExecutando algoritmo A*...")
    path, total_cost, root = A_star_task_algorithm(graph, start_location, orders, capacity, max_fuel)
    
    # Mostrar resultados
    if path is not None:
        print(f"\n Solução encontrada!")
        print(f"  Caminho: {path}")
        print(f"  Custo total: {total_cost}")
        print(f"  Número de passos: {len(path)}")
        print(f"\nSequência de visitas:")
        for idx, location in enumerate(path):
            print(f"  {idx}. Localização {location}")
    else:
        print("\n Nenhuma solução encontrada!")
        print(f"  Custo: {total_cost}")
    
    # Plotar a árvore de pesquisa (só gera imagem se < 1000 nós)
    root.plot_tree("search_tree.png")
    w.plot_graph()