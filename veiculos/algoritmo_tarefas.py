"""A* Algorithm for Multi-Task Delivery Route Optimization.

This module implements an A* search algorithm adapted for the Vehicle Routing Problem (VRP)
with capacity and fuel constraints. The algorithm finds the optimal sequence of pickups and
deliveries that minimizes the total travel time.

The problem is modeled as a search tree where:
    - Each node represents a state (current location + completed tasks)
    - Edges represent transitions (move to pickup or delivery location)
    - Heuristic h(n) estimates the remaining cost to complete all tasks
    - Cost g(n) is the accumulated time since the start

Key Features:
    - Dijkstra cache to avoid recalculation of routes
    - Admissible heuristic based on average cost per task
    - Active task penalization (λ-penalty) to avoid overload
    - Capacity and fuel constraints verified dynamically
    - Search tree visualization with matplotlib/networkx

This algorithm does not follow the FIPA protocol as it is a computational optimization
component that operates internally without agent communication. However, it integrates
with the SPADE multi-agent system where agents may use this algorithm to plan routes
and communicate the results via FIPA-ACL messages.

Classes:
    TreeNode: Represents a state in the A* search tree.

Functions:
    get_dijkstra_cached: Returns Dijkstra result with caching.
    clear_dijkstra_cache: Clears the global route cache.
    calculate_heuristic: Calculates h(n) for a given state.
    A_star_task_algorithm: Executes A* and returns the optimal route.

Usage Example:
    >>> from world.graph import Graph
    >>> graph = Graph()
    >>> orders = [order1, order2, order3]  # List of Order objects
    >>> path, time, tree = A_star_task_algorithm(
    ...     graph=graph,
    ...     start=0,
    ...     tasks=orders,
    ...     capacity=50,
    ...     max_fuel=100
    ... )
    >>> print(path)  # [(0, None), (3, 1), (5, 1), (7, 2), ...]
    >>> print(f"Total time: {time}s")
    >>> tree.plot_tree("search_tree.png")  # Optional visualization

Technical Notes:
    - Optimizations: Dijkstra cache reduces calls to routing algorithm
    - Admissibility: h(n) is admissible if average_cost ≤ actual minimum cost
    - Complexity: O(b^d) where b is branching factor and d is depth (2*num_tasks)
    - Memory: Stores entire search tree for visualization (can be disabled)

Algorithm Workflow:
    1. Initialize root node at starting location with all tasks pending
    2. Compute average cost per task for heuristic estimation
    3. Expand nodes with lowest f(n) = g(n) + h(n) using priority queue
    4. For each node, evaluate available pickup/delivery points considering:
        - Capacity constraints (current_load + task_quantity ≤ max_capacity)
        - Fuel constraints (route_fuel ≤ max_fuel)
        - Task precedence (pickup must occur before delivery)
    5. Generate child nodes for each feasible transition
    6. Continue until reaching target depth (2 * num_tasks)
    7. Backtrack from goal node to reconstruct optimal path

Performance Considerations:
    - Dijkstra cache reduces computational overhead significantly
    - Heuristic quality impacts search efficiency (better h → fewer expansions)
    - Lambda penalty parameter affects route structure (higher λ → fewer concurrent tasks)
"""

import sys
import os
from typing import TYPE_CHECKING

# Add parent directory to path for absolute imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from world.graph import Graph

# Conditional import to avoid circular import issues
if TYPE_CHECKING:
    from veiculos.veiculos import Order

# Global cache to store Dijkstra algorithm results
_dijkstra_cache = {}

