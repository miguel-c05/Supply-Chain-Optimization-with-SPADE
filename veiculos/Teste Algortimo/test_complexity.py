"""
Script para testar a complexidade temporal do algoritmo A* de roteamento
Testa diversas configurações e gera um CSV com métricas detalhadas
"""

import sys
import os
import time
import csv
from datetime import datetime
import random

# Adicionar o diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from world.world import World
from world.graph import Graph
from algoritmo_tarefas import (
    Order, A_star_task_algorithm, clear_dijkstra_cache, _dijkstra_cache
)


def count_unique_trips(path):
    """
    Conta o número de viagens únicas (transições entre localizações diferentes)
    """
    if not path or len(path) <= 1:
        return 0
    
    trips = 0
    for i in range(len(path) - 1):
        if path[i] != path[i + 1]:
            trips += 1
    return trips


def calculate_total_fuel(graph, path):
    """
    Calcula o combustível total consumido no caminho
    """
    if not path or len(path) <= 1:
        return 0.0
    
    total_fuel = 0.0
    for i in range(len(path) - 1):
        route, fuel, time = graph.djikstra(path[i], path[i + 1])
        total_fuel += fuel
    
    return total_fuel


def generate_orders(world, num_orders, quantity_range=(1, 5)):
    """
    Gera ordens aleatórias entre warehouses e stores
    """
    # Obter localizações de warehouses e stores
    warehouse_locations = []
    store_locations = []
    
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'warehouse') and node.warehouse:
            warehouse_locations.append(node_id)
        if hasattr(node, 'store') and node.store:
            store_locations.append(node_id)
    
    if not warehouse_locations or not store_locations:
        return None, None, None
    
    orders = []
    products = ["Electronics", "Food", "Clothing", "Books", "Toys", "Furniture", 
                "Medicine", "Hardware", "Sports", "Beauty"]
    
    for i in range(num_orders):
        warehouse = random.choice(warehouse_locations)
        store = random.choice(store_locations)
        quantity = random.randint(quantity_range[0], quantity_range[1])
        
        order = Order(
            product=products[i % len(products)],
            quantity=quantity,
            orderid=i + 1,
            sender=f"Warehouse{warehouse}",
            receiver=f"Store{store}",
            tick_received=0
        )
        
        # Calcular tempo de entrega
        path, fuel, time_delivery = world.graph.djikstra(warehouse, store)
        order.sender_location = warehouse
        order.receiver_location = store
        order.deliver_time = time_delivery
        order.fuel = fuel
        order.route = path
        
        orders.append(order)
    
    return orders, warehouse_locations, store_locations


