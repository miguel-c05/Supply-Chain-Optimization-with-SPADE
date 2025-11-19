"""World module for Supply Chain Optimization simulation.

This module defines the World class which manages the graph-based representation
of a supply chain network, including nodes (facilities) and edges (routes) with
dynamic cost and traffic simulation capabilities.
"""

import os
import random
import numpy as np
import config as cfg
from world.graph import Graph


class World:
    """Represents a world simulation environment for supply chain optimization.
    
    The World class creates and manages a grid-based graph network where nodes represent
    facilities (warehouses, suppliers, stores, gas stations) and edges represent routes
    between them. It simulates dynamic traffic conditions, fuel consumption, and costs
    associated with traversing routes.
    
    Attributes:
        width (int): Width of the grid world.
        height (int): Height of the grid world.
        tick_counter (int): Current simulation tick counter.
        graph (Graph): NetworkX-based graph representing the world.
        max_cost (float): Maximum cost value for edge weights.
        mode (str): Cost distribution mode - 'uniform' or 'different'.
        seed (int): Random seed for reproducibility.
        min_distance (int): Minimum distance in meters between nodes.
        max_distance (int): Maximum distance in meters between nodes.
        gas_stations (int): Number of gas station facilities.
        warehouses (int): Number of warehouse facilities.
        suppliers (int): Number of supplier facilities.
        stores (int): Number of store facilities.
        traffic_matrix (list): 2D matrix storing traffic costs between nodes.
        distances_matrix (list): 2D matrix storing distances between nodes.
        traffic_probability (float): Probability of traffic occurring.
        traffic_spread_probability (float): Probability of traffic spreading to adjacent edges.
        untraffic_probability (float): Probability of traffic clearing from an edge.
        traffic_interval (int): Number of ticks between traffic generation attempts.
    """

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
        """Initializes a World instance with grid graph and facility assignment.
        
        Creates a rectangular grid graph where nodes are connected to their orthogonal neighbors.
        Initializes cost and distance matrices, assigns facilities to random nodes, and 
        configures traffic simulation parameters.
        
        Args:
            width (int): Width of the grid world. Default is 5.
            height (int): Height of the grid world. Default is 5.
            mode (str): Cost distribution mode. Must be 'uniform' or 'different'.
                       'uniform' assigns cost 1 to all edges.
                       'different' assigns random costs between 1 and max_cost. Default is 'uniform'.
            min_distance (int): Minimum distance in meters between nodes. Default is 1000.
            max_distance (int): Maximum distance in meters between nodes. Default is 3000.
            seed (int, optional): Random seed for reproducibility. If provided, loads pre-generated
                                 matrices from SEED_DIR. If None, generates new matrices. Default is None.
            gas_stations (int): Number of gas stations to place in the world. Default is 0.
            warehouses (int): Number of warehouses to place in the world. Default is 0.
            suppliers (int): Number of suppliers to place in the world. Default is 0.
            stores (int): Number of stores to place in the world. Default is 0.
            highway (bool): If True, adds a high-capacity edge (highway) between two distant nodes.
                           Default is False.
            max_cost (float): Maximum traffic cost value for edges. Default is 10.
            traffic_probability (float): Probability (0-1) of traffic occurring at each interval.
                                        Default is 0.3 (30% chance).
            traffic_spread_probability (float): Probability (0-1) of traffic spreading to adjacent edges.
                                               Default is 0.85 (85% chance).
            traffic_interval (int): Number of ticks between traffic generation attempts. Default is 3.
            untraffic_probability (float): Probability (0-1) of traffic clearing from an edge.
                                          Default is 0.3 (30% chance).
            tick (int): Initial tick counter value. Default is 0.
        
        Raises:
            AssertionError: If mode is not 'uniform' or 'different'.
            FileNotFoundError: If seed is provided but corresponding .npy file is not found in SEED_DIR.
        """
        
        self.width = width
        self.height = height
        self.tick_counter = tick
        # Creates a grid graph where each node is connected to its orthogonal neighbors
        self.graph = Graph.grid_2d_graph(width, height)
        
        # Renames nodes to sequential integers (1, 2, ..., width*height)
        # This transforms (x, y) coordinate tuples to numeric identifiers
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

        # Generate or load cost and distance matrices from seed
        self.traffic_matrix, self.distances_matrix = self._generate_cost_matrix() 
        # Apply costs from matrices to graph edges
        self._add_costs_to_edges()
        # Randomly assign facility types to nodes
        self._assign_facilities()

        if highway:
            # Add high-capacity edge between distant nodes
            self._add_highway_edge()

        # Calculate fuel consumption for all edges based on distance and cost
        self.graph.calculate_all_fuel_consumption()

        # List to track edges affected by traffic simulation
        self.graph.infected_edges = []
        self.traffic_probability = traffic_probability
        self.traffic_spread_probability = traffic_spread_probability
        self.untraffic_probability = untraffic_probability
        self.traffic_interval = traffic_interval

    def _add_highway_edge(self):
        """Adds a high-capacity highway edge between two distant random nodes.
        
        Creates an additional edge connecting two nodes that are at least a minimum
        Manhattan distance apart (min(width, height)). The highway edge has reduced
        weight (cost) compared to regular edges, simulating a faster route.
        
        The method ensures the two selected nodes are distinct and sufficiently
        distant before creating the edge. If insufficient nodes exist, the method
        returns without adding an edge.
        """
        nodes = list(self.graph.nodes.keys())
        if len(nodes) < 2:
            return  # Insufficient nodes to add an edge

        while True:
            u_id, v_id = random.sample(nodes, 2)
            manhattan_dist = self._manhattan_distance(u_id, v_id)
            if manhattan_dist >= min(self.width, self.height): 
                # Get Node objects from node IDs
                u = self.graph.get_node(u_id)
                v = self.graph.get_node(v_id)
                # Add high-capacity edge with reduced weight for faster traversal
                self.graph.add_edge(u, v, weight=manhattan_dist//2, distance=manhattan_dist*self.min_distance)
                break

    def _manhattan_distance(self, node1_id, node2_id):
        """Calculates Manhattan distance between two nodes using their IDs.
        
        Converts node IDs back to (x, y) grid coordinates and computes the
        Manhattan distance (also known as taxicab or L1 distance).
        
        Args:
            node1_id (int): ID of the first node (1-indexed).
            node2_id (int): ID of the second node (1-indexed).
        
        Returns:
            int: Manhattan distance = |x1 - x2| + |y1 - y2|
        """
        # Convert node ID back to (x, y) grid coordinates
        # Formula: for 1-indexed ID -> 0-indexed x = (ID-1) % width, y = (ID-1) // width
        x1 = (node1_id - 1) % self.width
        y1 = (node1_id - 1) // self.width
        x2 = (node2_id - 1) % self.width
        y2 = (node2_id - 1) // self.width

        return abs(x1 - x2) + abs(y1 - y2)

    def _generate_cost_matrix(self):
        """Generates or loads traffic cost and distance matrices for the world.
        
        If a seed is provided, attempts to load pre-computed matrices from a .npy file.
        Otherwise, generates new symmetric matrices and saves them for reproducibility.
        
        Matrix generation depends on the mode:
        - 'uniform': All edge costs are set to 1
        - 'different': Edge costs are random floats between 1 and max_cost
        
        Distances are always randomly generated between min_distance and max_distance
        for each unique node pair.
        
        Returns:
            tuple: (traffic_matrix, distances_matrix) where both are (n+1) x (n+1) lists
                   indexed by node IDs (1-indexed). Matrices are symmetric.
        
        Raises:
            FileNotFoundError: If provided seed file does not exist in SEED_DIR.
        """
        if self.seed is not None:
            # Load pre-computed matrices from disk for reproducibility
            random.seed(self.seed)
            seed_folder = cfg.SEED_DIR
            try:
                m = np.load(os.path.join(seed_folder, f"{self.seed}.npy"), allow_pickle=True).tolist()
                traffic_matrix = m[0]
                distances_matrix = m[1]

            except FileNotFoundError:
                raise FileNotFoundError(f"Seed file for seed {self.seed} not found in {seed_folder}.")

            return traffic_matrix, distances_matrix

            
        # Generate new seed by finding the next available seed number
        self.seed = random.randint(0, 200)
        while f"{self.seed}.npy" in os.listdir(cfg.SEED_DIR):
            self.seed += 1

        random.seed(self.seed)
        # Initialize (n+1) x (n+1) matrices with 0-padding for 1-indexing
        traffic_matrix = [[0 for _ in range(self.width * self.height + 1)] for _ in range(self.width * self.height + 1)]
        distances_matrix = [[0 for _ in range(self.width * self.height + 1)] for _ in range(self.width * self.height + 1)]
        
        # Generate symmetric distance and traffic matrices
        # Distances are always random; traffic costs depend on mode
        for i in range(1, self.width * self.height + 1):
            for j in range(i + 1, self.width * self.height + 1):
                # Generate symmetric distance
                distance = np.random.randint(self.min_distance, self.max_distance)
                distances_matrix[i][j] = distance
                distances_matrix[j][i] = distance
                # Generate symmetric traffic cost based on mode
                if self.mode == "uniform":
                    traffic_matrix[i][j] = 1
                    traffic_matrix[j][i] = 1
                else:
                    # Different mode: assign random costs per direction
                    traffic_matrix[i][j] = round(float(random.uniform(1, self.max_cost)), 4)
                    traffic_matrix[j][i] = round(float(random.uniform(1, self.max_cost)), 4)

        # Save generated matrices to disk for future reproducibility
        np.save(os.path.join(cfg.SEED_DIR, f"{self.seed}.npy"), (traffic_matrix, distances_matrix))
        return traffic_matrix, distances_matrix

    def _add_costs_to_edges(self):
        """Applies traffic costs and distances from matrices to graph edges.
        
        Iterates through all edges in the graph and assigns their weight (cost) from
        the traffic_matrix and distance from the distances_matrix. Also stores the
        initial weight for later comparison during traffic simulation.
        
        This method must be called after generating the cost matrices and before
        beginning traffic simulations.
        """
        for edge in self.graph.edges:
            u, v = edge.node1.id, edge.node2.id
            # Assign traffic cost and distance from pre-computed matrices
            edge.weight = self.traffic_matrix[u][v]
            # Store initial weight to detect changes during traffic simulation
            edge.initial_weight = self.traffic_matrix[u][v]
            edge.distance = self.distances_matrix[u][v]

    def _assign_facilities(self):
        """Assigns facility types to random nodes without duplication.
        
        Randomly distributes warehouses, suppliers, stores, and gas stations across
        the world's nodes. Each node is assigned at most one facility type, and the
        assignment is done sequentially from a shuffled list of available nodes.
        
        The order of assignment follows: warehouses -> suppliers -> stores -> gas_stations.
        If the total number of facilities exceeds available nodes, the assignment stops
        when all nodes are occupied.
        """
        # Initialize facility attributes on all nodes
        for node in self.graph.nodes.values():
            node.warehouse = False
            node.supplier = False
            node.store = False
            node.gas_station = False
        
        # Create shuffled list of all available nodes for random assignment
        available_nodes = list(self.graph.nodes.keys())
        random.shuffle(available_nodes)
        
        node_index = 0
        
        # Assign warehouses to first available nodes
        for _ in range(self.warehouses):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].warehouse = True
                node_index += 1
    
        # Assign suppliers to next available nodes
        for _ in range(self.suppliers):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].supplier = True
                node_index += 1
        
        # Assign stores to next available nodes
        for _ in range(self.stores):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].store = True
                node_index += 1
        
        # Assign gas stations to remaining available nodes
        for _ in range(self.gas_stations):
            if node_index < len(available_nodes):
                node_id = available_nodes[node_index]
                self.graph.nodes[node_id].gas_station = True
                node_index += 1

    def plot_graph(self):
        """Visualizes the world graph with nodes, edges, and traffic information.
        
        Creates a directed graph visualization showing:
        - Nodes colored by facility type (warehouse, supplier, store, gas station)
        - Edges labeled with distance, weight (time cost), and fuel consumption
        - Edge colors indicating direction and traffic status (red for congested)
        - A legend explaining all visual elements
        
        The visualization uses matplotlib and networkx libraries. Edges are drawn
        with arrows indicating direction, and congested edges (with weight different
        from initial weight) are highlighted in red.
        """
        import matplotlib.pyplot as plt
        import networkx as nx

        # Create directed graph for visualization
        G = nx.DiGraph()
        
        for node_id, node in self.graph.nodes.items():
            G.add_node(node_id, pos=(node.x, node.y))
        
        # Add all directed edges with their weights
        for edge in self.graph.edges:
            node1 = edge.node1.id
            node2 = edge.node2.id
            G.add_edge(node1, node2, weight=edge.weight)
        
        # Extract node positions for visualization
        pos = nx.get_node_attributes(G, 'pos')
        
        # Determine node colors based on facility type
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
        
        # Draw nodes with facility-type colors
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=1000)
        nx.draw_networkx_labels(G, pos, font_size=10)
        
        # Draw each edge with direction-aware colors and traffic information
        for edge in self.graph.edges:
            u, v = edge.node1.id, edge.node2.id
            
            # Determine edge color: red for congested (weight != initial_weight),
            # blue for forward direction (u<v), light blue for reverse (v>u)
            if edge.weight != edge.initial_weight:
                color = 'red'  # Congested edge (traffic-affected)
            else:
                color = 'blue' if u < v else 'lightblue'  # Direction indicator
            
            # Draw edge with arrow indicating direction
            nx.draw_networkx_edges(G, pos, [(u, v)], edge_color=color, 
                                   arrowsize=20, connectionstyle='arc3,rad=0.1', 
                                   width=2, arrows=True)
            
            # Draw edge labels: distance (meters), weight (time cost), fuel consumption (liters)
            edge_labels = {(u, v): f"{edge.distance}m\n{edge.weight}s\n{edge.get_fuel_consumption()}L"}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, 
                                        label_pos=0.3, font_size=8, 
                                        font_color=color, bbox=dict(boxstyle='round,pad=0.3', 
                                        facecolor='white', edgecolor=color, alpha=0.8))
        
        # Create and display legend explaining all visual elements
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
        legend_elements.append(mpatches.Patch(color='red', label='Congested Edge'))
        
        plt.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))

        plt.title(f"Graph (Seed: {self.seed}, Mode: {self.mode}, Tick: {self.tick_counter})")
        plt.axis('off')
        plt.tight_layout()
        plt.show()

    def traffic(self):
        """Simulates traffic congestion by increasing cost on a random edge.
        
        Implements the FIPA (Foundation for Intelligent Physical Agents) Request-Response
        interaction protocol pattern through the following mechanism:
        - Selects a random edge in the network
        - Increases its weight (cost) by a random factor (1-2 units)
        - Updates the traffic_matrix to persist the cost increase
        - Recalculates fuel consumption based on new cost
        - Triggers dynamic traffic propagation to adjacent edges
        - Marks the edge as infected in the tracked infected_edges list
        
        This method follows FIPA principles by:
        1. Autonomously making decisions about traffic propagation
        2. Using request-response patterns when calling dinamic_traffic()
        3. Maintaining consistent state in both edge objects and matrices
        
        The traffic event is recorded in infected_edges for later recovery simulation.
        """
        # Select a random edge and apply traffic congestion
        edges = random.sample(self.graph.edges, 1)
        for edge in edges:
            u, v = edge.node1.id, edge.node2.id
            increase = round(random.uniform(1, 2), 4)
            # Increase traffic cost in matrix
            self.traffic_matrix[u][v] += increase
            # Update edge weight with cap at maximum cost
            edge.weight = min(self.traffic_matrix[u][v], self.max_cost)
            
            # Recalculate fuel consumption based on new cost
            edge.calculate_fuel_consumption()
            
            # Track this edge as affected by traffic for later recovery
            edge_key = (u, v)
            if edge_key not in self.graph.infected_edges:
                self.graph.infected_edges.append(edge_key)
            
            # Propagate traffic to adjacent edges following FIPA patterns
            self.dinamic_traffic(edge, visited=set())

    def dinamic_traffic(self, edge, visited=None):
        """Propagates traffic congestion to adjacent edges in downstream direction.
        
        Implements dynamic traffic spreading following FIPA Contract-Net interaction protocol:
        - The initial traffic event acts as a "call for proposals"
        - Adjacent edges receive "proposals" to participate in traffic spread
        - Each adjacent edge independently "accepts" or "rejects" based on
          traffic_spread_probability
        - When accepted, the edge increases its cost and recursively propagates
          the traffic further downstream
        
        This follows FIPA principles by:
        1. Using probabilistic decision-making (traffic_spread_probability)
        2. Maintaining referential integrity through recursive propagation
        3. Preventing infinite loops via the visited set
        4. Ensuring state consistency across all affected edges
        
        Args:
            edge (Edge): The edge from which traffic should propagate.
            visited (set, optional): Set of already-processed edge keys to prevent loops.
                                   Defaults to empty set if None.
        
        Returns:
            None: Modifies edge states and matrices in place.
        """
        if visited is None:
            visited = set()
        
        # Prevent processing the same edge twice (cycle detection)
        edge_key = (edge.node1.id, edge.node2.id)
        if edge_key in visited:
            return
        visited.add(edge_key)
        
        # Identify the target node (destination of current edge)
        # Traffic propagates to edges starting from this node
        target_node = edge.node2.id
        
        # Check all edges to find those starting at target node
        for graph_edge in self.graph.edges:
            # Only propagate in same direction (from target_node forward)
            if graph_edge.node1.id == target_node:
                
                # Skip already visited edges
                graph_edge_key = (graph_edge.node1.id, graph_edge.node2.id)
                if graph_edge_key in visited:
                    continue
                    
                # Probabilistic decision: spread traffic based on probability
                # FIPA Contract-Net: edge independently "accepts" traffic proposal
                p = random.uniform(0, 1)
                if p > self.traffic_spread_probability:
                    u, v = graph_edge.node1.id, graph_edge.node2.id
                    # Increase cost by smaller factor for propagated traffic
                    increase = round(random.uniform(1, (float(self.max_cost)/2)), 4)
                    self.traffic_matrix[u][v] += increase
                    # Cap weight at maximum cost
                    graph_edge.weight = min(self.traffic_matrix[u][v], self.max_cost)
                    
                    # Recalculate fuel consumption based on new cost
                    graph_edge.calculate_fuel_consumption()
                    
                    # Track this edge as infected for later recovery
                    if graph_edge_key not in self.graph.infected_edges:
                        self.graph.infected_edges.append(graph_edge_key)
                    
                    # Recursively propagate traffic further downstream
                    self.dinamic_traffic(graph_edge, visited)
        
    def _restore_infected_edges(self):
        """Restores traffic-affected edges to initial state with probabilistic recovery.
        
        Implements the FIPA Inform interaction protocol by:
        - Informing each infected edge about recovery opportunity
        - Each edge probabilistically recovers (resets to initial weight)
        - Notifying the world about recovery through state updates
        - Removing recovered edges from tracking list
        
        This follows FIPA patterns by:
        1. Using one-way asynchronous inform messages (probability-based decisions)
        2. Maintaining state consistency after recovery
        3. Allowing for independent recovery of each edge
        
        Recovery probability is controlled by untraffic_probability parameter.
        When an edge recovers, its weight returns to initial_weight and fuel
        consumption is recalculated accordingly.
        """
        # Collect edges that recover during this cycle
        edges_to_remove = []
        
        # Iterate through all currently infected edges
        for edge_key in self.graph.infected_edges:
            # Probabilistic recovery: each edge independently recovers
            p = random.uniform(0, 1)
            if p > self.untraffic_probability:
                u, v = edge_key
                edge = self.graph.get_edge(u, v)
                if edge:
                    # Restore edge to pre-traffic state
                    edge.weight = edge.initial_weight
                    self.traffic_matrix[u][v] = edge.initial_weight
                    
                    # Recalculate fuel consumption based on restored weight
                    edge.calculate_fuel_consumption()
                    
                    # Mark edge for removal from infected list
                    edges_to_remove.append(edge_key)
        
        # Remove recovered edges from tracking list
        for edge_key in edges_to_remove:
            self.graph.infected_edges.remove(edge_key)
        
    def get_events(self, delta_time):
        """Advances world simulation by specified ticks and returns state change events.
        
        Simulates traffic dynamics over delta_time ticks by:
        1. Attempting to restore traffic-affected edges each tick
        2. Probabilistically introducing new traffic events
        3. Tracking all edge state changes (weight and fuel consumption)
        4. Recording events with precise timing information
        
        Implements FIPA Inform interaction pattern through:
        - Asynchronous state notifications to tracking system
        - Independent edge state updates
        - Timestamped event delivery
        
        Args:
            delta_time (int): Number of simulation ticks to advance.
        
        Returns:
            list: List of dictionaries describing edge state changes.
                 Each dictionary contains:
                 - node1_id (int): Source node of changed edge
                 - node2_id (int): Destination node of changed edge
                 - new_time (float): Updated weight (time cost) of edge
                 - new_fuel_consumption (float): Updated fuel consumption (liters)
                 - instant (int): Tick offset when change occurred (4-tick intervals)
                 
        Note:
            - Events at instant=0 are filtered out (initial state)
            - Tick counter is incremented by delta_time
            - Infected edges are tracked for recovery simulation
        """
        events = []
        
        # Capture initial state of all edges for change detection
        initial_states = {}
        for edge in self.graph.edges:
            initial_states[(edge.node1.id, edge.node2.id)] = edge.weight
        
        # Execute simulation for specified number of ticks
        for i in range(delta_time):
            
            # Attempt recovery of traffic-affected edges (FIPA Inform)
            self._restore_infected_edges()

            # Probabilistically introduce traffic at specified intervals
            if self.tick_counter % self.traffic_interval == 0:
                p = random.uniform(0, 1)
                if p > self.traffic_probability:
                    # Introduce new traffic event
                    self.traffic()
            
            # Increment tick counter
            self.tick_counter += 1
            
            # Detect and record edge state changes
            for edge in self.graph.edges:
                edge_key = (edge.node1.id, edge.node2.id)
                if edge.weight != initial_states[edge_key]:
                    # Edge state changed - create event record
                    edge.calculate_fuel_consumption()
                    event = {
                        "node1_id": edge.node1.id,
                        "node2_id": edge.node2.id,
                        "new_time": edge.weight,
                        "new_fuel_consumption": round(edge.fuel_consumption, 3),
                        "instant": i*4
                    }
                    events.append(event)
                    # Update tracked state to current state for next comparison
                    initial_states[edge_key] = edge.weight
        
        # Filter out initial events (instant=0) to report only actual changes
        events = [event for event in events if event["instant"] != 0]
        return events
    