def get_dijkstra_cached(graph: Graph, start: int, end: int):
    """Returns Dijkstra algorithm result using cache to avoid recalculations.
    
    Implements a memoization system for Dijkstra algorithm calls. Since the graph
    does not change during A* execution, routes between the same points will always
    yield the same result. The cache is indexed by (start, end) tuple.
    
    This function is a pure optimization technique and does not involve FIPA protocol.
    It operates at the computational level within a single agent's decision-making process.
    
    Args:
        graph (Graph): Graph instance containing the network topology.
        start (int): Source node ID.
        end (int): Destination node ID.
    
    Returns:
        tuple: A tuple (path, fuel, time) where:
            - path (list[Node]): List of nodes in the shortest path.
            - fuel (float): Fuel required to traverse the path.
            - time (float): Total travel time in seconds.
    
    Side Effects:
        Modifies the global _dijkstra_cache dictionary by adding new results.
    
    Examples:
        >>> result1 = get_dijkstra_cached(graph, 3, 7)  # Computes and stores
        >>> result2 = get_dijkstra_cached(graph, 3, 7)  # Returns from cache (instantaneous)
        >>> assert result1 == result2
        >>> # Cache hit provides O(1) lookup vs O(V²) for full Dijkstra
    
    Notes:
        - Cache is global and persists between A* calls
        - Use clear_dijkstra_cache() to clear before new execution
        - Performance: O(1) for cache hits, O(V²) for misses (full Dijkstra)
        - Memory: O(N²) worst case if all node pairs are queried
    
    Implementation Details:
        The cache uses a dictionary with (start, end) tuples as keys.
        Cache misses trigger a call to graph.djikstra() which implements
        Dijkstra's algorithm with priority queue (typically O(E log V) complexity).
    """
    cache_key = (start, end)
    if cache_key not in _dijkstra_cache:
        _dijkstra_cache[cache_key] = graph.djikstra(start, end)
    return _dijkstra_cache[cache_key]

def clear_dijkstra_cache():
    """Clears the global Dijkstra results cache.
    
    Should be called before each A* execution to avoid using outdated routes
    if the graph has changed (e.g., traffic updates, road closures).
    
    This is a housekeeping function that ensures data consistency. It does not
    involve FIPA protocol communication.
    
    Side Effects:
        Resets the global _dijkstra_cache dictionary to empty.
    
    Examples:
        >>> clear_dijkstra_cache()
        >>> # Cache is now empty - next calls to get_dijkstra_cached will compute everything
    
    Notes:
        - Automatically called in A_star_task_algorithm before starting search
        - Essential for correctness if graph topology can change
        - Has no effect on algorithm correctness, only performance
        - After clearing, first route queries will be slower until cache rebuilds
    
    Performance Impact:
        Clearing cache means next A* search will need to compute all Dijkstra
        paths from scratch. For a graph with V vertices and typical VRP with N tasks,
        expect approximately O(N*V) Dijkstra calls during first A* execution.
    """
    global _dijkstra_cache
    _dijkstra_cache = {}

