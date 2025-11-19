"""Module for graph representation and pathfinding in supply chain networks.

This module provides classes for representing directed graphs with weighted edges,
including nodes with coordinates and edges with weight properties for traffic simulation.
It includes Dijkstra's algorithm implementation for finding optimal paths considering
both travel time (weight) and fuel consumption.

Classes:
    Node: Represents a vertex in the graph with optional 2D coordinates.
    Edge: Represents a directed connection between two nodes with weight and distance.
    Graph: Represents a complete graph structure with nodes and edges.
"""

import heapq


class Node:
    """Represents a node (vertex) in a graph structure.
    
    A node represents a location in the supply chain network with optional 2D coordinates.
    Nodes can be connected to other nodes through edges and maintain a list of neighbors
    for graph traversal operations.
    
    Attributes:
        id: Unique identifier for the node. Can be any hashable type (int, str, tuple, etc.).
        x (float, optional): X-coordinate of the node in 2D space. Defaults to None.
        y (float, optional): Y-coordinate of the node in 2D space. Defaults to None.
        neighbors (list): List of neighboring Node objects directly connected via edges.
    """
    
    def __init__(self, id, x=None, y=None):
        """Initialize a Node.
        
        Args:
            id: Unique identifier for the node.
            x (float, optional): X-coordinate for 2D spatial representation. Defaults to None.
            y (float, optional): Y-coordinate for 2D spatial representation. Defaults to None.
        """
        self.id = id
        self.x = x
        self.y = y
        self.neighbors = []
    
    def add_neighbor(self, node):
        """Add a neighboring node to this node's neighbor list.
        
        Only adds the node if it is not already in the neighbor list to avoid duplicates.
        
        Args:
            node (Node): The node to add as a neighbor.
        """
        if node not in self.neighbors:
            self.neighbors.append(node)
    
    def __repr__(self):
        """Return a string representation of the node.
        
        Returns:
            str: A formatted string showing the node's ID.
        """
        return f"Node({self.id})"
    
    def __hash__(self):
        """Return hash value for the node based on its ID.
        
        This allows nodes to be used as dictionary keys and in sets.
        
        Returns:
            int: Hash value of the node's ID.
        """
        return hash(self.id)
    
    def __eq__(self, other):
        """Check equality between two nodes based on their ID.
        
        Two nodes are considered equal if they have the same ID.
        
        Args:
            other (Node): The node to compare with.
            
        Returns:
            bool: True if both nodes have the same ID, False otherwise.
        """
        return self.id == other.id


