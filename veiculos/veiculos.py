"""Vehicle Module for SPADE-based Supply Chain Simulation.

This module implements autonomous vehicle agents that operate in an event-driven 
supply chain system. Vehicles receive orders from warehouses, calculate optimal 
routes, manage load capacity and fuel consumption, and execute deliveries 
asynchronously using SPADE (Smart Python Agent Development Environment) framework.

The module follows FIPA-ACL (Foundation for Intelligent Physical Agents - Agent 
Communication Language) protocols for inter-agent communication, enabling 
standardized message exchanges between vehicles, warehouses, stores, and the 
event coordination agent.

Classes:
    Order: Represents a delivery order with origin, destination, and product details.
    Veiculo: SPADE agent that manages order execution and map navigation.

Usage Example:
    >>> from world.graph import Graph
    >>> map_graph = Graph()
    >>> vehicle = Veiculo(
    ...     jid="vehicle1@localhost",
    ...     password="pass123",
    ...     max_fuel=100,
    ...     capacity=50,
    ...     max_orders=10,
    ...     map=map_graph,
    ...     weight=1.0,
    ...     current_location=0,
    ...     event_agent_jid="event@localhost"
    ... )
    >>> await vehicle.start()

Notes:
    - Uses A* algorithm for multi-order route optimization
    - Communicates with warehouses using FIPA-ACL protocol
    - Integrates with event agent for temporal simulation and transit updates
    - XMPP presence indicates availability (CHAT=available, AWAY=busy)
    - Supports dynamic traffic updates and route recalculation
    
FIPA Protocol Implementation:
    This module implements several FIPA-ACL performatives:
    - `propose`: Vehicle sends proposals to warehouses (vehicle-proposal)
    - `confirm`: Warehouse confirms order acceptance (order-confirmation)
    - `inform`: Event agent sends status updates (arrival, transit)
    - `request`: Vehicles request pickups/deliveries from suppliers/stores
"""

import copy
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.presence import PresenceType, PresenceShow
import asyncio
from datetime import datetime
import random
import json
import sys
import os

# Add parent directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from veiculos.algoritmo_tarefas import A_star_task_algorithm
from world.graph import Graph


class Order:
    """
    Represents a delivery order in the supply chain system.
    
    An Order encapsulates all information necessary for transporting products 
    between two points (sender → receiver). It includes route calculations,
    delivery time estimation, fuel consumption, and execution state tracking.
    
    This class serves as a data container that is passed between agents and
    updated as the vehicle progresses through the delivery lifecycle (proposal,
    acceptance, pickup, transit, delivery).
    
    Attributes:
        product (str): Name or identifier of the product to be delivered.
        quantity (int): Quantity of the product (affects vehicle load capacity).
        orderid (int): Unique identifier for the order in the system.
        sender (str): JID of the sending agent (source warehouse).
        receiver (str): JID of the receiving agent (destination store or warehouse).
        deliver_time (float | None): Estimated delivery time calculated via Dijkstra algorithm.
            Initially None, populated by time_to_deliver() method.
        route (list[Node] | None): Path of nodes from sender to receiver.
            Initially None, populated by time_to_deliver() method.
        sender_location (int | None): ID of the source node in the graph.
            Initially None, set when order is created or calculated.
        receiver_location (int | None): ID of the destination node in the graph.
            Initially None, set when order is created or calculated.
        fuel (float | None): Fuel required to complete the route.
            Initially None, calculated by time_to_deliver() method.
        comecou (bool): Indicates whether the vehicle has picked up the order.
            False = pending pickup, True = in transit after pickup.
    
    Example:
        >>> order = Order(
        ...     product="Widget",
        ...     quantity=10,
        ...     orderid=42,
        ...     sender="warehouse1@localhost",
        ...     receiver="store5@localhost"
        ... )
        >>> order.time_to_deliver(
        ...     sender_location=3, 
        ...     receiver_location=7, 
        ...     map=graph, 
        ...     weight=1.0,
        ...     current_location=0,
        ...     capacity=50,
        ...     max_fuel=100
        ... )
        >>> print(f"Delivery time: {order.deliver_time}s")
    
    Note:
        The 'comecou' attribute (Portuguese for "started") is used to distinguish
        between orders awaiting pickup and orders currently being delivered.
    """
    
    def __init__(self, product:str, quantity:int, orderid:int, sender:str, receiver:str):
        """
        Initializes a new delivery order.
        
        Creates an Order instance with basic information. Route-related attributes
        (deliver_time, route, fuel, locations) are initialized to None and must be
        calculated later using the time_to_deliver() method.
        
        Args:
            product: Name or code identifier of the product.
            quantity: Number of units to transport (affects vehicle load).
            orderid: Unique numeric identifier for this order.
            sender: XMPP JID of the warehouse/sending agent.
            receiver: XMPP JID of the store/receiving agent.
        
        Note:
            Route attributes (deliver_time, route, fuel) are initialized as None
            and must be calculated subsequently with time_to_deliver().
        """
        self.product = product
        self.quantity = quantity
        self.sender = sender
        self.receiver = receiver

        self.deliver_time = None
        self.route = None
        self.sender_location = None
        self.receiver_location = None
        self.orderid = orderid
        self.fuel = None
        self.comecou = False
        
    def __str__(self):
        return (f"Order(id={self.orderid}, product={self.product}, qty={self.quantity}, "
                f"sender={self.sender}, receiver={self.receiver}, "
                f"sender_loc={self.sender_location}, receiver_loc={self.receiver_location}, "
                f"time={self.deliver_time}, fuel={self.fuel}, started={self.comecou})")
        
    def time_to_deliver(self,sender_location:int,receiver_location:int ,map: Graph,weight: float, current_location:int,capacity:int, max_fuel: int):
        """
        Calculates delivery time, route, and required fuel using Dijkstra and A* algorithms.
        
        This method performs two-stage route calculation:
        1. Uses Dijkstra to find shortest path between sender and receiver
        2. Uses A* task algorithm to optimize delivery time considering vehicle constraints
        
        The method updates multiple order attributes with calculation results, making
        the order ready for vehicle route planning and execution.
        
        Args:
            sender_location: ID of the source node in the graph (warehouse location).
            receiver_location: ID of the destination node in the graph (store location).
            map: Graph instance containing the transportation network topology.
            weight: Vehicle weight (available for future fuel consumption calculations).
            current_location: Current position of the vehicle in the graph.
            capacity: Maximum load capacity of the vehicle (units).
            max_fuel: Maximum fuel capacity of the vehicle.
        
        Side Effects:
            Modifies the following instance attributes:
            - self.route: List of Node objects representing the path.
            - self.deliver_time: Total travel time in seconds (optimized by A*).
            - self.fuel: Amount of fuel required for the route.
            - self.sender_location: Copy of sender_location argument.
            - self.receiver_location: Copy of receiver_location argument.
        
        Example:
            >>> order = Order("Product", 5, 1, "w1@localhost", "s1@localhost")
            >>> order.time_to_deliver(
            ...     sender_location=3, 
            ...     receiver_location=7, 
            ...     map=graph, 
            ...     weight=1.5,
            ...     current_location=0,
            ...     capacity=50,
            ...     max_fuel=100
            ... )
            >>> print(order.route)  # [Node(3), Node(5), Node(7)]
            >>> print(order.deliver_time)  # 45.2
        
        Note:
            The weight parameter is currently unused but available for future
            extensions that consider vehicle weight in fuel consumption.
            The final deliver_time is optimized by A* and may differ from
            the raw Dijkstra time calculation.
        """
        # Calculate delivery time based on the map using Dijkstra
        path, fuel, time = map.djikstra(int(sender_location), int(receiver_location))
        self.route = path
        self.deliver_time = time
        self.fuel = fuel
        self.sender_location = sender_location
        self.receiver_location = receiver_location
        # Optimize delivery time using A* task algorithm
        _ , time , _ = A_star_task_algorithm(map, current_location, [self], capacity, max_fuel)
        self.deliver_time = time