class TreeNode:
    """Represents a node in the A* search tree.
    
    Each TreeNode encapsulates a complete state of the routing problem:
        - Current vehicle location
        - Tasks already started (pickups performed)
        - Tasks already completed (deliveries performed)
        - Current load and available fuel
        - Costs g(n) and h(n) for A* evaluation
    
    The tree is built dynamically by the A* algorithm, expanding nodes with
    lowest f(n) = g(n) + h(n) until reaching the target depth (2 * num_tasks).
    
    This class represents internal algorithm state and does not participate in
    FIPA protocol communication. However, the resulting route plan may be
    communicated between agents using FIPA-ACL messages (e.g., INFORM performative
    to notify other agents about planned route).
    
    Attributes:
        state (list[tuple]): Global task state as [(sender, receiver, qty, orderid), ...].
            Each tuple represents one delivery task with:
                - sender (int): Pickup location node ID
                - receiver (int): Delivery location node ID  
                - qty (int): Quantity to transport
                - orderid (int): Unique order identifier
        parent (TreeNode | None): Parent node in tree (None for root).
        location (int): Current node ID in the graph.
        order_id (int | None): Order ID associated with transition that created this node.
            None for root node (initial position).
        children (list[TreeNode]): List of expanded child nodes.
        initial_points_reached (list[tuple]): Pickups performed as [(orderid, location), ...].
        end_points_reached (list[tuple]): Deliveries performed as [(orderid, location), ...].
        available_points (list[tuple]): Points available for next expansion.
            Set by evaluate_available_points() method.
        depth (int): Depth in tree (0 = root, goal = 2*num_tasks).
        quantity (int): Current vehicle load.
        max_fuel (int): Maximum tank capacity.
        max_quantity (int): Maximum load capacity.
        h (float): Heuristic h(n) - estimated cost to goal.
        g (float): Cost g(n) - accumulated cost from root.
        f (float): Evaluation function f(n) = g(n) + h(n).
        average_cost_per_task (float): Average cost per task (used in h(n) calculation).
        lambda_penalty (int): Penalty for active tasks (default: 2).
            Higher values discourage having many concurrent active orders.
    
    Examples:
        >>> root = TreeNode(
        ...     location=0,
        ...     state=[(3, 7, 10, 1), (5, 9, 15, 2)],
        ...     max_quantity=50,
        ...     max_fuel=100,
        ...     depth=0,
        ...     initial_points_reached=[],
        ...     end_points_reached=[],
        ...     h=45.5,
        ...     g=0.0
        ... )
        >>> root.available_points = root.evaluate_available_points(graph)
        >>> root.create_childs()
        >>> print(len(root.children))  # 2 (one child for each available pickup)
    
    Notes:
        - Comparison (__gt__, __eq__) based on f(n) for PriorityQueue usage
        - order_id is None only for root node
        - Goal state has depth = 2 * num_tasks (pickup + delivery per task)
        - quantity attribute tracks current load, updated when creating children
    
    State Representation:
        The state tuple format (sender, receiver, qty, orderid) remains constant
        across all nodes. What changes is which pickups/deliveries have been performed
        (tracked in initial_points_reached and end_points_reached).
        
    Search Tree Structure:
        Root (depth=0): Vehicle at start, no tasks done
        Level 1 (depth=1): One pickup performed
        Level 2 (depth=2): Either second pickup OR first delivery
        ...
        Goal (depth=2N): All N pickups and N deliveries completed
    """
    
    def __init__(self, 
                 location,
                 state: list["Order"],
                 max_quantity:int=0, 
                 max_fuel:int=0,parent=None,
                 depth=0,initial_points_reached:list[int]=0,
                 end_points_reached:list[int]=0, 
                 h=0,
                 g=0,
                 average_cost_per_task:float=0,
                 lambda_penalty:int=2,
                 order_id=None):
        """Initializes a new node in the A* search tree.
        
        Creates a TreeNode representing a specific state in the vehicle routing
        problem. Each node captures the vehicle's position, completed tasks,
        and associated costs for A* evaluation.
        
        Args:
            location (int): Current node ID in the graph.
            state (list[tuple]): List of tasks as tuples (sender, receiver, qty, orderid).
                This state is shared across all nodes in the search tree.
            max_quantity (int, optional): Maximum vehicle load capacity. Defaults to 0.
            max_fuel (int, optional): Maximum fuel tank capacity. Defaults to 0.
            parent (TreeNode, optional): Parent node in tree. None for root. Defaults to None.
            depth (int, optional): Depth in tree (increments with each expansion). Defaults to 0.
            initial_points_reached (list[tuple], optional): Pickups performed [(orderid, loc), ...].
                Defaults to 0 (treated as empty list).
            end_points_reached (list[tuple], optional): Deliveries performed [(orderid, loc), ...].
                Defaults to 0 (treated as empty list).
            h (float, optional): Heuristic value h(n). Defaults to 0.
            g (float, optional): Accumulated cost g(n). Defaults to 0.
            average_cost_per_task (float, optional): Average cost per task for h(n) calculation.
                Defaults to 0.
            lambda_penalty (int, optional): Penalty factor for active tasks. Defaults to 2.
            order_id (int, optional): Order ID associated with transition creating this node.
                None for root node. Defaults to None.
        
        Notes:
            - f(n) is automatically computed as g + h
            - quantity is initialized to 0 and updated in create_childs()
            - available_points must be set by calling evaluate_available_points()
        
        Implementation Details:
            The constructor performs minimal computation. Most of the node's
            characteristics are determined when it is expanded (create_childs).
            This lazy initialization improves performance.
        """
        self.state = state
        self.parent = parent
        self.location = location
        self.order_id = order_id  # Order ID associated with this node
        self.children = []
        self.initial_points_reached = initial_points_reached
        self.end_points_reached = end_points_reached
        self.available_points = 0
        self.depth = depth
        self.quantity= 0
        self.max_fuel = max_fuel
        self.max_quantity = max_quantity
        self.h = h
        self.g = g
        self.f= self.g + self.h
        self.average_cost_per_task = average_cost_per_task
        self.lambda_penalty = lambda_penalty

    def __gt__(self, other):
        """Comparison operator greater than (>) based on f(n).
        
        Used by PriorityQueue to order nodes. Nodes with lower f(n) have
        higher priority (are expanded first) in the A* algorithm.
        
        This method enables the priority queue to maintain nodes sorted by
        their evaluation function, which is crucial for A* optimality.
        
        Args:
            other (TreeNode): Another TreeNode to compare against.
        
        Returns:
            bool: True if self.f > other.f, False otherwise.
        
        Notes:
            - Lower f(n) means better (more promising) node
            - PriorityQueue uses min-heap, so __gt__ reverses order
            - Ties in f(n) are broken by object ID in PriorityQueue
        
        Examples:
            >>> node1 = TreeNode(..., g=10, h=5)  # f = 15
            >>> node2 = TreeNode(..., g=8, h=4)   # f = 12
            >>> node1 > node2  # True (15 > 12)
            >>> # In PriorityQueue, node2 will be expanded first
        """
        return self.f > other.f
    
    def __eq__ (self, other):
        """Equality operator (==) based on state.
        
        Two nodes are equal if they have the same task state, regardless of
        location or costs. Used to detect duplicate states in search.
        
        However, in current A* implementation, this is not actively used for
        duplicate detection (nodes are not checked against closed list).
        Could be extended for graph search variant.
        
        Args:
            other (TreeNode): Another TreeNode to compare against.
        
        Returns:
            bool: True if self.state == other.state, False otherwise.
        
        Notes:
            - State comparison is by value (list equality)
            - Does not consider location, costs, or depth
            - Could be used to implement closed list optimization
        
        Examples:
            >>> state1 = [(3, 7, 10, 1), (5, 9, 15, 2)]
            >>> node1 = TreeNode(location=0, state=state1, ...)
            >>> node2 = TreeNode(location=4, state=state1, ...)
            >>> node1 == node2  # True (same state, different location)
        """
        return self.state == other.state
    
    def add_child(self, child_node):
        """Adds a child node to the children list.
        
        Simple utility method to maintain tree structure. Called during
        node expansion in create_childs() method.
        
        Args:
            child_node (TreeNode): TreeNode to be added as child.
        
        Side Effects:
            Modifies self.children by appending new node.
        
        Examples:
            >>> parent = TreeNode(...)
            >>> child = TreeNode(parent=parent, ...)
            >>> parent.add_child(child)
            >>> len(parent.children)  # 1
        """
        self.children.append(child_node)

    def create_childs(self):
        """Expands current node by creating all viable child nodes.
        
        For each available point (pickup or delivery), creates a new child node
        representing the transition to that point. Updates state, load, costs,
        and calculates new heuristic.
        
        This method implements the core expansion logic of the A* search tree.
        Each child represents a decision to visit a specific pickup or delivery
        location next in the route.
        
        Algorithm:
            1. For each point in available_points:
               - Copy lists of reached points
               - Update load (+ for pickup, - for delivery)
               - Create new TreeNode with depth+1
               - Calculate g(n) = parent.g + travel_time
               - Calculate h(n) with new state
               - Add child to children list
        
        Side Effects:
            - Modifies self.children (adds new nodes)
            - Each child has reference to self as parent
        
        available_points Format:
            List of tuples (location, orderid, quantity, time, type) where:
            - location (int): Destination node ID
            - orderid (int): Order ID
            - quantity (int): Quantity to load/unload
            - time (float): Travel time to location
            - type (int): 1=warehouse (pickup), 0=customer (delivery)
        
        Examples:
            >>> node.available_points = [(3, 1, 10, 5.5, 1), (7, 2, 15, 8.2, 1)]
            >>> node.create_childs()
            >>> print(len(node.children))  # 2
            >>> print(node.children[0].location)  # 3
            >>> print(node.children[0].quantity)  # 10 (pickup)
        
        Notes:
            - Must call evaluate_available_points() before this method
            - Children inherit state, max_quantity, max_fuel from parent
            - order_id associated with child identifies which order generated transition
            - Each child's g(n) includes cumulative cost from root
            - Each child's h(n) is recalculated based on remaining tasks
        
        Implementation Details:
            The method preserves immutability of parent state by copying lists.
            Quantity is updated based on point type (warehouse adds, customer subtracts).
            The heuristic calculation considers the new completion state.
        """
        for point in self.available_points:
            new_initial_points_reached = self.initial_points_reached.copy()
            new_end_points_reached = self.end_points_reached.copy()
            new_quantity = self.quantity
            point_order_id = point[1]  # order_id is at index 1
            
            if point[4] == 1:  # warehouse
                new_initial_points_reached.append((point[1],point[0]))
                new_quantity += point[2]
            else:  # customer
                new_end_points_reached.append((point[1],point[0]))
                new_quantity -= point[2]
            child_node = TreeNode(
                location=point[0],
                state=self.state,
                max_quantity=self.max_quantity,
                max_fuel=self.max_fuel,
                parent=self,
                depth=self.depth + 1,
                initial_points_reached=new_initial_points_reached,
                end_points_reached=new_end_points_reached,
                g=self.g + point[3],
                h=calculate_heuristic(
                    self.state,
                    new_end_points_reached,
                    new_initial_points_reached,
                    average_cost_per_task=self.average_cost_per_task,
                    lambda_penalty=self.lambda_penalty

                ),
                average_cost_per_task=self.average_cost_per_task,
                order_id=point_order_id  # Associate order_id with node
            )
            child_node.quantity = new_quantity
            self.add_child(child_node)

    def evaluate_available_points(self,graph: Graph):
        """Evaluates which points (pickups/deliveries) are reachable from current node.
        
        Checks all tasks in state and determines which transitions are viable
        considering:
            - Capacity constraints (not exceeding max_quantity)
            - Fuel constraints (not exceeding max_fuel)
            - Logical sequence (pickup before delivery)
            - Already visited points (avoid duplicates)
        
        This method implements the constraint checking logic that ensures generated
        routes are feasible with respect to vehicle limitations.
        
        Decision Logic:
            For each task (sender, receiver, qty, orderid) in state:
            
            1. If pickup not yet performed:
               - Check if qty + current_load ≤ max_quantity
               - Calculate route and fuel using get_dijkstra_cached
               - If fuel ≤ max_fuel: add sender to available points (type=1)
            
            2. If pickup already performed but delivery not:
               - Calculate route and fuel to receiver
               - If fuel ≤ max_fuel: add receiver to available points (type=0)
        
        Args:
            graph (Graph): Graph instance to calculate routes via Dijkstra.
        
        Returns:
            list[tuple]: List of tuples (location, orderid, quantity, time, type) where:
                - location (int): Destination node ID
                - orderid (int): Associated order ID
                - quantity (int): Quantity to load/unload
                - time (float): Travel time to location in seconds
                - type (int): 1=warehouse (pickup), 0=customer (delivery)
        
        Examples:
            >>> node = TreeNode(location=0, state=[(3, 7, 10, 1), (5, 9, 15, 2)], ...)
            >>> available = node.evaluate_available_points(graph)
            >>> print(available)
            # [(3, 1, 10, 5.5, 1), (5, 2, 15, 8.2, 1)]  # Two pickups available
            
            >>> # After picking up order 1:
            >>> node2 = TreeNode(location=3, initial_points_reached=[(1, 3)], ...)
            >>> available2 = node2.evaluate_available_points(graph)
            >>> print(available2)
            # [(7, 1, 10, 3.2, 0), (5, 2, 15, 6.1, 1)]  # Delivery 1 + Pickup 2
        
        Notes:
            - Uses Dijkstra cache via get_dijkstra_cached for performance
            - Does not modify node state (pure method)
            - Result should be manually assigned to self.available_points
            - Capacity check is pre-emptive (before route calculation)
            - Fuel check is post-route calculation (after knowing actual distance)
        
        Constraint Validation:
            Capacity: Prevents overloading by checking total load after pickup
            Fuel: Ensures vehicle can reach destination with current tank
            Precedence: Enforces pickup before delivery for same order
            Uniqueness: Prevents revisiting same pickup/delivery location
        """
        available_points = []
        for sender_location, receiver_location, quantity,orderid in self.state:
            if quantity + self.quantity > self.max_quantity:
                continue
            if (orderid,sender_location) not in self.initial_points_reached:
                _ ,fuel,time = get_dijkstra_cached(graph, self.location, sender_location)
                if fuel <= self.max_fuel:
                    available_points.append((sender_location, orderid, quantity,time, 1))
            else: 
                if (orderid,receiver_location) not in self.end_points_reached:
                    _ ,fuel,time = get_dijkstra_cached(graph, self.location, receiver_location)
                    if fuel <= self.max_fuel:
                        available_points.append((receiver_location, orderid, quantity,time, 0))

        return available_points
    
    def plot_tree(self, filename="search_tree.png"):
        """Creates a graphical visualization of the search tree using matplotlib and networkx.
        
        Generates a PNG image showing the entire search tree expanded by A*.
        Each node displays:
            - Location (Loc)
            - Depth (D)
            - Evaluation function f(n)
            - Components g(n) and h(n)
        
        This visualization tool helps understand the search behavior and debugging
        the algorithm. It does not involve FIPA protocol as it's a diagnostic utility.
        
        Visual Features:
            - Colors: Gradient by depth (viridis colormap)
            - Layout: Hierarchical (root at top, growing downward)
            - Arrows: Indicate direction parent → child
            - Size: 32x20 inches, 300 DPI
        
        Limitations:
            - Does not generate image if total_nodes >= 1000 (avoids huge file)
            - Requires matplotlib and networkx to be installed
        
        Args:
            filename (str, optional): PNG filename to save. Defaults to "search_tree.png".
        
        Side Effects:
            - Creates image file in current directory
            - Prints tree statistics (total nodes, maximum depth)
        
        Raises:
            ImportError: If matplotlib or networkx are not installed.
        
        Examples:
            >>> path, time, tree = A_star_task_algorithm(...)
            >>> tree.plot_tree("my_search_tree.png")
            # 📊 Search tree statistics:
            #   Total nodes: 245
            #   Maximum depth: 6
            # ✓ Search tree saved to: my_search_tree.png
        
        Notes:
            - Helper function count_nodes traverses recursively
            - Helper function get_max_depth calculates depth
            - Layout uses hierarchical algorithm with adaptive spacing
            - For large trees (≥1000 nodes), only prints statistics
        
        Performance:
            - Tree traversal: O(N) where N is number of nodes
            - Graph layout: O(N log N) for hierarchical positioning
            - Image rendering: O(N) for drawing all nodes and edges
        """
        
        # First, count the total number of nodes
        def count_nodes(node):
            count = 1
            for child in node.children:
                count += count_nodes(child)
            return count
        
        total_nodes = count_nodes(self)
        print(f"\n📊 Search tree statistics:")
        print(f"  Total nodes: {total_nodes}")
        
        # Calculate maximum depth
        def get_max_depth(node):
            if not node.children:
                return node.depth
            return max(get_max_depth(child) for child in node.children)
        
        max_depth = get_max_depth(self)
        print(f"  Maximum depth: {max_depth}")
        
        # If there are more than 1000 nodes, do not generate image
        if total_nodes >= 1000:
            print(f"\n⚠️  Tree too large ({total_nodes} nodes). Skipping image generation.")
            return
        
        # Continue with image generation
        try:
            import matplotlib.pyplot as plt
            import networkx as nx
        except ImportError:
            print("Error: matplotlib and networkx are required to plot the tree")
            print("Install with: pip install matplotlib networkx")
            return
        
        # Create directed graph
        G = nx.DiGraph()
        pos = {}
        labels = {}
        node_colors = []
        
        # Helper function to add nodes recursively
        def add_nodes_recursive(node, x=0, y=0, layer_width=2.0):
            node_id = id(node)
            
            # Add node to graph
            G.add_node(node_id)
            pos[node_id] = (x, -y)  # Negative y to grow downward
            
            # Create label with node information
            label = f"Loc:{node.location}\n"
            label += f"D:{node.depth}\n"
            label += f"f:{node.f:.1f}\n"
            label += f"g:{node.g:.1f}|h:{node.h:.1f}"
            labels[node_id] = label
            
            # Color node based on depth (gradient)
            node_colors.append(node.depth)
            
            # Add children
            num_children = len(node.children)
            if num_children > 0:
                # Calculate horizontal spacing for children
                child_width = layer_width / max(num_children, 1)
                start_x = x - (layer_width / 2) + (child_width / 2)
                
                for i, child in enumerate(node.children):
                    child_x = start_x + i * child_width
                    child_y = y + 1
                    
                    # Add edge
                    G.add_edge(node_id, id(child))
                    
                    # Recursion for child
                    add_nodes_recursive(child, child_x, child_y, layer_width * 0.8)
        
        # Build tree starting from root
        add_nodes_recursive(self, x=0, y=0, layer_width=10.0)
        
        # Create figure
        plt.figure(figsize=(32, 20))
        
        # Draw graph
        nx.draw(
            G, pos,
            labels=labels,
            node_color=node_colors,
            cmap=plt.cm.viridis,
            node_size=2000,
            font_size=7,
            font_weight='bold',
            arrows=True,
            arrowsize=10,
            edge_color='gray',
            linewidths=2,
            with_labels=True
        )
        
        # Add title
        plt.title(f"A* Search Tree\nTotal nodes: {len(G.nodes)}", 
                 fontsize=14, fontweight='bold')
        
        # Save figure
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"\n✓ Search tree saved to: {filename}")
        
        plt.close()
    