class Edge:
    """Represents a directed edge in a graph connecting two nodes.
    
    An edge represents a connection between two locations in the supply chain network,
    with properties for traversal cost (weight), distance, and fuel consumption calculation.
    The edge can represent road segments with traffic conditions affecting traversal time
    and fuel efficiency.
    
    Attributes:
        node1 (Node): The starting node of the directed edge.
        node2 (Node): The ending node of the directed edge.
        weight (float, optional): Cost of traversing the edge (e.g., travel time in seconds).
        initial_weight (float): The base weight without traffic influence, used to calculate traffic factors.
        distance (float, optional): Physical distance of the edge (e.g., in meters).
        fuel_consumption (float): Calculated fuel consumption in liters for traversing this edge.
    """
    
    def __init__(self, node1, node2, weight=None, distance=None):
        """Initialize an Edge between two nodes.
        
        Args:
            node1 (Node): The starting node of the edge.
            node2 (Node): The ending node of the edge.
            weight (float, optional): Traversal cost representing travel time or time delay.
                                     Defaults to None.
            distance (float, optional): Physical distance of the edge. Defaults to None.
        """
        self.node1 = node1
        self.node2 = node2
        self.weight = weight
        self.initial_weight = weight
        self.distance = distance
        self.fuel_consumption = 0  # liters
    
    def __repr__(self):
        """Return a string representation of the edge.
        
        Returns:
            str: A formatted string showing the edge's nodes, weight, and distance.
        """
        return f"Edge({self.node1.id} -> {self.node2.id}, weight={self.weight}, distance={self.distance})"

    def get_other_node(self, node):
        """Retrieve the other node connected by this edge.
        
        Given one node of the edge, returns the opposite node in the connection.
        
        Args:
            node (Node): One of the nodes in the edge.
            
        Returns:
            Node: The other node in the edge. Returns node2 if node equals node1,
                  otherwise returns node1.
        """
        return self.node2 if node == self.node1 else self.node1

    def calculate_fuel_consumption(self, fuel_efficiency=0.065, vehicle_weight=1500):
        """Calculate fuel consumption for traversing this edge.
        
        Computes fuel consumption based on distance, traffic conditions (represented by weight),
        and vehicle characteristics. The calculation uses a multi-factor model:
        
        Formula: fuel = (distance/1000) * fuel_efficiency * (1 + traffic_factor) * weight_factor
        
        Where:
            - distance: edge distance in meters, converted to kilometers (distance/1000)
            - fuel_efficiency: base consumption in liters per kilometer (default: 0.065 L/km = 6.5 L/100km)
            - traffic_factor: increases consumption based on congestion; calculated as:
                            (weight - initial_weight) / 10.0
                            Lower speeds due to traffic increase fuel consumption
            - weight_factor: accounts for vehicle mass impact on consumption:
                           1 + 0.01 * ((vehicle_weight - 1500) / 100)
                           Heavier vehicles consume more fuel
        
        The traffic factor represents the impact of network congestion where increased
        traversal time (weight) indicates slower speeds, resulting in higher consumption.
        
        Args:
            fuel_efficiency (float): Base fuel consumption in liters per km. 
                                    Default: 0.065 L/km (equivalent to 6.5 L/100km).
            vehicle_weight (int): Vehicle mass in kilograms. Default: 1500 kg.
        
        Returns:
            float: Calculated fuel consumption in liters, rounded to 2 decimal places.
                   Returns 0 if any required attribute (distance, weight, initial_weight) is None.
        
        Side Effects:
            Updates the edge's fuel_consumption attribute with the calculated value.
        """
        if self.distance is None or self.weight is None or self.initial_weight is None:
            return 0
        
        # Traffic factor: accounts for reduced speed due to congestion
        # (weight - initial_weight) represents additional delay from traffic
        # Normalized by dividing by 10.0 to scale appropriately
        traffic_factor = max(0, (self.weight - self.initial_weight) / 10.0)
        
        # Vehicle weight factor: heavier vehicles consume more fuel
        # Normalized around baseline weight of 1500 kg
        weight_factor = 1 + 0.01 * ((vehicle_weight - 1500) / 100)

        self.fuel_consumption = (self.distance / 1000) * fuel_efficiency * (1 + traffic_factor) * weight_factor

        return round(self.fuel_consumption, 2)
    
    def get_fuel_consumption(self):
        """Retrieve the most recently calculated fuel consumption for this edge.
        
        Returns the fuel consumption value that was previously calculated by
        calculate_fuel_consumption(). The value represents liters needed to
        traverse this edge under current conditions.
        
        Returns:
            float: Fuel consumption in liters, rounded to 3 decimal places.
        """
        return round(self.fuel_consumption, 3)