def run_test(config, run_number):
    """
    Executa um teste com uma configuração específica
    
    Args:
        config: dict com parâmetros do teste
        run_number: número da execução (para repetições)
    
    Returns:
        dict com métricas do teste
    """
    try:
        # Criar mundo
        world = World(
            width=config['width'],
            height=config['height'],
            mode="different",
            max_cost=4,
            gas_stations=config['gas_stations'],
            warehouses=config['warehouses'],
            suppliers=2,
            stores=config['stores'],
            highway=config['highway'],
            traffic_probability=0.3,
            traffic_spread_probability=0.7,
            traffic_interval=3,
            untraffic_probability=0.4
        )
        
        # Gerar ordens
        orders, warehouse_locations, store_locations = generate_orders(
            world, 
            config['num_orders'],
            config['quantity_range']
        )
        
        if not orders or not warehouse_locations or not store_locations:
            return None
        
        # Configurar veículo
        start_location = warehouse_locations[0]
        
        # Limpar cache antes do teste
        clear_dijkstra_cache()
        
        # Executar algoritmo e medir tempo
        start_time = time.time()
        
        # Capturar print de nós criados (redirecionando stdout temporariamente)
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            path, total_cost, root = A_star_task_algorithm(
                world.graph,
                start_location,
                orders,
                config['capacity'],
                config['max_fuel']
            )
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Extrair número de nós do output
        output = f.getvalue()
        nodes_created = 0
        for line in output.split('\n'):
            if 'Nós criados:' in line:
                try:
                    nodes_created = int(line.split(':')[1].strip())
                except:
                    pass
        
        # Calcular métricas
        if path is not None:
            unique_trips = count_unique_trips(path)
            total_fuel = calculate_total_fuel(world.graph, path)
            path_length = len(path)
            success = True
        else:
            unique_trips = 0
            total_fuel = 0.0
            path_length = 0
            success = False
        
        # Métricas adicionais
        total_quantity = sum(order.quantity for order in orders)
        avg_quantity = total_quantity / len(orders) if orders else 0
        
        # Calcular utilização de capacidade
        capacity_utilization = (total_quantity / config['capacity']) * 100 if config['capacity'] > 0 else 0
        
        # Calcular utilização de fuel
        fuel_utilization = (total_fuel / config['max_fuel']) * 100 if config['max_fuel'] > 0 else 0
        
        return {
            'run_number': run_number,
            'timestamp': datetime.now().isoformat(),
            'success': success,
            'execution_time_seconds': round(execution_time, 4),
            'world_size': config['width'] * config['height'],
            'width': config['width'],
            'height': config['height'],
            'num_warehouses': config['warehouses'],
            'num_stores': config['stores'],
            'num_orders': config['num_orders'],
            'vehicle_capacity': config['capacity'],
            'vehicle_max_fuel': config['max_fuel'],
            'quantity_min': config['quantity_range'][0],
            'quantity_max': config['quantity_range'][1],
            'total_quantity': total_quantity,
            'avg_quantity_per_order': round(avg_quantity, 2),
            'highway': config['highway'],
            'nodes_created': nodes_created,
            'cache_routes': len(_dijkstra_cache),
            'path_length': path_length,
            'unique_trips': unique_trips,
            'total_cost': round(total_cost, 2) if success else 0,
            'total_fuel_consumed': round(total_fuel, 2),
            'capacity_utilization_percent': round(capacity_utilization, 2),
            'fuel_utilization_percent': round(fuel_utilization, 2),
            'cost_per_order': round(total_cost / config['num_orders'], 2) if success and config['num_orders'] > 0 else 0,
            'fuel_per_order': round(total_fuel / config['num_orders'], 2) if config['num_orders'] > 0 else 0,
        }
        
    except Exception as e:
        print(f"Erro no teste (run {run_number}): {e}")
        import traceback
        traceback.print_exc()
        return None


def calculate_capacity_and_fuel(num_orders, capacity_multiplier, fuel_multiplier, 
                                 quantity_range=(1, 5)):
    """
    Calcula a capacidade e fuel com base nos multiplicadores
    
    Args:
        num_orders: número de ordens
        capacity_multiplier: multiplicador para capacidade (1.5, 2, ou 3)
        fuel_multiplier: multiplicador para fuel (0.3, 0.8, 1, ou 5)
        quantity_range: range de quantidades por ordem
        
    Returns:
        tuple (capacity, max_fuel)
    """
    # Gerar ordens temporárias para calcular avg e max quantity
    quantities = [random.randint(quantity_range[0], quantity_range[1]) 
                  for _ in range(num_orders)]
    avg_quantity = sum(quantities) / len(quantities) if quantities else 0
    max_quantity = max(quantities) if quantities else quantity_range[1]
    
    # Calcular capacidade: max(multiplier * avg_quantity, max_quantity)
    capacity = max(int(capacity_multiplier * avg_quantity), max_quantity)
    
    # Fuel base estimado (baseado no tamanho do mapa e número de ordens)
    # Usamos uma heurística: cada ordem pode precisar atravessar metade do mapa
    base_fuel = 100  # fuel base
    max_fuel = int(base_fuel * fuel_multiplier)
    
    return capacity, max_fuel


