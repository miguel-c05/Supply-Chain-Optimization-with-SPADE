class Node:
    def __init__(self, id, x=None, y=None):
        self.id = id
        self.x = x
        self.y = y
        self.neighbors = []
    
    def add_neighbor(self, node):
        if node not in self.neighbors:
            self.neighbors.append(node)
    
    def __repr__(self):
        return f"Node({self.id})"
    
    def __hash__(self):
        return hash(self.id)
    
    def __eq__(self, other):
        return self.id == other.id


class Edge:
    def __init__(self, node1, node2, weight=None, distance=None):
        self.node1 = node1
        self.node2 = node2
        self.weight = weight
        self.initial_weight = weight
        self.distance = distance
        self.fuel_consumption = 0  # liters
    
    def __repr__(self):
        return f"Edge({self.node1.id} -> {self.node2.id}, weight={self.weight}, distance={self.distance})"

    def get_other_node(self, node):
        return self.node2 if node == self.node1 else self.node1

    def calculate_fuel_consumption(self, fuel_efficiency=6.5, vehicle_weight=1500):
        """
        Calcula o consumo de combustível baseado na distância e no tráfego (weight).
        
        Args:
            fuel_efficiency: consumo base em litros por km (padrão: 6.5 L/km)
            vehicle_weight: peso do veículo em kg (padrão: 1500 kg)
        
        Returns:
            float: litros necessários para atravessar a aresta
        
        Fórmula: fuel = (distance/1000) * fuel_efficiency * (1 + traffic_factor) * weight_factor
        - distance está em metros, divide por 1000 para converter para km
        - traffic_factor aumenta o consumo com base no tráfego (devido à menor velocidade)
        - weight é em segundos, normalizamos por um fator para ajustar o impacto
        """

        if self.distance is None or self.weight is None or self.initial_weight is None:
            return 0
        
        # Fator de tráfego: quanto mais tempo na aresta, mais combustível é usado (baixa velocidade = mais consumo)
        # Normalizamos a diferença: (weight - initial_weight) / 10.0
        traffic_factor = max(0, (self.weight - self.initial_weight) / 10.0)
        
        # Fator de peso: veículos mais pesados consomem mais
        weight_factor = 1 + 0.01 * ((vehicle_weight - 1500) / 100)

        #print(self.distance, fuel_efficiency, traffic_factor, weight_factor)
        self.fuel_consumption = (self.distance / 1000) * fuel_efficiency * (1 + traffic_factor) * weight_factor

        return round(self.fuel_consumption, 2)
    
    def get_fuel_consumption(self):
        """Retorna o consumo de combustível da aresta"""
        return round(self.fuel_consumption, 2)


class Graph:
    def __init__(self):
        self.nodes = {}
        self.edges = []
        self.infected_edges = []
    
    def add_node(self, node):
        self.nodes[node.id] = node
    
    def add_edge(self, node1, node2, weight=None, distance=None):
        # Cria aresta de node1 para node2
        edge1 = Edge(node1, node2, weight, distance)
        self.edges.append(edge1)
        
        # Cria aresta de node2 para node1 (direção oposta)
        edge2 = Edge(node2, node1, weight, distance)
        self.edges.append(edge2)
        
        # Adiciona vizinhos bidireccionalmente
        node1.add_neighbor(node2)
        node2.add_neighbor(node1)
        
        return edge1, edge2
    
    def get_node(self, node_id):
        return self.nodes.get(node_id)
    
    def get_edge(self, node1_id, node2_id):
        """Retorna a aresta direcionada de node1_id para node2_id"""
        node1 = self.get_node(node1_id)
        node2 = self.get_node(node2_id)
        for edge in self.edges:
            if edge.node1 == node1 and edge.node2 == node2:
                return edge
        return None
    
    def get_neighbors(self, node_id):
        node = self.get_node(node_id)
        return node.neighbors if node else []
    
    def calculate_all_fuel_consumption(self, fuel_efficiency=6.5):
        """
        Calcula o consumo de combustível para todas as arestas.
        
        Args:
            fuel_efficiency: consumo base em litros por km (padrão: 6.5 L/km)

        Returns:
            dict: mapeamento de aresta -> consumo de combustível
        """
        fuel_map = {}
        for edge in self.edges:
            edge_key = (edge.node1.id, edge.node2.id)
            fuel_map[edge_key] = edge.calculate_fuel_consumption(fuel_efficiency)
        return fuel_map
    
    @staticmethod
    def grid_2d_graph(width, height):
        """Cria um grafo em grid 2D com nós conectados aos vizinhos ortogonais"""
        graph = Graph()
        
        # Criar todos os nós
        for i in range(height):
            for j in range(width):
                node = Node(id=(j, i), x=j, y=i)
                graph.add_node(node)
        
        # Conectar nós adjacentes (cima, baixo, esquerda, direita)
        for i in range(height):
            for j in range(width):
                current = graph.get_node((j, i))
                
                # Conectar à direita
                if j < width - 1:
                    right = graph.get_node((j + 1, i))
                    graph.add_edge(current, right)
                
                # Conectar para baixo
                if i < height - 1:
                    down = graph.get_node((j, i + 1))
                    graph.add_edge(current, down)
        
        return graph
    
    def relabel_nodes(self, mapping):
        """Renomeia os nós do grafo usando um dicionário de mapeamento"""
        new_nodes = {}
        for old_id, new_id in mapping.items():
            if old_id in self.nodes:
                node = self.nodes[old_id]
                node.id = new_id
                new_nodes[new_id] = node
        self.nodes = new_nodes