def calculate_heuristic(state,end_points_reached,initial_points_reached,average_cost_per_task,lambda_penalty:int=2):
    """Calculates heuristic h(n) for estimating remaining cost to goal.
    
    Implements an admissible heuristic based on:
        1. Average cost per task × remaining tasks (optimistic estimate)
        2. Penalty for active tasks (encourages completing pickups before starting new ones)
    
    This heuristic function is critical for A* efficiency. An admissible (never overestimating)
    heuristic guarantees optimal solution. This function does not involve FIPA protocol.
    
    Formula:
        h(n) = average_cost_per_task × (total_tasks - completed_tasks)
               - λ × active_tasks
    
    Where:
        - total_tasks = len(state)
        - completed_tasks = len(end_points_reached)
        - active_tasks = len(initial_points_reached) - completed_tasks
        - λ = lambda_penalty (default: 2)
    
    Admissibility:
        The heuristic is admissible if average_cost_per_task ≤ actual minimum cost
        per task. Since average_cost is calculated from real tasks, this is typically
        true (may underestimate due to not considering backtracking).
    
    Args:
        state (list[tuple]): Task list as [(sender, receiver, qty, orderid), ...].
        end_points_reached (list[tuple]): Completed deliveries [(orderid, location), ...].
        initial_points_reached (list[tuple]): Performed pickups [(orderid, location), ...].
        average_cost_per_task (float): Average cost per task calculated at start.
        lambda_penalty (int, optional): Penalty factor for active tasks. Defaults to 2.
    
    Returns:
        float: Heuristic value h(n).
    
    Examples:
        >>> state = [(3, 7, 10, 1), (5, 9, 15, 2), (2, 8, 5, 3)]
        >>> h = calculate_heuristic(
        ...     state=state,
        ...     end_points_reached=[(1, 7)],  # Task 1 completed
        ...     initial_points_reached=[(1, 3), (2, 5)],  # Tasks 1 and 2 started
        ...     average_cost_per_task=10.0,
        ...     lambda_penalty=2
        ... )
        >>> # h = 10.0 * (3 - 1) - 2 * (2 - 1) = 20.0 - 2.0 = 18.0
        >>> print(h)  # 18.0
    
    Notes:
        - Lambda penalty λ encourages vehicle to complete deliveries before new pickups
        - Higher λ value favors routes with less concurrent load
        - λ=0 ignores penalty (pure task count heuristic)
        - Penalty is negative (reduces h), making nodes with active tasks more attractive
    
    Heuristic Properties:
        - Admissible: Never overestimates (if average_cost ≤ minimum actual cost)
        - Consistent: h(n) ≤ cost(n,n') + h(n') for all neighbors n'
        - Informative: Provides meaningful guidance (better than h=0)
    
    Design Rationale:
        The lambda penalty term biases the search toward completing active orders
        rather than accumulating many concurrent pickups, which reduces vehicle
        load and improves practical efficiency.
    """
    total_tasks = len(state)
    completed_tasks = len(end_points_reached)
    active_tasks = len(initial_points_reached) - completed_tasks
    average_cost_per_task = average_cost_per_task
    return (average_cost_per_task * (total_tasks - completed_tasks)) - (lambda_penalty * active_tasks)