def main():
    """
    Função principal que define todas as configurações de teste e executa
    Testa todas as combinações de:
    - Orders: 1-10
    - Map sizes: 5x5, 10x10, 15x15
    - Stores + Warehouses: 5, 8
    - Fuel multipliers: 0.3, 0.8, 1, 5
    - Capacity multipliers: 1.5, 2, 3
    """
    print("=" * 80)
    print("TESTE EXAUSTIVO DE COMPLEXIDADE TEMPORAL DO ALGORITMO A*")
    print("=" * 80)
    
    # Definir parâmetros de teste
    order_counts = list(range(1, 11))  # 1 a 10 ordens
    map_sizes = [(5, 5), (10, 10), (15, 15)]  # Tamanhos de mapa
    location_counts = [5, 8]  # Total de stores + warehouses
    fuel_multipliers = [0.3, 0.8, 1, 5]  # Multiplicadores de fuel
    capacity_multipliers = [1.5, 2, 3]  # Multiplicadores de capacidade
    quantity_range = (1, 5)  # Range fixo de quantidades
    
    # Gerar todas as configurações
    test_configs = []
    config_id = 0
    
    for map_size in map_sizes:
        width, height = map_size
        
        for location_count in location_counts:
            # Distribuir entre warehouses e stores (aproximadamente igual)
            warehouses = location_count // 2
            stores = location_count - warehouses
            
            # Calcular gas_stations baseado no tamanho do mapa
            gas_stations = max(1, (width * height) // 30)
            
            for num_orders in order_counts:
                for fuel_mult in fuel_multipliers:
                    for cap_mult in capacity_multipliers:
                        # Calcular capacidade e fuel
                        capacity, max_fuel = calculate_capacity_and_fuel(
                            num_orders, cap_mult, fuel_mult, quantity_range
                        )
                        
                        config_id += 1
                        config_name = (f"map{width}x{height}_loc{location_count}_"
                                     f"ord{num_orders}_fuel{fuel_mult}_cap{cap_mult}")
                        
                        test_configs.append({
                            'name': config_name,
                            'config_id': config_id,
                            'width': width,
                            'height': height,
                            'warehouses': warehouses,
                            'stores': stores,
                            'gas_stations': gas_stations,
                            'num_orders': num_orders,
                            'capacity': capacity,
                            'max_fuel': max_fuel,
                            'quantity_range': quantity_range,
                            'highway': True if width * height >= 100 else False,
                            'fuel_multiplier': fuel_mult,
                            'capacity_multiplier': cap_mult,
                        })
    
    print(f"\nTotal de configurações diferentes: {len(test_configs)}")
    print(f"Cada configuração será executada 10 vezes")
    print(f"Total de testes: {len(test_configs) * 10}")
    
    # Nome do arquivo CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"exhaustive_complexity_test_{timestamp}.csv"
    
    # Cabeçalhos do CSV
    fieldnames = [
        'config_id', 'config_name', 'run_number', 'timestamp', 'success',
        'execution_time_seconds', 'world_size', 'width', 'height',
        'num_warehouses', 'num_stores', 'num_gas_stations', 'num_orders',
        'vehicle_capacity', 'vehicle_max_fuel', 'capacity_multiplier', 'fuel_multiplier',
        'quantity_min', 'quantity_max', 'total_quantity', 'avg_quantity_per_order',
        'highway', 'nodes_created', 'cache_routes',
        'path_length', 'unique_trips', 'total_cost', 'total_fuel_consumed',
        'capacity_utilization_percent', 'fuel_utilization_percent',
        'cost_per_order', 'fuel_per_order'
    ]
    
    # Abrir arquivo CSV
    with open(csv_filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        total_tests = len(test_configs) * 10
        current_test = 0
        
        # Executar cada configuração 10 vezes
        for config in test_configs:
            print(f"\n{'='*80}")
            print(f"Configuração {config['config_id']}/{len(test_configs)}: {config['name']}")
            print(f"  Mapa: {config['width']}x{config['height']}, "
                  f"Warehouses: {config['warehouses']}, Stores: {config['stores']}, "
                  f"Orders: {config['num_orders']}")
            print(f"  Capacidade: {config['capacity']} (mult: {config['capacity_multiplier']}), "
                  f"Fuel: {config['max_fuel']} (mult: {config['fuel_multiplier']})")
            print(f"{'='*80}")
            
            for run in range(10):
                current_test += 1
                progress_pct = (current_test / total_tests) * 100
                print(f"\rProgresso: {current_test}/{total_tests} ({progress_pct:.1f}%) - "
                      f"Config {config['config_id']}/{len(test_configs)} run {run+1}/10", 
                      end='', flush=True)
                
                result = run_test(config, run + 1)
                
                if result:
                    result['config_id'] = config['config_id']
                    result['config_name'] = config['name']
                    result['capacity_multiplier'] = config['capacity_multiplier']
                    result['fuel_multiplier'] = config['fuel_multiplier']
                    result['num_gas_stations'] = config['gas_stations']
                    writer.writerow(result)
                    csvfile.flush()  # Garantir que os dados são escritos imediatamente
            
            print()  # Nova linha após completar uma configuração
    
    print(f"\n{'='*80}")
    print(f"TESTE COMPLETO!")
    print(f"Resultados salvos em: {csv_filename}")
    print(f"Total de configurações testadas: {len(test_configs)}")
    print(f"Total de testes executados: {total_tests}")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
