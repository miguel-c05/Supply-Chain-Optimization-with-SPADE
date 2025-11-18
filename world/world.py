import os
import random
import numpy as np
import config as cfg
from world.graph import Graph


class World:

    def __init__(self, 
                 width=5, 
                 height=5, 
                 mode="uniform", 
                 min_distance=1000,
                 max_distance=3000,
                 seed=None, 
                 gas_stations=0, 
                 warehouses=0, 
                 suppliers=0, 
                 stores=0, 
                 highway=False, 
                 max_cost=10,
                 traffic_probability=0.3,
                 traffic_spread_probability=0.85,
                 traffic_interval=3,
                 untraffic_probability=0.3,
                 tick=0):
        
        self.width = width
        self.height = height
        self.tick_counter = tick
        # Cria um grafo que representa uma matriz, onde cada nó está ligado aos seus vizinhos ortogonais
        self.graph = Graph.grid_2d_graph(width, height)
        
        # Renomeia os nós para inteiros sequenciais (1, 2, ..., width*height)
        mapping = {}
        for i in range(height):
            for j in range(width):
                mapping[(j, i)] = i * width + j + 1
        self.graph.relabel_nodes(mapping)

        self.max_cost = max_cost
        self.mode = mode
        assert self.mode in ["uniform", "different"], "Mode must be either 'uniform' or 'different'"
        self.seed = seed

        self.min_distance = min_distance
        self.max_distance = max_distance
        
        self.gas_stations = gas_stations
        self.warehouses = warehouses
        self.suppliers = suppliers
        self.stores = stores

        self.traffic_matrix, self.distances_matrix = self._generate_cost_matrix() 
        self._add_costs_to_edges()
        self._assign_facilities()

        if highway:
            self._add_highway_edge()

        # Calcula o consumo de combustível de todas as arestas
        self.graph.calculate_all_fuel_consumption()

        self.graph.infected_edges = []  # Lista para rastrear arestas infectadas
        self.traffic_probability = traffic_probability
        self.traffic_spread_probability = traffic_spread_probability
        self.untraffic_probability = untraffic_probability
        self.traffic_interval = traffic_interval

    def _add_highway_edge(self):
        """Adiciona uma aresta de alta capacidade entre dois nós aleatórios com minimo de distancia manhattan de 5"""
        nodes = list(self.graph.nodes.keys())
        if len(nodes) < 2:
            return  # Não há nós suficientes para adicionar uma aresta

        while True:
            u_id, v_id = random.sample(nodes, 2)
            manhattan_dist = self._manhattan_distance(u_id, v_id)
            if manhattan_dist >= min(self.width, self.height): 
                # Obtém os objetos Node a partir dos IDs
                u = self.graph.get_node(u_id)
                v = self.graph.get_node(v_id)
                self.graph.add_edge(u, v, weight=manhattan_dist//2, distance=manhattan_dist*self.min_distance)  # Aresta de alta capacidade com peso 1
                break

    def _manhattan_distance(self, node1_id, node2_id):
        """Calcula a distância de Manhattan entre dois nós usando seus IDs"""
        # Converte ID de volta para coordenadas (x, y)
        x1 = (node1_id - 1) % self.width
        y1 = (node1_id - 1) // self.width
        x2 = (node2_id - 1) % self.width
        y2 = (node2_id - 1) // self.width

        return abs(x1 - x2) + abs(y1 - y2)

    def _generate_cost_matrix(self):
        if self.seed is not None:
            random.seed(self.seed)
            seed_folder = cfg.SEED_DIR
            try:
                m = np.load(os.path.join(seed_folder, f"{self.seed}.npy"), allow_pickle=True).tolist()
                traffic_matrix = m[0]
                distances_matrix = m[1]

            except FileNotFoundError:
                raise FileNotFoundError(f"Seed file for seed {self.seed} not found in {seed_folder}.")

            return traffic_matrix, distances_matrix

            
        self.seed = random.randint(0, 200)
        while f"{self.seed}.npy" in os.listdir(cfg.SEED_DIR):
            self.seed += 1

        random.seed(self.seed)
        traffic_matrix = [[0 for _ in range(self.width * self.height + 1)] for _ in range(self.width * self.height + 1)]
        distances_matrix = [[0 for _ in range(self.width * self.height + 1)] for _ in range(self.width * self.height + 1)]
        
        # Generate symmetric distance matrix
        for i in range(1, self.width * self.height + 1):
            for j in range(i + 1, self.width * self.height + 1):
                distance = np.random.randint(self.min_distance, self.max_distance)
                distances_matrix[i][j] = distance
                distances_matrix[j][i] = distance
                if self.mode == "uniform":
                    traffic_matrix[i][j] = 1
                    traffic_matrix[j][i] = 1
                else:
                    traffic_matrix[i][j] = round(float(random.uniform(1, self.max_cost)), 4)
                    traffic_matrix[j][i] = round(float(random.uniform(1, self.max_cost)), 4)

        np.save(os.path.join(cfg.SEED_DIR, f"{self.seed}.npy"), (traffic_matrix, distances_matrix))
        return traffic_matrix, distances_matrix

    def _add_costs_to_edges(self):
        """Adiciona os custos da matriz como peso nas arestas"""
        for edge in self.graph.edges:
            u, v = edge.node1.id, edge.node2.id
            #print(f"Adding cost to edge ({u}, {v}): Distance = {self.distances_matrix[u][v]}, Initial Weight = {self.traffic_matrix[u][v]}")
            edge.weight = self.traffic_matrix[u][v]
            edge.initial_weight = self.traffic_matrix[u][v]
            edge.distance = self.distances_matrix[u][v]

    def _assign_facilities(self):
        """Atribui facilities (warehouses, suppliers, stores, gas_stations) a nós aleatórios"""
        # Inicializa atributos de facilities em todos os nós
        for node in self.graph.nodes.values():
            node.warehouse = False
            node.supplier = False
            node.store = False
            node.gas_station = False
        
        # Lista de todos os nós disponíveis
        available_nodes = list(self.graph.nodes.keys())
        random.shuffle(available_nodes)
        
        node_index = 0
        
        # Atribui warehouses
        for _ in range(self.warehouses):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].warehouse = True
                node_index += 1
    
        # Atribui suppliers
        for _ in range(self.suppliers):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].supplier = True
                node_index += 1
        
        # Atribui stores
        for _ in range(self.stores):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].store = True
                node_index += 1
        
        # Atribui gas_stations
        for _ in range(self.gas_stations):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].gas_station = True
                node_index += 1

    def plot_graph(self):
        """Plota o grafo com os custos nas arestas direcionadas"""
        import matplotlib.pyplot as plt
        import networkx as nx

        G = nx.DiGraph()  # Grafo direcionado
        
        for node_id, node in self.graph.nodes.items():
            G.add_node(node_id, pos=(node.x, node.y))
        
        # Adiciona todas as arestas direcionadas com seus pesos
        for edge in self.graph.edges:
            node1 = edge.node1.id
            node2 = edge.node2.id
            G.add_edge(node1, node2, weight=edge.weight)
        
        pos = nx.get_node_attributes(G, 'pos')
        
        # Define cores para cada tipo de nó
        node_colors = []
        for node_id in G.nodes():
            node = self.graph.nodes[node_id]
            if node.warehouse:
                node_colors.append('orange')
            elif node.supplier:
                node_colors.append('green')
            elif node.store:
                node_colors.append('purple')
            elif node.gas_station:
                node_colors.append('yellow')
            else:
                node_colors.append('lightgrey')
        
        # Desenha os nós com suas cores
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1000)
        nx.draw_networkx_labels(G, pos, font_size=10)
        
        # Desenha cada aresta com sua cor e label correspondente
        for edge in self.graph.edges:
            u, v = edge.node1.id, edge.node2.id
            
            # Define cor baseada no estado do tráfego
            # Se o peso é diferente do peso inicial, é vermelho (infectado)
            # Caso contrário, usa azul para u<v e lightblue para v>u
            if edge.weight != edge.initial_weight:
                color = 'red'
            else:
                color = 'blue' if u < v else 'lightblue'
            
            # Desenha a aresta
            nx.draw_networkx_edges(G, pos, [(u, v)], edge_color=color, 
                                   arrowsize=20, connectionstyle='arc3,rad=0.1', 
                                   width=2, arrows=True)
            
            # Desenha o label com a mesma cor
            edge_labels = {(u, v): f"{edge.distance}m\n{edge.weight}s\n{edge.get_fuel_consumption()}L"}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, 
                                        label_pos=0.3, font_size=8, 
                                        font_color=color, bbox=dict(boxstyle='round,pad=0.3', 
                                        facecolor='white', edgecolor=color, alpha=0.8))
        
        # Adiciona legenda
        import matplotlib.patches as mpatches
        legend_elements = []
        if self.warehouses > 0:
            legend_elements.append(mpatches.Patch(color='orange', label='Warehouse'))
        if self.suppliers > 0:
            legend_elements.append(mpatches.Patch(color='green', label='Supplier'))
        if self.stores > 0:
            legend_elements.append(mpatches.Patch(color='purple', label='Store'))
        if self.gas_stations > 0:
            legend_elements.append(mpatches.Patch(color='yellow', label='Gas Station'))
        legend_elements.append(mpatches.Patch(color='lightgrey', label='Empty'))
        legend_elements.append(mpatches.Patch(color='blue', label='Edge Direction (u→v)'))
        legend_elements.append(mpatches.Patch(color='lightblue', label='Edge Direction (v→u)'))
        legend_elements.append(mpatches.Patch(color='red', label='Infected Edge'))
        
        plt.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))

        plt.title(f"Graph (Seed: {self.seed}, Mode: {self.mode}, Tick: {self.tick_counter})")
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    def traffic(self):
        """Aumenta o custo de uma edge aleatória para simular tráfego"""
        edges = random.sample(self.graph.edges, 1)
        for edge in edges:
            u, v = edge.node1.id, edge.node2.id
            increase = round(random.uniform(1, 2), 4)
            self.traffic_matrix[u][v] += increase
            edge.weight = min(self.traffic_matrix[u][v], self.max_cost)
            
            # Recalcula o consumo de combustível da aresta
            edge.calculate_fuel_consumption()
            
            # Adiciona aresta à lista de infected_edges
            edge_key = (u, v)
            if edge_key not in self.graph.infected_edges:
                self.graph.infected_edges.append(edge_key)
            
            self.dinamic_traffic(edge, visited=set())
            #print(f"Traffic added: Cost from Node {u} to Node {v} increased by {increase} to {edge.weight}")

    def dinamic_traffic(self, edge, visited=None):
        """Propaga tráfego dinamicamente para arestas adjacentes na mesma direção"""
        if visited is None:
            visited = set()
        
        # Evita processar a mesma aresta novamente
        edge_key = (edge.node1.id, edge.node2.id)
        if edge_key in visited:
            return
        visited.add(edge_key)
        
        # O nó para onde queremos propagar tráfego é o nó2 da aresta atual
        target_node = edge.node2.id
        
        for graph_edge in self.graph.edges:
            # Verifica se a aresta começa no nó alvo (mesma direção)
            if graph_edge.node1.id == target_node:
                
                # Evita processar a mesma aresta
                graph_edge_key = (graph_edge.node1.id, graph_edge.node2.id)
                if graph_edge_key in visited:
                    continue
                    
                p = random.uniform(0, 1)
                if p > self.traffic_spread_probability:
                    u, v = graph_edge.node1.id, graph_edge.node2.id
                    increase = round(random.uniform(1, (float(self.max_cost)/2)), 4)
                    self.traffic_matrix[u][v] += increase
                    graph_edge.weight = min(self.traffic_matrix[u][v], self.max_cost)
                    
                    # Recalcula o consumo de combustível da aresta
                    graph_edge.calculate_fuel_consumption()
                    
                    # Adiciona aresta à lista de infected_edges
                    if graph_edge_key not in self.graph.infected_edges:
                        self.graph.infected_edges.append(graph_edge_key)
                    
                    #print(f"Dynamic traffic: Cost from Node {u} to Node {v} increased by {increase} to {graph_edge.weight}")
                    self.dinamic_traffic(graph_edge, visited)
        
    def _restore_infected_edges(self):
        """Restaura as arestas infectadas com probabilidade > 0.2"""
        edges_to_remove = []
        
        for edge_key in self.graph.infected_edges:
            p = random.uniform(0, 1)
            if p > self.untraffic_probability:
                u, v = edge_key
                edge = self.graph.get_edge(u, v)
                if edge:
                    edge.weight = edge.initial_weight
                    self.traffic_matrix[u][v] = edge.initial_weight
                    
                    # Recalcula o consumo de combustível da aresta restaurada
                    edge.calculate_fuel_consumption()
                    
                    edges_to_remove.append(edge_key)
                    #print(f"Edge ({u}, {v}) restored to initial weight: {edge.initial_weight}")
        
        # Remove arestas restauradas da lista de infected_edges
        for edge_key in edges_to_remove:
            self.graph.infected_edges.remove(edge_key)
        
    def get_events(self, delta_time):
        """
        Avança o estado do mundo em delta_time ticks e retorna lista de eventos.
        
        Returns:
            list: Lista de dicionários com informações das arestas que mudaram.
                  Cada dicionário contém: node1_id, node2_id, new_time, 
                  new_fuel_consumption, instant
        """
        events = []
        
        # Store initial edge states
        initial_states = {}
        for edge in self.graph.edges:
            initial_states[(edge.node1.id, edge.node2.id)] = edge.weight
        
        # Simulate each tick
        for i in range(delta_time):
            
            self._restore_infected_edges()

            if self.tick_counter % self.traffic_interval == 0:
                p = random.uniform(0, 1)
                if p > self.traffic_probability:
                    self.traffic()
            
            self.tick_counter += 1
            
            # Check which edges changed in this tick
            for edge in self.graph.edges:
                edge_key = (edge.node1.id, edge.node2.id)
                if edge.weight != initial_states[edge_key]:
                    # Edge changed - record the event
                    edge.calculate_fuel_consumption()
                    event = {
                        "node1_id": edge.node1.id,
                        "node2_id": edge.node2.id,
                        "new_time": edge.weight,
                        "new_fuel_consumption": round(edge.fuel_consumption, 3),
                        "instant": i
                    }
                    events.append(event)
                    # Update the initial state to current state
                    initial_states[edge_key] = edge.weight

            self.plot_graph()
        
        events = [event for event in events if event["instant"] != 0]
        return events