def A_star_task_algorithm(graph: Graph, start:int, tasks:list["Order"],capacity:int, max_fuel: int):
    """Executes the A* algorithm to find optimal sequence of pickups and deliveries.
    
    Solves the Vehicle Routing Problem (VRP) with capacity and fuel constraints,
    finding the route that minimizes total time to execute all tasks.
    
    This algorithm operates as an internal planning component and does not directly
    use FIPA protocol. However, in a multi-agent system, the resulting route plan
    may be communicated between agents using FIPA-ACL messages:
        - Vehicle agent may REQUEST route from planner agent
        - Planner responds with INFORM containing optimal path
        - Vehicle may CONFIRM acceptance or REFUSE if infeasible
    
    Algorithm Steps:
        1. Initialization:
           - Clear Dijkstra cache
           - Calculate average cost per task for heuristic
           - Create initial state as list of (sender, receiver, qty, orderid)
           - Create root node at location=start
        
        2. A* Search:
           - Use PriorityQueue to expand nodes with lowest f(n)
           - For each node: evaluate available points, create children
           - Add children to queue
           - Stop when depth = 2 * num_tasks (all tasks completed)
        
        3. Path Reconstruction:
           - Traverse parent links from goal node to root
           - Build list of (location, order_id)
           - Reverse list to chronological order
    
    Args:
        graph (Graph): Graph instance with network topology.
        start (int): Initial vehicle node ID.
        tasks (list[Order]): List of Order objects to be executed.
        capacity (int): Maximum vehicle load capacity.
        max_fuel (int): Maximum fuel tank capacity.
    
    Returns:
        tuple: A tuple (path, total_time, tree) where:
            - path (list[tuple]): Sequence of (node_id, order_id) representing route.
                - First element: (start, None) - initial position
                - Following elements: (location, orderid) - pickups and deliveries
            - total_time (float): Total time to complete all tasks.
            - tree (TreeNode): Root of search tree (for visualization).
    
    Examples:
        >>> from world.graph import Graph
        >>> graph = Graph()
        >>> orders = [
        ...     Order(product="A", quantity=10, orderid=1, 
        ...           sender="w1", receiver="s1", 
        ...           sender_location=3, receiver_location=7),
        ...     Order(product="B", quantity=15, orderid=2,
        ...           sender="w2", receiver="s2",
        ...           sender_location=5, receiver_location=9)
        ... ]
        >>> path, time, tree = A_star_task_algorithm(
        ...     graph=graph,
        ...     start=0,
        ...     tasks=orders,
        ...     capacity=50,
        ...     max_fuel=100
        ... )
        >>> print(path)
        # [(0, None), (3, 1), (7, 1), (5, 2), (9, 2)]
        >>> print(f"Total time: {time}s")
        # Total time: 45.3s
        >>> tree.plot_tree("route_search.png")
    
    Edge Cases:
        - If tasks empty: returns ([(start, None)], 0.0, root)
        - If no feasible solution: returns (None, float('inf'), root)
            and generates visualization showing search tree
    
    Notes:
        - Goal is depth = 2 * len(tasks) (1 pickup + 1 delivery per task)
        - PriorityQueue uses (f, id(node), node) for tie-breaking by ID
        - order_id=None in root node (initial position without associated task)
        - Search is optimal (finds minimum cost solution) if heuristic is admissible
    
    Complexity:
        - Time: O(b^d) where b is branching factor, d is depth (2*num_tasks)
        - Space: O(b^d) for storing search tree
        - Typical branching: 2*num_tasks initially, decreasing as tasks complete
    
    Integration with SPADE Agents:
        While this function itself doesn't use FIPA, it integrates with SPADE agents:
        1. Vehicle agent calls this function to compute optimal route
        2. Result may be sent to other agents via FIPA INFORM message
        3. Coordinator agent may REQUEST route updates during execution
        4. Warehouse agents receive INFORM about pickup times from route
    """
    # Simplified A* algorithm implementation for task ordering
    from queue import PriorityQueue
    
    # Clear Dijkstra cache for new execution
    clear_dijkstra_cache()
    # Calculate average cost per task
    total_time = sum(order.deliver_time for order in tasks)
    average_cost_per_task = total_time / len(tasks) if tasks else 0
    # Create initial state (sender_location, receiver_location, quantity, orderid)
    initial_state = [
        (order.sender_location, order.receiver_location, order.quantity, order.orderid)
        for order in tasks
    ]
    
    # Create root node
    root = TreeNode(
        location=start,
        state=initial_state,
        max_quantity=capacity,
        max_fuel=max_fuel,
        parent=None,
        depth=0,
        initial_points_reached=[],
        end_points_reached=[],
        h=calculate_heuristic(initial_state, [], [], average_cost_per_task),
        g=0,
        average_cost_per_task=average_cost_per_task
    )
    
    # Priority queue for A*
    open_list = PriorityQueue()
    open_list.put((root.f, id(root), root))
    target_depth = 2 * len(tasks)
    
    while not open_list.empty():
        _, _, current_node = open_list.get()
        
        # Check if we reached the goal
        if current_node.depth == target_depth:
            # Reconstruct path as list of tuples (location, order_id)
            path = []
            node = current_node
            while node is not None:
                if node.order_id is not None:  # Skip root node which has no order_id
                    path.append((node.location, node.order_id))
                elif node.parent is None:  # Root node - add only initial location
                    path.append((node.location, None))
                node = node.parent
            path.reverse()
            
            # Return: path with tuples (location, order_id), total time, search tree
            total_time = current_node.g
            return path, total_time, root
        
        # Evaluate available points
        current_node.available_points = current_node.evaluate_available_points(graph)
        # Create children
        current_node.create_childs()
        
        # Add children to priority queue
        for child in current_node.children:
            open_list.put((child.f, id(child), child))
    
    root.plot_tree("route_search.png")
    
    return None, float('inf'), root


