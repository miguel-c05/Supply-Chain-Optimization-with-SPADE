import os
import random
import numpy as np
import config as cfg
from world.graph import Graph


class World:

    def __init__(self, width, height, mode="uniform", seed=None, gas_stations=0, warehouses=0, suppliers=0, stores=0):

        self.width = width
        self.height = height
        # Cria um grafo que representa uma matriz, onde cada nó está ligado aos seus vizinhos ortogonais
        self.graph = Graph.grid_2d_graph(width, height)
        
        # Renomeia os nós para inteiros sequenciais (1, 2, ..., width*height)
        mapping = {}
        for i in range(height):
            for j in range(width):
                mapping[(j, i)] = i * width + j + 1
        self.graph.relabel_nodes(mapping)

        self.mode = mode
        assert self.mode in ["uniform", "different"], "Mode must be either 'uniform' or 'different'"
        self.seed = seed
        
        self.gas_stations = gas_stations
        self.warehouses = warehouses
        self.suppliers = suppliers
        self.stores = stores

        self.cost_matrix = self._generate_cost_matrix()
        self._add_costs_to_edges()
        self._assign_facilities()

        


    def _generate_cost_matrix(self, max_cost=10):
        if self.seed is not None:
            random.seed(self.seed)
            seed_folder = cfg.SEED_DIR
            try:
                cost_matrix = np.load(os.path.join(seed_folder, f"{self.seed}.npy"), allow_pickle=True).tolist()
            
            except FileNotFoundError:
                raise FileNotFoundError(f"Seed file for seed {self.seed} not found in {seed_folder}.")
            
            return cost_matrix

            
        self.seed = random.randint(0, 200)
        while f"{self.seed}.npy" in os.listdir(cfg.SEED_DIR):
            self.seed += 1

        random.seed(self.seed)
        cost_matrix = [[0 for _ in range(self.width * self.height + 1)] for _ in range(self.width * self.height + 1)]
        
        if self.mode == "uniform":
            uniform_cost = random.randint(1, max_cost)
            for edge in self.graph.edges:
                u, v = edge.node1.id, edge.node2.id
                cost_matrix[u][v] = uniform_cost
        else:
            for edge in self.graph.edges:
                u, v = edge.node1.id, edge.node2.id
                cost_matrix[u][v] = random.randint(1, max_cost)

        np.save(os.path.join(cfg.SEED_DIR, f"{self.seed}.npy"), cost_matrix)
        return cost_matrix
    

    def _add_costs_to_edges(self):
        """Adiciona os custos da matriz como peso nas arestas"""
        for edge in self.graph.edges:
            u, v = edge.node1.id, edge.node2.id
            edge.weight = self.cost_matrix[u][v]


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
        if self.warehouses > 0:
            for _ in range(self.warehouses):
                if node_index < len(available_nodes):
                    node_id = available_nodes[node_index]
                    self.graph.nodes[node_id].warehouse = True
                    node_index += 1
        
        # Atribui suppliers
        if self.suppliers > 0:
            for _ in range(self.suppliers):
                if node_index < len(available_nodes):
                    node_id = available_nodes[node_index]
                    self.graph.nodes[node_id].supplier = True
                    node_index += 1
        
        # Atribui stores
        if self.stores > 0:
            for _ in range(self.stores):
                if node_index < len(available_nodes):
                    node_id = available_nodes[node_index]
                    self.graph.nodes[node_id].store = True
                    node_index += 1
        
        # Atribui gas_stations
        if self.gas_stations > 0:
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
                node_colors.append('lightblue')
        
        # Desenha os nós com suas cores
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1000)
        nx.draw_networkx_labels(G, pos, font_size=10)
        
        # Desenha cada aresta com sua cor e label correspondente
        for edge in self.graph.edges:
            u, v = edge.node1.id, edge.node2.id
            
            # Define cor baseada na direção: u->v usa azul, v->u usa vermelho
            color = 'blue' if u < v else 'red'
            
            # Desenha a aresta
            nx.draw_networkx_edges(G, pos, [(u, v)], edge_color=color, 
                                   arrowsize=20, connectionstyle='arc3,rad=0.1', 
                                   width=2, arrows=True)
            
            # Desenha o label com a mesma cor
            edge_labels = {(u, v): edge.weight}
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
        legend_elements.append(mpatches.Patch(color='lightblue', label='Empty'))
        
        plt.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))

        plt.title(f"Graph (Seed: {self.seed}, Mode: {self.mode})")
        plt.axis('off')
        plt.tight_layout()
        plt.show()