class Graph:
    """Represents a weighted directed graph for supply chain network simulation.
    
    This class manages a collection of nodes and directed edges representing a
    supply chain network. It provides methods for graph construction, neighbor queries,
    pathfinding using Dijkstra's algorithm, and fuel consumption calculations.
    
    The graph supports bidirectional edge creation for undirected connections and
    maintains tracking of infected edges for network failure simulation.
    
    Attributes:
        nodes (dict): Dictionary mapping node IDs to Node objects.
        edges (list): List of all Edge objects in the graph (both directions).
        infected_edges (list): List of edges marked as "infected" for failure simulation.
    """
    
    def __init__(self):
        """Initialize an empty graph with no nodes or edges."""
        self.nodes = {}
        self.edges = []
        self.infected_edges = []
    
    def add_node(self, node):
        """Add a node to the graph.
        
        Registers a node in the graph's node dictionary using its ID as key.
        The node is then available for edge connections and graph traversal.
        
        Args:
            node (Node): The node to add to the graph.
        """
        self.nodes[node.id] = node
    
    def add_edge(self, node1, node2, weight=None, distance=None):
        """Add a bidirectional edge between two nodes.
        
        Creates two directed edges (one in each direction) to form an undirected
        connection between the nodes. Both nodes are registered as neighbors of
        each other. This method is used for symmetric road connections in the
        supply chain network.
        
        Args:
            node1 (Node): First node of the edge.
            node2 (Node): Second node of the edge.
            weight (float, optional): Traversal cost (e.g., travel time). Defaults to None.
            distance (float, optional): Physical distance of the connection. Defaults to None.
        
        Returns:
            tuple: A pair of Edge objects (edge1, edge2) representing the bidirectional
                   connection, where edge1 goes from node1 to node2, and edge2 goes
                   from node2 to node1.
        """
        # Create directed edge from node1 to node2
        edge1 = Edge(node1, node2, weight, distance)
        self.edges.append(edge1)
        
        # Create directed edge from node2 to node1 (opposite direction)
        edge2 = Edge(node2, node1, weight, distance)
        self.edges.append(edge2)
        
        # Register as neighbors bidirectionally
        node1.add_neighbor(node2)
        node2.add_neighbor(node1)
        
        return edge1, edge2
    
    def get_node(self, node_id):
        """Retrieve a node by its ID.
        
        Args:
            node_id: The unique identifier of the node to retrieve.
        
        Returns:
            Node: The requested node, or None if not found.
        """
        return self.nodes.get(node_id)
    
    def get_edge(self, node1_id, node2_id):
        """Retrieve a directed edge between two nodes.
        
        Searches for a directed edge from the source node to the destination node.
        Note that edges are directional; to get the reverse direction, call this
        method with swapped parameters.
        
        Args:
            node1_id: ID of the source node.
            node2_id: ID of the destination node.
        
        Returns:
            Edge: The directed edge from node1 to node2, or None if not found.
        """
        node1 = self.get_node(node1_id)
        node2 = self.get_node(node2_id)
        for edge in self.edges:
            if edge.node1 == node1 and edge.node2 == node2:
                return edge
        return None
    
    def get_neighbors(self, node_id):
        """Retrieve all neighboring nodes for a given node.
        
        Args:
            node_id: ID of the node whose neighbors are requested.
        
        Returns:
            list: List of neighboring Node objects. Returns empty list if node not found.
        """
        node = self.get_node(node_id)
        return node.neighbors if node else []
    
    def calculate_all_fuel_consumption(self, fuel_efficiency=0.065):
        """Calculate fuel consumption for all edges in the graph.
        
        Iterates through all edges and computes their fuel consumption based on
        current network conditions (weights) and the specified fuel efficiency.
        This is useful for analyzing total network fuel costs and impact of
        congestion on energy consumption.
        
        Args:
            fuel_efficiency (float): Base fuel consumption in liters per km. 
                                    Default: 0.065 L/km (6.5 L/100km).
        
        Returns:
            dict: Mapping from edge tuples (node1_id, node2_id) to calculated fuel
                  consumption in liters. Each edge is processed separately, and
                  bidirectional edges have independent consumption calculations.
        """
        fuel_map = {}
        for edge in self.edges:
            edge_key = (edge.node1.id, edge.node2.id)
            fuel_map[edge_key] = edge.calculate_fuel_consumption(fuel_efficiency)
        return fuel_map
    
    @staticmethod
    def grid_2d_graph(width, height):
        """Create a 2D grid graph with orthogonal connections.
        
        Generates a grid-based graph where nodes are positioned at regular intervals
        and connected only to their orthogonal neighbors (up, down, left, right).
        Diagonal connections are not created. This topology is useful for simulating
        urban or structured distribution networks with Manhattan distance properties.
        
        The grid coordinates follow the convention: node.id = (x, y) where:
            - x ranges from 0 to width-1 (column)
            - y ranges from 0 to height-1 (row)
        
        Args:
            width (int): Number of columns in the grid.
            height (int): Number of rows in the grid.
        
        Returns:
            Graph: A new graph object with (width * height) nodes arranged in a grid,
                   with bidirectional edges connecting orthogonal neighbors.
        """
        graph = Graph()
        
        # Create all nodes at grid positions
        for i in range(height):
            for j in range(width):
                node = Node(id=(j, i), x=j, y=i)
                graph.add_node(node)
        
        # Connect orthogonal neighbors (right and down connections create bidirectional edges)
        for i in range(height):
            for j in range(width):
                current = graph.get_node((j, i))
                
                # Connect to right neighbor
                if j < width - 1:
                    right = graph.get_node((j + 1, i))
                    graph.add_edge(current, right)
                
                # Connect to bottom neighbor
                if i < height - 1:
                    down = graph.get_node((j, i + 1))
                    graph.add_edge(current, down)
        
        return graph
    
    def relabel_nodes(self, mapping):
        """Rename nodes in the graph using a mapping dictionary.
        
        Updates node IDs according to the provided mapping, which is useful for
        renumbering or restructuring node identifiers without recreating the graph.
        This operation modifies the graph in-place.
        
        Args:
            mapping (dict): Dictionary mapping old node IDs to new node IDs.
                           Only nodes with IDs in mapping.keys() are updated.
        """
        new_nodes = {}
        for old_id, new_id in mapping.items():
            if old_id in self.nodes:
                node = self.nodes[old_id]
                node.id = new_id
                new_nodes[new_id] = node
        self.nodes = new_nodes

    def djikstra(self, start_node_id, target_node_id):
        """Find the shortest path between two nodes using Dijkstra's algorithm.
        
        Implements Dijkstra's algorithm to find the path with minimum total weight
        (travel time) from start to target node, with fuel consumption as a secondary
        optimization criterion. The algorithm prioritizes paths with lower weights,
        and breaks ties by selecting paths with lower fuel consumption.
        
        FIPA Protocol Compliance:
        This method supports agent-based routing in FIPA-compliant supply chain agents.
        Agents can request optimal routes via standard FIPA messaging, allowing
        decentralized pathfinding decisions aligned with agent communication standards.
        
        Implementation Details:
            - Uses a min-heap priority queue with tuples (weight, fuel, counter, node)
            - The counter field ensures stable ordering when weights are equal
            - Fuel consumption is calculated dynamically for each edge traversal
            - Stops exploring paths once a superior alternative is found for each node
        
        Args:
            start_node_id: ID of the starting node.
            target_node_id: ID of the destination node.
        
        Returns:
            tuple: A 3-tuple containing:
                - path (list): List of Node objects representing the shortest path,
                               ordered from start to target. Returns None if no path exists.
                - total_fuel (float): Total fuel consumption in liters for traversing
                                     the complete path, rounded to 3 decimal places.
                - total_time (float): Total weight (travel time) in seconds, rounded to
                                     3 decimal places.
            
            Returns (None, 0.0, 0.0) if either start or target node does not exist.
        
        Time Complexity: O((V + E) log V) where V is number of nodes and E is number of edges.
        Space Complexity: O(V) for distance, fuel, and previous node tracking.
        """
        start_node = self.get_node(start_node_id)
        target_node = self.get_node(target_node_id)

        if not start_node or not target_node:
            # Always return (path, fuel, time) tuple for consistency
            return None, 0.0, 0.0

        # Min-heap priority queue: (weight_accumulated, fuel_accumulated, counter, node)
        # Counter ensures stable ordering when weights are equal
        counter = 0
        queue = [(0, 0, counter, start_node)]
        
        # Initialize distance and fuel tracking for all nodes
        distances = {node: float('inf') for node in self.nodes.values()}
        fuel_consumed = {node: float('inf') for node in self.nodes.values()}
        distances[start_node] = 0
        fuel_consumed[start_node] = 0
        previous_nodes = {node: None for node in self.nodes.values()}

        while queue:
            current_distance, current_fuel, _, current_node = heapq.heappop(queue)

            # Skip if a better path was already found
            if current_distance > distances[current_node]:
                continue
            if current_distance == distances[current_node] and current_fuel > fuel_consumed[current_node]:
                continue

            # Explore all neighbors
            for neighbor in current_node.neighbors:
                edge = self.get_edge(current_node.id, neighbor.id)
                if edge:
                    # Calculate traversal costs for this edge
                    weight = edge.weight if edge.weight is not None else 1
                    edge.calculate_fuel_consumption()
                    fuel = edge.fuel_consumption
                    
                    # Calculate costs via this path
                    new_distance = current_distance + weight
                    new_fuel = current_fuel + fuel

                    # Update if better path found (primary: lower weight, secondary: lower fuel)
                    if (new_distance < distances[neighbor] or 
                        (new_distance == distances[neighbor] and new_fuel < fuel_consumed[neighbor])):
                        distances[neighbor] = new_distance
                        fuel_consumed[neighbor] = new_fuel
                        previous_nodes[neighbor] = current_node
                        counter += 1
                        heapq.heappush(queue, (new_distance, new_fuel, counter, neighbor))

        # Reconstruct path from start to target
        path = []
        current = target_node
        while current:
            path.append(current)
            current = previous_nodes[current]
        path.reverse()

        # Calculate total fuel and time along the path
        total_fuel = 0.0
        total_time = 0.0
        for i in range(len(path) - 1):
            edge = self.get_edge(path[i].id, path[i + 1].id)
            if edge:
                # Ensure fuel consumption is calculated for this edge
                edge.calculate_fuel_consumption()
                total_fuel += edge.fuel_consumption
                total_time += edge.weight

        return path, round(total_fuel, 3), round(total_time, 3)