class Veiculo(Agent):
    """
    SPADE agent representing an autonomous delivery vehicle.
    
    The Veiculo (Vehicle) is an intelligent agent that manages delivery orders, 
    calculates optimal routes using A*, communicates with warehouses and stores, 
    and simulates movement on a graph. It integrates with an event agent for 
    temporal simulation and responds to traffic/transit events.
    
    The agent follows the FIPA-ACL protocol for inter-agent communication,
    using standardized performatives (propose, confirm, inform, request) to
    coordinate with warehouses, suppliers, stores, and the event coordination agent.
    
    Behaviour Architecture:
        - ReceiveOrdersBehaviour: Receives order proposals from warehouses.
            Implements FIPA propose protocol by sending vehicle-proposal messages.
        - WaitConfirmationBehaviour: Awaits confirmation of accepted orders.
            Implements FIPA confirm protocol by processing order-confirmation messages.
        - MovementBehaviour: Processes movement and arrival events.
            Implements FIPA inform protocol by receiving event agent updates.
        - PresenceInfoBehaviour: Responds to presence information requests.
            Implements FIPA query protocol for vehicle status queries.
        - ReceivePickupConfirmation: Receives pickup confirmations from suppliers.
            Implements FIPA inform protocol for pickup acknowledgments.
        - ReceiveDeliveryConfirmation: Receives delivery confirmations from stores.
            Implements FIPA inform protocol for delivery acknowledgments.
    
    FIPA Communication Protocol:
        1. Order Proposal (FIPA propose):
           Warehouse → Vehicle: "order-proposal" with order details
           Vehicle → Warehouse: "vehicle-proposal" with can_fit + delivery_time
        
        2. Order Confirmation (FIPA confirm):
           Warehouse → Vehicle: "order-confirmation" with acceptance decision
           Vehicle processes and adds order to active or pending queue
        
        3. Status Updates (FIPA inform):
           Event Agent → Vehicle: "arrival" events for node arrivals
           Event Agent → Vehicle: "Transit" events for traffic updates
           Vehicle → Event Agent: "time-update" with estimated arrival time
        
        4. Pickup/Delivery (FIPA inform):
           Vehicle → Supplier: "vehicle-pickup" when collecting goods
           Vehicle → Store: "vehicle-delivery" when delivering goods
    
    Attributes:
        max_fuel (int): Maximum fuel tank capacity.
        capacity (int): Maximum load capacity (product units).
        current_fuel (int): Current available fuel.
        current_load (int): Current load being transported.
        max_orders (int): Maximum number of simultaneous orders allowed.
        weight (float): Vehicle weight (affects fuel consumption).
        orders (list[Order]): Active orders being executed in current route.
        map (Graph): Graph representing the transportation network.
        current_location (int): ID of the node where vehicle is currently located.
        next_node (int | None): ID of the next destination node in the route.
        fuel_to_next_node (float): Fuel required to reach the next node.
        actual_route (list[tuple[int, int]]): Current route as list of (node_id, order_id) tuples.
        pending_orders (list[Order]): Orders accepted but not yet started.
        time_to_finish_task (float): Estimated time to complete current route.
        pending_confirmations (dict): Orders awaiting warehouse confirmation.
            Key: orderid (int)
            Value: dict with {order, can_fit, delivery_time, sender_jid}
        event_agent_jid (str): JID of the event coordination agent.
        verbose (bool): Enable detailed logging output.
    
    Example:
        >>> from world.graph import Graph
        >>> graph = Graph()
        >>> vehicle = Veiculo(
        ...     jid="vehicle1@localhost",
        ...     password="pass123",
        ...     max_fuel=100,
        ...     capacity=50,
        ...     max_orders=10,
        ...     map=graph,
        ...     weight=1.0,
        ...     current_location=0,
        ...     event_agent_jid="event@localhost",
        ...     verbose=False
        ... )
        >>> await vehicle.start()
        >>> # Vehicle autonomously awaits and processes orders from warehouses
    
    Note:
        - XMPP Presence: CHAT = available for orders, AWAY = executing tasks
        - Uses A* for multi-order route optimization (minimizes total time)
        - Automatic fuel refill at pickups and deliveries
        - Supports dynamic traffic updates via event agent
        - Route recalculation when new orders are accepted
    """


    def __init__(self, jid:str, password:str, max_fuel:int, capacity:int, max_orders:int, map: Graph, weight: float,current_location:int,event_agent_jid, verbose : bool = False):
        """
        Initializes a new vehicle agent.
        
        Creates a Veiculo instance with specified capacity, fuel, and map configuration.
        The vehicle starts with a full fuel tank, no load, and no active orders.
        
        Args:
            jid: Jabber ID (XMPP) of the agent in format "vehicle@domain".
            password: Password for XMPP authentication.
            max_fuel: Maximum fuel tank capacity (arbitrary units).
            capacity: Maximum load capacity (product units).
            max_orders: Maximum number of simultaneous orders (currently not enforced).
            map: Graph instance with the transportation network topology.
            weight: Vehicle weight for fuel consumption calculations.
            current_location: ID of the initial node where vehicle starts.
            event_agent_jid: JID of the event coordination agent for time synchronization.
            verbose: Enable detailed debug logging (default: False).
        
        Note:
            The vehicle starts with full fuel tank (current_fuel = max_fuel) and no load.
            The max_orders parameter is defined but not currently enforced in the logic.
        """
        super().__init__(jid, password)

        self.max_fuel = max_fuel
        self.capacity = capacity
        self.current_fuel = max_fuel
        self.current_load = 0
        self.max_orders = max_orders
        self.weight = weight
        self.orders = []
        self.map = map
        self.current_location = current_location 
        self.next_node= None
        self.fuel_to_next_node= 0
        self.actual_route = []  # List of tuples (node_id, order_id)
        self.pending_orders = []
        self.time_to_finish_task = 0
        self.event_agent_jid = event_agent_jid
        self.verbose = verbose
        
        # Dictionary to store multiple orders awaiting confirmation
        # Key: orderid, Value: dict with order, can_fit, delivery_time, sender_jid
        self.pending_confirmations = {}


    async def setup(self):
        """
        Configures and starts the vehicle agent behaviours.
        
        This method is automatically called by SPADE when the agent starts. It configures:
        - XMPP presence (accepts all contacts, status AVAILABLE/CHAT)
        - Message templates for filtering communication types (following FIPA-ACL)
        - Six cyclic behaviours with specific templates for different message types
        
        Message Templates Created (FIPA-ACL Performatives):
            - order_template: Filters "order-proposal" messages from warehouses.
                Uses FIPA propose performative for contract negotiation.
            - confirmation_template: Filters "order-confirmation" messages.
                Uses FIPA confirm performative for agreement finalization.
            - event_template: Filters "inform" messages from event agent.
                Uses FIPA inform performative for status updates.
            - inform_template: Filters "presence-info" query messages.
                Uses FIPA query performative for information requests.
            - pickup_confirm_template: Filters "pickup-confirm" from suppliers.
                Uses FIPA inform performative for acknowledgments.
            - delivery_confirm_template: Filters "delivery-confirm" from stores.
                Uses FIPA inform performative for acknowledgments.
        
        Side Effects:
            - Adds ReceiveOrdersBehaviour for receiving proposals.
            - Adds WaitConfirmationBehaviour for processing confirmations.
            - Adds MovementBehaviour for processing time/movement events.
            - Adds PresenceInfoBehaviour for responding to status queries.
            - Adds ReceivePickupConfirmation for supplier acknowledgments.
            - Adds ReceiveDeliveryConfirmation for store acknowledgments.
            - Sets presence as AVAILABLE/CHAT (available for orders).
        
        Note:
            Template filtering prevents behaviours from processing incorrect messages,
            ensuring clean separation of concerns following FIPA-ACL protocol standards.
        """
        from spade.template import Template
        
        self.presence.approve_all=True
        self.presence.set_presence(presence_type=PresenceType.AVAILABLE,
                                   show=PresenceShow.CHAT)
        
        print(f"[{self.name}] Vehicle agent setup complete. Presence: AVAILABLE/CHAT")
        
        # Template to receive order proposals from warehouses (FIPA propose)
        order_template = Template()
        order_template.set_metadata("performative", "order-proposal")
        
        # Template to receive confirmations from warehouses (FIPA confirm)
        confirmation_template = Template()
        confirmation_template.set_metadata("performative", "order-confirmation")
        
        # Template to receive messages from event agent (tick, arrival, transit) (FIPA inform)
        event_template = Template()
        event_template.set_metadata("performative", "inform")

        # Template to receive presence information queries (FIPA query)
        inform_template = Template()
        inform_template.set_metadata("performative", "presence-info")
        
        # Template to receive pickup confirmations from suppliers (FIPA inform)
        pickup_confirm_template = Template()
        pickup_confirm_template.set_metadata("performative", "pickup-confirm")
        
        # Template to receive delivery confirmations from warehouses/stores (FIPA inform)
        delivery_confirm_template = Template()
        delivery_confirm_template.set_metadata("performative", "delivery-confirm")
        
        # Add cyclic behaviours with templates
        self.add_behaviour(self.ReceiveOrdersBehaviour(), template=order_template)
        self.add_behaviour(self.WaitConfirmationBehaviour(), template=confirmation_template)
        self.add_behaviour(self.MovementBehaviour(), template=event_template)
        self.add_behaviour(self.PresenceInfoBehaviour(),template=inform_template)
        self.add_behaviour(self.ReceivePickupConfirmation(),template=pickup_confirm_template)
        self.add_behaviour(self.ReceiveDeliveryConfirmation(),template=delivery_confirm_template)


    class ReceiveOrdersBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour to receive and process order proposals from warehouses.
        
        This behaviour continuously awaits messages from warehouses with order proposals
        following the FIPA Contract Net Protocol. For each received order:
        1. Validates required fields
        2. Calculates route and time using time_to_deliver()
        3. Checks if order fits in current route (can_fit_in_current_route)
        4. Sends proposal back to warehouse (can_fit + delivery_time)
        5. Stores order in pending_confirmations awaiting warehouse decision
        
        FIPA Protocol Implementation:
            This behaviour implements the PROPOSE stage of the FIPA Contract Net Protocol:
            - Receives CFP (Call for Proposal) as "order-proposal" message
            - Evaluates feasibility considering current commitments
            - Sends PROPOSE with delivery time and capacity availability
            - Awaits ACCEPT-PROPOSAL or REJECT-PROPOSAL from warehouse
        
        Message Format Received:
            - Metadata: performative="order-proposal" (FIPA CFP)
            - Body (JSON): {
                "product": str,
                "quantity": int,
                "orderid": int,
                "sender": str (JID),
                "receiver": str (JID),
                "sender_location": int,
                "receiver_location": int
              }
        
        Response Message Format Sent:
            - Metadata: performative="vehicle-proposal" (FIPA PROPOSE)
            - Body (JSON): {
                "orderid": int,
                "can_fit": bool,
                "delivery_time": float,
                "vehicle_id": str (JID)
              }
        
        Note:
            - Does not accept orders here - only analyzes and proposes
            - WaitConfirmationBehaviour processes the final warehouse decision
            - Invalid messages (missing fields) are silently ignored
        """

        async def run(self):
            """
            Main execution loop for receiving and processing order proposals.
            
            Continuously receives messages with order proposals, validates them,
            calculates feasibility, and sends proposals back to warehouses.
            """
            msg = await self.receive(timeout=1)
            if msg:
                order_data = json.loads(msg.body)
                
                # Validate required fields
                required_fields = ["product", "quantity", "orderid", "sender", "receiver", 
                                    "sender_location", "receiver_location"]
                if not all(field in order_data for field in required_fields):
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Invalid message - missing fields: {order_data}")
                    return
                
                order = Order(
                    product=order_data["product"],
                    quantity=order_data["quantity"],
                    orderid=order_data["orderid"],
                    sender=order_data["sender"],
                    receiver=order_data["receiver"]
                )
                order.sender_location = order_data["sender_location"]
                order.receiver_location = order_data["receiver_location"]
                
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Order received: {order}")
                
                # Calculate order information (route, time, fuel)
                order.time_to_deliver(
                    sender_location=order.sender_location,
                    receiver_location=order.receiver_location,
                    map=self.agent.map,
                    weight=self.agent.weight,
                    current_location=self.agent.current_location,
                    capacity=self.agent.capacity,
                    max_fuel=self.agent.max_fuel

                )
                
                # Check if order fits in current route
                can_fit, delivery_time = await self.can_fit_in_current_route(order)
                order.deliver_time = delivery_time

                proposal_msg= Message(to=order.sender)
                proposal_msg.set_metadata("performative", "vehicle-proposal")
                
                proposal_data = {
                    "orderid": order.orderid,
                    "can_fit": can_fit,
                    "delivery_time": delivery_time,
                    "vehicle_id": str(self.agent.jid)
                }
                proposal_msg.body = json.dumps(proposal_data)
                await self.send(proposal_msg)
                
                
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Proposal sent back to {msg.sender} - Order {order.orderid}: can_fit={can_fit}, time={delivery_time}, order route={order.route}")
                else:
                    print(f"[{self.agent.name}] Proposal sent back to {msg.sender}") 
                    
                # Store information in pending confirmations dictionary
                self.agent.pending_confirmations[order.orderid] = {
                    "order": order,
                    "can_fit": can_fit,
                    "delivery_time": delivery_time,
                    "sender_jid": str(msg.sender)
                }
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Order {order.orderid} added to pending confirmations. Total: {len(self.agent.pending_confirmations)}")
        
        async def calculate_order_info(self, order: Order):
            """
            Calculates the route, time, and fuel required for an order.
            
            This method is an asynchronous wrapper for the Order's time_to_deliver method.
            Calls Dijkstra's algorithm to calculate the shortest path between origin and destination.
            
            Args:
                order: Order instance to calculate route information for.
            
            Side Effects:
                Modifies the order's attributes:
                - order.route: Path of nodes
                - order.deliver_time: Travel time
                - order.fuel: Required fuel
                - order.sender_location: Origin
                - order.receiver_location: Destination
            
            Note:
                This method is currently unused in the code (calculation done directly in run()).
            """
            path, fuel, time = await self.agent.map.djikstra(
                int(order.sender), 
                int(order.receiver)
            )
            order.route = path
            order.deliver_time = time
            order.fuel = fuel
            order.sender_location = int(order.sender)
            order.receiver_location = int(order.receiver)
        
        async def can_fit_in_current_route(self, new_order: Order) -> tuple[bool, float]:
            """
            Checks if the new order can fit in the current route without overload.
            
            This method is the core of the vehicle's scheduling logic. It simulates the execution
            of the current route adding the new order and verifies:
            1. If vehicle is available (CHAT) → accepts immediately
            2. If route passes through order sender → simulates pickup/delivery
            3. If there's capacity overflow at any point → rejects to pending
            4. Calculates delivery time considering current route
            
            Algorithm:
                - Checks XMPP presence (CHAT = free, AWAY = busy)
                - If free: returns (True, direct_time)
                - If busy: traverses actual_route simulating load
                - For each node: processes pickup/delivery of existing orders
                - Tries to insert pickup/delivery of new order
                - If overflow: calculates time with A* after current route
            
            Args:
                new_order: Order to check if it can be inserted.
            
            Returns:
                Tuple (can_fit, delivery_time) where:
                - can_fit (bool): True if fits in current route without overflow.
                - delivery_time (float): Estimated delivery time in seconds.
            
            Example:
                >>> can_fit, time = await self.can_fit_in_current_route(order)
                >>> if can_fit:
                ...     print(f"Order fits in current route, delivery in {time}s")
                ... else:
                ...     print(f"Order goes to pending, delivery in {time}s")
            
            Note:
                - Route is a list of (node_id, order_id) tuples
                - Simulates load without modifying actual vehicle state
                - If doesn't pass through sender, calculates time with pending_orders
            """
            # Check the agent's presence state
            # CHAT = available (no tasks), AWAY = busy (with tasks)
            presence_show = self.agent.presence.get_show()
            
            
            # If in CHAT (available), has no active tasks
            if presence_show == PresenceShow.CHAT:
                _ , order_time, _= A_star_task_algorithm(
                self.agent.map,
                self.agent.current_location,
                [new_order],
                self.agent.capacity,
                self.agent.max_fuel)
                return True, order_time
            
            # Create a dictionary with current orders for fast access
            orders_dict = {order.orderid: order for order in self.agent.orders}
            
            # Check if the new order passes through any point in current route
            route_nodes = [node_id for node_id, _ in self.agent.actual_route]

            passes_through_sender = new_order.sender_location in route_nodes
            
            # If doesn't pass through sender, calculate time with pending orders
            if not passes_through_sender:
                future_time = await self.calculate_future_delivery_time(new_order)
                return False, future_time
            
            # Simulate adding the order to the route
            # Traverse current path and simulate load
            current_load = self.agent.current_load
            new_order_picked = False
            new_order_delivered = False
            delivery_time = 0
            cumulative_time = 0
            
            for i, (node_id, order_id) in enumerate(self.agent.actual_route):
                # Calculate time to this point
                if i > 0:
                    prev_node_id = self.agent.actual_route[i - 1][0]
                    _, _, segment_time = self.agent.map.djikstra(prev_node_id, node_id)
                    cumulative_time += segment_time
                
                # Check if it's pickup or delivery of the new order
                if node_id == new_order.sender_location and not new_order_picked:
                    # Try to pickup the new order
                    test_load = current_load + new_order.quantity
                    
                    if test_load > self.agent.capacity:
                        # Overflow - calculate time with pending orders
                        future_time = await self.calculate_future_delivery_time(new_order)
                        return False, future_time
                    
                    current_load = test_load
                    new_order_picked = True
                
                elif node_id == new_order.receiver_location and new_order_picked and not new_order_delivered:
                    # Deliver the new order
                    current_load -= new_order.quantity
                    new_order_delivered = True
                    delivery_time = cumulative_time
                    # Delivered the item - can stop simulating
                    return True, delivery_time
                
                # Process the existing order at this point
                if order_id and order_id in orders_dict:
                    existing_order = orders_dict[order_id]
                    
                    # Check if it's pickup or delivery
                    if node_id == existing_order.sender_location:
                        # Pickup
                        test_load = current_load + existing_order.quantity
                        if test_load > self.agent.capacity:
                            # Overflow while processing existing order
                            future_time = await self.calculate_future_delivery_time(new_order)
                            return False, future_time
                        current_load = test_load
                    elif node_id == existing_order.receiver_location:
                        # Delivery
                        current_load -= existing_order.quantity
            
            # If reached here and didn't deliver, means it didn't pass through receiver
            # Calculate time with pending orders
            if not new_order_delivered:
                future_time = await self.calculate_future_delivery_time(new_order)
                return False, future_time
            
            # If delivered, return success (shouldn't reach here as it returns in loop)
            return True, delivery_time
        
        async def calculate_future_delivery_time(self, order: Order) -> float:
            """
            Calculates delivery time for order that doesn't fit in current route.
            
            When an order cannot be fit into the current route (due to overflow or
            because it doesn't pass through sender), this method estimates how long it will take
            to deliver it after completing all current tasks.
            
            Strategy:
                1. Determines final location of current route (last node)
                2. Creates list with pending_orders + new order
                3. Executes A* from final location with all orders
                4. Adds remaining time of current route to A* time
            
            Args:
                order: Order to calculate future delivery time for.
            
            Returns:
                Total time in seconds = current_route_time + future_A*_time
            
            Example:
                >>> future_time = await self.calculate_future_delivery_time(order)
                >>> print(f"Order will be delivered in {future_time}s (after current tasks)")
            
            Note:
                - Uses A* to optimize future route with multiple orders
                - Considers capacity and fuel in optimization
                - If actual_route is empty, uses current_location as start
            """
            # Determine where the vehicle will be when finishing current route
            if self.agent.actual_route:
                final_location = self.agent.actual_route[-1][0]  # Last node_id of the route
            else:
                final_location = self.agent.current_location
            
            # Create list with pending_orders + new order
            future_orders = self.agent.pending_orders.copy()
            future_orders.append(order)
            
            # Calculate optimal route with A* from the last point
            
            route, total_time, _ = A_star_task_algorithm(
                self.agent.map,
                final_location,
                future_orders,
                self.agent.capacity,
                self.agent.max_fuel
            )
            # Add remaining time to finish current route
            current_route_time = self.agent.time_to_finish_task
            
            return current_route_time + total_time       
    
    class WaitConfirmationBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour that awaits confirmation from warehouses to accept orders.
        
        After sending a proposal (vehicle-proposal), the vehicle awaits the warehouse's
        decision. This behaviour processes the response and:
        - If confirmed + can_fit: adds to current route (orders) and recalculates
        - If confirmed + !can_fit: adds to pending_orders for future execution
        - If rejected: discards the order
        - Updates presence to AWAY when accepting first order
        
        FIPA Protocol Implementation:
            This behaviour implements the ACCEPT-PROPOSAL/REJECT-PROPOSAL stage of
            the FIPA Contract Net Protocol:
            - Receives ACCEPT-PROPOSAL as "order-confirmation" with confirmed=true
            - Receives REJECT-PROPOSAL as "order-confirmation" with confirmed=false
            - Commits to order execution if accepted
            - Cleans up pending state if rejected
        
        Expected Message Format:
            - Metadata: performative="order-confirmation" (FIPA ACCEPT/REJECT)
            - Body (JSON): {
                "orderid": int,
                "confirmed": bool
              }
        
        Validations:
            - Checks if orderid is in pending_confirmations
            - Verifies sender is the correct warehouse
        
        Side Effects:
            - Modifies self.agent.orders or self.agent.pending_orders
            - Updates self.agent.actual_route via recalculate_route()
            - Changes presence to AWAY (busy with tasks)
            - Removes order from pending_confirmations
        
        Note:
            - Only processes if there are pending_confirmations (avoids empty loops)
            - Timeout of 1s + sleep(0.1) to save CPU
        """
        
        async def run(self):
            """
            Main execution loop for processing order confirmations from warehouses.
            """
            # Only process if there are pending confirmations
            if not self.agent.pending_confirmations:
                await asyncio.sleep(0.1)
                return
            
            # Try to receive confirmation from warehouse
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    orderid = data.get("orderid")
                    
                    # Check if this order is in pending confirmations
                    if orderid not in self.agent.pending_confirmations:
                        print(f"[{self.agent.name}] Confirmation received for unknown order: {orderid}")
                        return
                    
                    # Get pending order information
                    pending_info = self.agent.pending_confirmations[orderid]
                    order = pending_info["order"]
                    can_fit = pending_info["can_fit"]
                    sender_jid = pending_info["sender_jid"]
                    
                    # Check if sender is correct
                    if str(msg.sender) != sender_jid:
                        print(f"[{self.agent.name}] Confirmation from incorrect sender for order {orderid}")
                        return
                    
                    confirmation = data.get("confirmed", False)
                    print(f"[{self.agent.name}] Confirmation received for order {orderid}: {confirmation}")
                    
                    # Process confirmation
                    if confirmation:
                        if can_fit:
                            # Add to orders (current route)
                            self.agent.orders.append(order)
                            await self.recalculate_route()
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] Order {order.orderid} accepted and added to orders")
                        else:
                            # Add to pending_orders (execute later)
                            self.agent.pending_orders.append(order)
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] Order {order.orderid} accepted and added to pending_orders")
                        
                        # Update presence to AWAY (busy with tasks)
                        self.agent.presence.set_presence(
                            presence_type=PresenceType.AVAILABLE, 
                            show=PresenceShow.AWAY, 
                            status="Busy with tasks"
                        )
                        if not self.agent.next_node and self.agent.actual_route:
                            self.agent.next_node = self.agent.actual_route[1][0]
                        
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] Status changed to AWAY - has pending tasks")
                            print(f"[{self.agent.name}] Current route: {self.agent.actual_route}")
                    else:
                        print(f"[{self.agent.name}] Order {order.orderid} rejected by warehouse")
                    
                    # Remove from pending confirmations dictionary
                    del self.agent.pending_confirmations[orderid]
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Order {orderid} removed from pending confirmations. Remaining: {len(self.agent.pending_confirmations)}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Error processing confirmation: {e}")
            else:
                pass  # No message received, wait for next cycle
        
        async def recalculate_route(self):
            """
            Recalculates the optimized route with all current orders using A*.
            
            Identical to the method in ReceiveOrdersBehaviour. Recalculates the optimal path
            to minimize total time considering all accepted orders.
            
            Side Effects:
                - self.agent.actual_route: Updated with new sequence
                - self.agent.time_to_finish_task: Updated with total time
            
            Note:
                Duplicated code - consider refactoring to a method of Veiculo class.
            """
            if self.agent.orders:
                route, time , _ = A_star_task_algorithm(
                    self.agent.map,
                    self.agent.current_location,
                    self.agent.orders,
                    self.agent.capacity,
                    self.agent.max_fuel
                )
                self.agent.actual_route = route
                self.agent.time_to_finish_task = time
    
    class ReceivePickupConfirmation(CyclicBehaviour):
        """
        Cyclic behaviour to receive pickup confirmations from suppliers.
        
        This behaviour processes acknowledgment messages from suppliers confirming
        that the vehicle has successfully picked up goods. This implements the
        FIPA inform performative for unidirectional status updates.
        
        FIPA Protocol Implementation:
            - Receives INFORM messages with performative="pickup-confirm"
            - Logs confirmation for tracking and debugging purposes
            - No response required (one-way notification)
        
        Expected Message Format:
            - Metadata: performative="pickup-confirm" (FIPA INFORM)
            - Body (JSON): {
                "orderid": int
              }
        
        Note:
            Currently only logs the confirmation. Could be extended to update
            internal state or trigger additional behaviours.
        """
        async def run(self):
            """Main loop for receiving pickup confirmations."""
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    orderid = data.get("orderid")
                    
                    print(f"[{self.agent.name}] ✅ Pickup confirmation received from supplier {msg.sender} for order {orderid}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Error processing pickup confirmation: {e}")
    
    class ReceiveDeliveryConfirmation(CyclicBehaviour):
        """
        Cyclic behaviour to receive delivery confirmations from warehouses/stores.
        
        This behaviour processes acknowledgment messages from destination agents
        (warehouses or stores) confirming that goods have been successfully delivered.
        Implements FIPA inform performative for one-way notifications.
        
        FIPA Protocol Implementation:
            - Receives INFORM messages with performative="delivery-confirm"
            - Logs confirmation for tracking and auditing
            - No response required (acknowledgment only)
        
        Expected Message Format:
            - Metadata: performative="delivery-confirm" (FIPA INFORM)
            - Body (JSON): {
                "orderid": int
              }
        
        Note:
            Currently only logs the confirmation. Could be extended to update
            delivery statistics or trigger completion workflows.
        """
        async def run(self):
            """Main loop for receiving delivery confirmations."""
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    orderid = data["orderid"]
                    print(f"[{self.agent.name}] ✅ Delivery confirmation received from {msg.sender} for order {orderid}")
                    
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[{self.agent.name}] Error processing delivery confirmation: {e}")
    
    class MovementBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour that processes movement and arrival events from the event agent.
        
        This is the most complex behaviour, responsible for:
        - Processing "arrival" events (arrival at a node)
        - Processing "Transit" events (traffic updates)
        - Simulating movement during time intervals
        - Managing pickup and delivery of orders
        - Recalculating routes when necessary
        - Notifying warehouses about order status
        
        FIPA Protocol Implementation:
            This behaviour implements the INFORM receiver role:
            - Receives INFORM messages from event agent with simulation updates
            - Sends INFORM messages to warehouses/suppliers about order status
            - Uses inform performative for all status notifications
        
        Types of Events Processed:
            1. "arrival" + vehicle match (FIPA INFORM):
                - Processes arrival at node (pickup or delivery)
                - Removes node from actual_route
                - Processes multiple tasks at same node consecutively
                - If route empty: moves pending_orders to orders or becomes CHAT
                - Notifies event agent of time to next node
            
            2. "Transit" (FIPA INFORM):
                - Updates edge weights in graph with new traffic data
                - Recalculates times considering new traffic
            
            3. Other (movement during transit):
                - Simulates movement along route with available time
                - Updates current_location based on elapsed time
        
        Arrival Processing Flow:
            1. Pop first node from actual_route
            2. Call process_node_arrival() for pickup/delivery
            3. Loop: process consecutive equal nodes (multiple tasks)
            4. If route empty → check pending_orders or become available
            5. Calculate next node and notify event agent
        
        Expected Message Format:
            - Metadata: performative="inform" (FIPA INFORM)
            - Body (JSON): {
                "type": "arrival" | "Transit" | others,
                "time": float,
                "vehicles": list[str] (for arrival),
                "data": {...} (for Transit)
              }
        
        Note:
            - Only processes if presence = AWAY (busy)
            - Timeout of 5s to not miss important events
            - Automatic refueling at pickups/deliveries
        """

        async def run(self):
            """
            Main execution loop for processing movement and arrival events.
            
            Continuously receives messages from event agent and processes them based on type.
            """
            # Check if vehicle is busy (AWAY = has tasks)

            
            msg = await self.receive(timeout=5)  # Longer timeout to not miss messages

            presence_show = self.agent.presence.get_show()
            
            if presence_show == PresenceShow.CHAT:
                print(f"[{self.agent.name}] Vehicle available - ignoring movement messages")
                # Vehicle available (no tasks) - does not process movement messages
            if msg:
                # Print received message
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Message received in MovementBehaviour")
                if self.agent.verbose:
                    print(f"  Body: {msg.body}")
                    print(f"  Metadata: {msg.metadata}")
                    
                data = json.loads(msg.body)
                type = data.get("type")
                time = data.get("time")
                vehicles = data.get("vehicles", [])  # New vehicles list
                
                # Check if this vehicle is in the vehicles list
                is_for_this_vehicle = self.agent.name in vehicles
                if self.agent.verbose:
                    print (f"[{self.agent.name}] is_for_this_vehicle: {is_for_this_vehicle} (vehicles={vehicles})")
                if type == "arrival" and is_for_this_vehicle:
                    # Arrived at a node - process arrival
                    self.agent.current_location, order_id = self.agent.actual_route.pop(0)
                    if not order_id:
                        self.agent.current_location, order_id = self.agent.actual_route.pop(0)
                    # Process the first task at the node
                    await self.process_node_arrival(self.agent.current_location, order_id)
                    
                    # Process all consecutive equal nodes (multiple tasks at same location)
                    while self.agent.actual_route and self.agent.actual_route[0][0] == self.agent.current_location:
                        # Next item in route is at same node - process immediately
                        next_location, next_order_id = self.agent.actual_route.pop(0)
                        await self.process_node_arrival(next_location, next_order_id)
                    
                    # Check if current route is finished
                    if not self.agent.actual_route:
                        if len(self.agent.pending_orders) == 0:
                            # No more tasks - become available
                            self.agent.presence.set_presence(
                                presence_type=PresenceType.AVAILABLE,
                                show=PresenceShow.CHAT,
                                status="Available for new orders"
                            )
                            
                            self.agent.next_node = None
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] Status changed to AVAILABLE - no tasks")
                                print(f"[{self.agent.name}] All tasks completed. Vehicle now available.")
                                print(f"[{self.agent.name}] Presence updated to AVAILABLE {self.agent.presence.get_show()}.")
                            return 
                            
                            
                        
                        # There are pending orders - calculate new route
                        self.agent.actual_route, _, _ = A_star_task_algorithm(
                            self.agent.map, 
                            self.agent.current_location,
                            self.agent.pending_orders,
                            self.agent.capacity,
                            self.agent.max_fuel
                        )
                        # Move pending orders to orders
                        self.agent.orders = self.agent.pending_orders.copy()
                        self.agent.pending_orders = []
                        self.agent.next_node = self.agent.actual_route[1][0]
                    else:
                        # Define next node
                        if self.agent.actual_route[0][0] == None:
                            self.agent.next_node = self.agent.actual_route[1][0]
                        else:
                            self.agent.next_node = self.agent.actual_route[0][0]
                elif presence_show == PresenceShow.AWAY: 
                    # Movement during transit
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Movement during transit")
                        print(f"[{self.agent.name}] Available time to move: {time}")
                        print(f"[{self.agent.name}] Current location before moving: {self.agent.current_location}")
                    temp_location = self.agent.current_location
                    self.agent.current_location = await self.update_location_and_time(time)
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Current location after moving: {self.agent.current_location}")
                    _, _, simulated_time = self.agent.map.djikstra(temp_location, self.agent.current_location)
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] Simulated time to move: {simulated_time}")
                    
                if type == "Transit":
                    if self.agent.verbose:
                        print("Update traffic")
                    # Update map with new traffic information
                    await self.update_map(data.get("data"))
                
                # Calculate and notify remaining time
                # DO NOT notify if:
                # 1. Simulated time is 0 AND (event is Transit OR not in vehicles list)
                should_notify = True
                if time == 0 and type == "Transit":
                    should_notify = False
                    #print(f"[{self.agent.name}] ⚠️  Notification ignored (time=0 and type={type}, is_for_this_vehicle={is_for_this_vehicle})")
                if self.agent.verbose:
                    print(f"[{self.agent.name}] should_notify: {should_notify}, next_node: {self.agent.next_node}, route: {self.agent.actual_route}")
                if should_notify and self.agent.next_node:
                    _, _, time_left = self.agent.map.djikstra(
                        self.agent.current_location,
                        self.agent.next_node
                    )
                    print(f"[{self.agent.name}] Notifying event agent from {self.agent.current_location} - time to next node ({self.agent.next_node}): {time_left}")
                    await self.notify_event_agent(time_left, self.agent.next_node)
        
        async def process_node_arrival(self, node_id: int, order_id: int):
            """
            Processes vehicle arrival at a node - pickup or delivery.
            
            Determines if the node corresponds to the sender (pickup) or receiver (delivery)
            of the order. Updates vehicle load, fuel, order state and XMPP presence.
            Notifies the warehouse about status changes.
            
            Decision Logic:
                - If node_id == sender_location and !comecou → PICKUP
                  * Increments current_load
                  * Marks order.comecou = True
                  * Changes presence to AWAY with specific status
                  * Notifies warehouse with "order-started"
                
                - If node_id == receiver_location and comecou → DELIVERY
                  * Decrements current_load
                  * Removes order from self.agent.orders
                  * Notifies warehouse with "order-completed"
                
                - Both cases: Refuel (current_fuel = max_fuel)
            
            Args:
                node_id: ID of the node where the vehicle arrived.
                order_id: ID of the order associated with this node in the route.
            
            Side Effects:
                - Modifies self.agent.current_load
                - Modifies self.agent.current_fuel (refuel)
                - Modifies order.comecou
                - Removes order from self.agent.orders (on delivery)
                - Updates XMPP presence
                - Sends messages to warehouse
            
            Example:
                >>> await self.process_node_arrival(node_id=5, order_id=42)
                # If node 5 is sender of order 42:
                # [vehicle1] PICKUP - Order 42 at 5
                # [vehicle1] Status changed to AWAY - processing order 42
            
            Note:
                - If order_id is None or order doesn't exist in orders, returns without action
                - Refueling is instantaneous in both cases
            """
            if not order_id:
                return
            
            # Find the corresponding order
            order = None
            for o in self.agent.orders:
                if o.orderid == order_id:
                    order = o
                    break
            
            if not order:
                return
            
            # Check if it's pickup (sender_location)
            if node_id == order.sender_location and not order.comecou:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] PICKUP - Order {order.orderid} at {node_id}")
                
                # Update load
                self.agent.current_load += order.quantity
                
                # Refuel
                self.agent.current_fuel = self.agent.max_fuel
                
                # Mark order as started
                order.comecou = True
                
                # Change status to AWAY (busy with task)
                self.agent.presence.set_presence(
                    presence_type=PresenceType.AVAILABLE,
                    show=PresenceShow.AWAY,
                    status=f"Delivering order {order.orderid}"
                )
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Status changed to AWAY - processing order {order.orderid}")
                
                # Notify supplier that pickup was made
                await self.notify_supplier_pickup(order)
                
                # Notify warehouse that delivery started
                await self.notify_warehouse_start(order)
                
            # Check if it's delivery (receiver_location)
            elif node_id == order.receiver_location and order.comecou:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] DELIVERY - Order {order.orderid} at {node_id}")
                
                # Update load
                self.agent.current_load -= order.quantity
                
                # Refuel
                self.agent.current_fuel = self.agent.max_fuel
                
                # Remove order from list
                self.agent.orders.remove(order)
                
                # Notify warehouse that delivery was completed
                await self.notify_warehouse_complete(order)
        
        async def notify_supplier_pickup(self, order: Order):
            """
            Notifies the supplier that the vehicle has picked up the order.
            
            Sends a FIPA INFORM message to the supplier agent confirming that goods
            have been collected from their location. The supplier is identified by
            the order's sender_location converted to a JID.
            
            Args:
                order: Order that was picked up.
            
            Message Sent:
                - To: supplier{sender_location}@localhost
                - Metadata: performative="vehicle-pickup" (FIPA INFORM)
                - Body (JSON): Full order details including product, quantity, locations
            
            Note:
                The order sender is the warehouse, but pickup is at the supplier.
                We need to identify the supplier by location.
            """
            # The order sender is the warehouse, but pickup is at the supplier
            # We need to identify the supplier by location
            supplier_location = order.sender_location
            
            # Build supplier JID based on location
            supplier_jid = f"supplier{supplier_location}@localhost"
            
            msg = Message(to=supplier_jid)
            msg.set_metadata("performative", "vehicle-pickup")
            msg.set_metadata("supplier_id", supplier_jid)
            msg.set_metadata("vehicle_id", str(self.agent.jid))
            msg.set_metadata("order_id", str(order.orderid))
            
            order_dict = {
                "product": order.product,
                "quantity": order.quantity,
                "orderid": order.orderid,
                "sender": order.sender,
                "receiver": order.receiver,
                "sender_location": order.sender_location,
                "receiver_location": order.receiver_location
            }
            msg.body = json.dumps(order_dict)
            await self.send(msg)
            print(f"[{self.agent.name}] Notified supplier {supplier_jid}: pickup order {order.orderid}")
        
        async def notify_warehouse_start(self, order: Order):
            """
            Notifies the warehouse that the order started being processed (pickup made).
            
            Sends a FIPA-ACL message to the sending warehouse informing that the vehicle
            picked up the load and started delivery.
            
            Args:
                order: Order that was started.
            
            Message Sent:
                - To: order.sender (warehouse JID)
                - Metadata: performative="vehicle-pickup", type="order-started" (FIPA INFORM)
                - Body (JSON): {
                    "orderid": int,
                    "vehicle_id": str,
                    "status": "started",
                    "location": int
                  }
            """
            msg = Message(to=order.sender)
            msg.set_metadata("performative", "vehicle-pickup")
            msg.set_metadata("type", "order-started")
            
            data = {
                "orderid": order.orderid,
                "vehicle_id": str(self.agent.jid),
                "status": "started",
                "location": self.agent.current_location,
                }
            msg.body = json.dumps(data)
            await self.send(msg)
            print(f"[{self.agent.name}] Notified {order.sender}: order {order.orderid} started")
        
        async def notify_warehouse_complete(self, order: Order):
            """
            Notifies the warehouse that the order was completed (delivery made).
            
            Sends a FIPA-ACL message to the destination warehouse/store informing that
            the delivery was successfully completed.
            
            Args:
                order: Order that was completed.
            
            Message Sent:
                - To: order.receiver (store/warehouse JID)
                - Metadata: performative="vehicle-delivery" (FIPA INFORM)
                - Body (JSON): {
                    "orderid": int,
                    "vehicle_id": str,
                    "status": "completed",
                    "location": int,
                    "time": float
                  }
            """
            msg = Message(to=order.receiver)
            msg.set_metadata("performative", "vehicle-delivery")
            
            data = {
                "orderid": order.orderid,
                "vehicle_id": str(self.agent.jid),
                "status": "completed",
                "location": self.agent.current_location,
                "time": order.deliver_time    
            }
            msg.body = json.dumps(data)
            await self.send(msg)
            print(f"[{self.agent.name}] Notified {order.receiver}: order {order.orderid} completed")
        
        async def notify_event_agent(self, time_left: float, next_node: int):
            """
            Notifies the event agent about remaining time until the next node.
            
            Informs the event agent how long the vehicle will take to reach the
            next node in the route. The event agent uses this information to schedule
            "arrival" events in the simulation.
            
            Args:
                time_left: Time in seconds until reaching the next node.
                next_node: ID of the next destination node.
            
            Message Sent:
                - To: self.agent.event_agent_jid
                - Metadata: performative="inform", type="time-update"
                - Body (JSON): {
                    "vehicle_id": str,
                    "current_location": int,
                    "next_node": int,
                    "time_left": float
                  }
            
            Note:
                - Only sends if event_agent_jid is configured
                - Returns silently if attribute doesn't exist
            """
            
            msg = Message(to=self.agent.event_agent_jid)
            msg.set_metadata("performative", "inform")
            msg.set_metadata("type", "time-update")
            
            data = {
                "type": "arrival",
                "vehicle_id": str(self.agent.jid),
                "current_location": self.agent.current_location,
                "next_node": next_node,
                "time": time_left,
            }
            msg.body = json.dumps(data)
            await self.send(msg)
        
        async def update_map(self, traffic_data: dict):
            """
            Updates the graph with new traffic data received from the event agent.
            
            Processes "Transit" events that contain information about edge weight changes
            (representing congestion, roadwork, etc.). Updates edge weights in the
            vehicle's graph.
            
            Args:
                traffic_data: Dictionary with structure:
                  {
                      "edges": [
                          {
                              "node1": int,
                              "node2": int,
                              "weight": float (new weight)
                          },
                          ...
                      ]
                  }
            
            Side Effects:
                Modifies self.agent.map.edges - updates edge weights.
            
            Example:
                >>> traffic_data = {
                ...     "edges": [
                ...         {"node1": 3, "node2": 7, "weight": 25.5},
                ...         {"node1": 7, "node2": 9, "weight": 18.3}
                ...     ]
                ... }
                >>> await self.update_map(traffic_data)
                # [vehicle1] Map updated with new traffic data
            
            Note:
                - If traffic_data is None or empty, returns without action
                - Uses map.get_edge() to find bidirectional edge
                - Does not automatically recalculate route (consider implementing)
            """

            if not traffic_data:
                return
            
            # Update edge weights based on traffic data
            for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge = self.agent.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight
            if self.agent.verbose:
                print(f"[{self.agent.name}] Map updated with new traffic data") 
                

        async def update_location_and_time(self, time_left):
            """
            Updates vehicle location based on available movement time.
            
            Simulates vehicle movement along the route between current_location and
            next_node during a time interval. If available time is sufficient, the
            vehicle advances to the next node; otherwise, stays at current node
            (discrete movement between vertices).
            
            Algorithm:
                1. Calculates route from current_location to next_node using Dijkstra
                2. Converts route from Node objects to ID list
                3. Iterates through route sequentially:
                   - For each edge, gets required time (edge.weight)
                   - If remaining_time >= edge_time: move to next node
                   - If remaining_time < edge_time: stay at current node
                4. Returns new location
            
            Args:
                time_left: Available time for movement (in seconds).
            
            Returns:
                ID of the node where the vehicle is after simulating movement.
            
            Example:
                >>> # Vehicle at node 3, next_node = 7, available time = 15s
                >>> # Route: 3 → 5 (10s) → 7 (8s)
                >>> new_location = await self.update_location_and_time(15.0)
                >>> print(new_location)  # 5 (reached node 5, but not 7)
            
            Side Effects:
                None - method is pure, does not modify vehicle state.
                Caller (run) is responsible for updating current_location.
            
            Note:
                - Movement is discrete (only stops at vertices, not on edges)
                - If insufficient time for any edge, stays at current node
                - Considers next_node from actual_route[0] or actual_route[1] if [0] has order=None
            """
            next_node_id, order = self.agent.actual_route[0]
            if order is None:
                next_node_id = self.agent.actual_route[1][0]
            route_nodes, _ , _ = self.agent.map.djikstra(self.agent.current_location, next_node_id)
            
            # Convert route from Node objects to IDs
            route = [node.id for node in route_nodes] if route_nodes else []
            
            remaining_time = time_left
            current_pos = self.agent.current_location
            route_index = 0
            
            # Iterate through route while time is available
            while route_index < len(route) and remaining_time > 0:
                next_node_id = route[route_index]
                if self.agent.verbose:
                    print(f"[{self.agent.name}] Current route: {route}")
                    print(f"[{self.agent.name}] Trying to move to node {next_node_id} with remaining time {remaining_time}")
                if current_pos == next_node_id:
                    route_index += 1
                    continue
                
                # Get edge between current_pos and next_node_id
                edge = self.agent.map.get_edge(current_pos, next_node_id)
                
                if edge is None:
                    # If no edge, stop
                    break
                
                # Time required to traverse this edge
                edge_time = edge.weight  # assuming weight is time
                if self.agent.verbose: 
                    print(f"[{self.agent.name}] Time required for edge {current_pos} -> {next_node_id}: {edge_time}")
                
                if remaining_time >= edge_time:
                    # Sufficient time to reach next node
                    current_pos = next_node_id
                    remaining_time -= edge_time
                    route_index += 1
                else:
                    # Insufficient time - stay at current node
                    break
            
            return current_pos

    class PresenceInfoBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour that responds to presence information requests.
        
        This behaviour waits for messages with performative="presence-info" and responds
        with the vehicle's current presence information (status and availability).
        
        FIPA Protocol Implementation:
            This behaviour implements the QUERY responder role:
            - Receives QUERY messages requesting presence information
            - Sends INFORM messages with current vehicle state
        
        Received Message Format:
            - Metadata: performative="presence-info"
            - Body: Any content (ignored)
        
        Response Message Format:
            - Metadata: performative="presence-response"
            - Body (JSON): {
                "vehicle_id": str (vehicle JID),
                "presence_type": str (AVAILABLE, UNAVAILABLE, etc.),
                "presence_show": str (CHAT, AWAY, DND, XA),
                "status": str (status message),
                "current_location": int,
                "current_load": int,
                "current_fuel": int,
                "active_orders": int,
                "pending_orders": int
              }
        
        Use Case:
            Other agents (warehouse, monitoring systems) can query vehicle status
            to make informed decisions about task assignment.
        
        Note:
            - Always responds to message sender
            - Timeout of 1s to avoid excessive CPU usage
        """
        
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 📩 Presence request received from {msg.sender}")
                
                # Get current presence information
                presence_type = self.agent.presence.get_presence().type
                presence_show = self.agent.presence.get_show()
                presence_status = self.agent.presence.get_status()
                
                # Create response with presence and vehicle state information
                reply = msg.make_reply()
                reply.set_metadata("performative", "presence-response")
                reply.set_metadata("vehicle_id", str(self.agent.jid))
                
                response_data = {
                    "vehicle_id": str(self.agent.jid),
                    "presence_type": str(presence_type),
                    "presence_show": str(presence_show),
                    "status": presence_status if presence_status else "No status",
                    "current_location": self.agent.current_location,
                    "current_load": self.agent.current_load,
                    "current_fuel": self.agent.current_fuel,
                    "active_orders": len(self.agent.orders),
                    "pending_orders": len(self.agent.pending_orders)
                }
                
                reply.body = json.dumps(response_data)
                
                await self.send(reply)
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ✅ Presence response sent to {msg.sender}")
                    print(f"  Status: {presence_show}, Location: {self.agent.current_location}, Active orders: {len(self.agent.orders)}")

                                     