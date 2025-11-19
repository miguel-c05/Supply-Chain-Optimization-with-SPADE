"""
Supplier Agent Module for Supply Chain Optimization System.

This module implements the Supplier agent, which provides infinite inventory to warehouses
in the supply chain. The Supplier serves as the ultimate source of materials, responding
to warehouse purchase requests and coordinating vehicle delivery logistics.

The module implements the FIPA Contract Net Protocol as a **Participant** role:
- **Responds** to warehouse purchase requests (warehouse-buy CFP)
- **Proposes** materials (supplier-accept)
- **Receives awards** (warehouse-confirm) or rejections (warehouse-deny)
- **Coordinates vehicles** for delivery to warehouses

Key Features:
    - Infinite stock of all products (never runs out)
    - Concurrent request handling from multiple warehouses
    - Vehicle coordination for material delivery
    - Order tracking through pending_deliveries system

Typical usage example:
    ```python
    from world.graph import Graph
    
    # Initialize graph and supplier agent
    map_graph = Graph()
    supplier = Supplier(
        jid="supplier1@localhost",
        password="supplier_password",
        map=map_graph,
        node_id=20,
        contact_list=["warehouse1@localhost", "vehicle1@localhost"],
        verbose=True
    )
    await supplier.start()
    ```
"""

import asyncio
import random
import queue
import json
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template
from spade.presence import PresenceShow, Contact, PresenceInfo
from world.graph import Graph, Node, Edge
from veiculos.veiculos import Order

class Supplier(Agent):
    """
    Supplier Agent for Supply Chain Management System.
    
    The Supplier agent acts as the ultimate source of materials in the supply chain,
    providing infinite inventory to warehouses. It implements the FIPA Contract Net
    Protocol as a **Participant**, responding to warehouse requests and coordinating
    vehicle deliveries.
    
    FIPA Contract Net Protocol - Participant Role Implementation:
    
    **As Participant (with Warehouses)**:
        - **Proposal Phase**: Receives warehouse-buy CFP from warehouses
        - **Proposal Submission**: Always sends supplier-accept (has infinite stock)
        - **Result Reception**: Receives warehouse-confirm (accept-proposal) or warehouse-deny (reject-proposal)
        - **Execution**: Coordinates vehicle delivery for confirmed orders
    
    Infinite Stock Model:
        Unlike Store and Warehouse agents, the Supplier has unlimited inventory:
        - Never rejects requests due to insufficient stock
        - Always responds with supplier-accept (FIPA propose)
        - Tracks total supplied quantities for statistics only
        - No stock locking or capacity constraints
    
    Order Lifecycle:
        1. **Request Reception**: Warehouse sends warehouse-buy (FIPA CFP)
        2. **Automatic Acceptance**: Supplier sends supplier-accept (FIPA propose)
        3. **Awaiting Award**: Wait for warehouse decision (10 second timeout)
        4. **Confirmation**: Warehouse sends warehouse-confirm (FIPA accept-proposal)
        5. **Vehicle Assignment**: Launch AssignVehicle to coordinate delivery
        6. **Delivery Tracking**: Order added to pending_deliveries
        7. **Pickup**: Vehicle picks up materials from supplier
        8. **Completion**: Order removed from pending_deliveries
    
    ID Encoding System:
        Uses hierarchical encoding for generating unique request identifiers:
        - Formula: `agent_type * 100_000_000 + instance_id * 1_000_000 + request_counter`
        - Agent type code for Supplier: 3
        - Example: supplier1's base ID = 3_001_000_000
    
    Attributes:
        jid (str): Jabber ID of the supplier agent (e.g., "supplier1@localhost").
        node_id (int): Graph node ID representing the supplier's physical location.
        map (Graph): Reference to the world graph for pathfinding calculations.
        contact_list (list[str]): JIDs for warehouses and vehicles.
        verbose (bool): Flag to control debug output verbosity.
        id_base (int): Base value for generating unique request IDs.
        total_supplied (dict[str, int]): Cumulative quantities supplied per product.
            Format: {product: total_quantity_supplied}
        pending_deliveries (dict[int, Order]): Confirmed orders awaiting vehicle pickup.
            Format: {order_id: Order object}
        vehicle_proposals (dict[int, dict[str, tuple[bool, int]]]): Vehicle delivery proposals.
            Format: {order_id: {vehicle_jid: (can_fit, delivery_time)}}
        vehicles (list[str]): List of vehicle JIDs discovered from contacts.
        presence_infos (dict[str, str]): Vehicle presence status cache.
        current_tick (int): Current simulation time, synchronized by world agent.
    
    Behaviours:
        Warehouse Interaction (FIPA Participant):
            - ReceiveBuyRequest: Processes warehouse purchase requests (FIPA CFP)
            - AcceptBuyRequest: Sends proposal to warehouse (FIPA propose)
            - ReceiveConfirmationOrDenial: Handles warehouse award/rejection
        
        Vehicle Coordination:
            - AssignVehicle: Initiates vehicle assignment for deliveries
            - ReceivePresenceInfo: Checks vehicle availability
            - ReceiveVehicleProposals: Collects vehicle delivery proposals
            - ChooseBestVehicle: Selects optimal vehicle using scoring algorithm
            - ReceiveVehicleArrival: Handles vehicle pickup notifications
        
        Time Management:
            - ReceiveTimeDelta: Synchronizes simulation time and traffic updates
    
    Message Protocols:
        Incoming from Warehouses:
            - warehouse-buy: Purchase request (FIPA CFP)
            - warehouse-confirm: Order confirmation (FIPA accept-proposal)
            - warehouse-deny: Order rejection (FIPA reject-proposal)
        
        Outgoing to Warehouses:
            - supplier-accept: Material proposal (FIPA propose)
        
        Vehicle Communication:
            - order-proposal: Request vehicle delivery quote
            - vehicle-proposal: Vehicle delivery proposal
            - order-confirmation: Confirm vehicle assignment
            - vehicle-pickup: Vehicle picks up order from supplier
            - presence-info: Request vehicle availability
            - presence-response: Vehicle availability status
    
    Usage Instructions:
        **For Vehicle Integration**:
            - All vehicles must subscribe to all suppliers (mutual presence subscription)
            - Vehicles access pending orders via `supplier_agent.pending_deliveries.values()`
            - Vehicle pickup removes order from pending_deliveries
        
        **For Warehouse Integration**:
            - Warehouses send warehouse-buy requests to supplier
            - Supplier always accepts (infinite stock)
            - Warehouse selects winning supplier based on delivery time
    
    Example:
        ```python
        supplier = Supplier(
            jid="supplier1@localhost",
            password="password",
            map=world_graph,
            node_id=20,
            contact_list=["warehouse1@localhost", "vehicle1@localhost"],
            verbose=True
        )
        await supplier.start()
        
        # Access statistics
        print(supplier.total_supplied)  # {'electronics': 500, 'textiles': 300}
        
        # Access pending orders (for vehicles)
        for order in supplier.pending_deliveries.values():
            print(f"Order {order.orderid}: {order.quantity}x{order.product}")
        ```
    
    Note:
        The infinite stock model simplifies the supply chain by eliminating upstream
        constraints, allowing focus on warehouse inventory management and vehicle logistics.
    """
    
    # ------------------------------------------
    #          SUPPLIER <-> WAREHOUSE
    # ------------------------------------------
    
    class ReceiveBuyRequest(CyclicBehaviour):
        """
        Cyclic behaviour that processes incoming purchase requests from warehouses.
        
        This behaviour implements the proposal phase of the FIPA Contract Net Protocol
        where the supplier acts as a **Participant**. It receives CFP messages from
        warehouses and automatically accepts all requests since the supplier has
        infinite stock.
        
        FIPA Protocol Phase: **Proposal Phase - Participant Role**
            - Role: Participant (Supplier responding to Warehouse's CFP)
            - Receives: warehouse-buy messages (FIPA CFP)
            - Evaluates: Always accepts (infinite stock model)
            - Responds: supplier-accept (FIPA propose) for every request
        
        Infinite Stock Advantage:
            Unlike warehouses that must check inventory:
            - No stock validation needed
            - No rejection logic (always accepts)
            - No stock locking mechanism required
            - Simplifies participant role implementation
        
        Message Format (warehouse-buy):
            Metadata:
                - performative: "warehouse-buy"
                - request_id: Unique request identifier
            Body:
                - Format: "{quantity} {product}"
                - Example: "100 raw_materials"
        
        Workflow:
            1. **Receive**: Wait up to 20 seconds for warehouse-buy message
            2. **Parse**: Extract request_id, quantity, product from message
            3. **Accept**: Launch AcceptBuyRequest behaviour (always accept)
            4. **Track**: Update total_supplied statistics
            5. **Continue**: Return to listening (cyclic behaviour)
        
        Statistics Tracking:
            Maintains cumulative supply counts per product:
            - Increment total_supplied[product] by quantity
            - Create entry if product not yet supplied
            - Used for monitoring and reporting only
        
        Concurrency Handling:
            - Processes multiple warehouse requests concurrently
            - Each request launches independent AcceptBuyRequest behaviour
            - No race conditions (infinite stock eliminates conflicts)
        
        Example Execution:
            ```
            Request Received: "100 electronics" (request_id=201000000)
            From: warehouse1@localhost
            Decision: ACCEPT (always)
            Actions:
                - total_supplied[electronics]: 500 -> 600
                - Launch AcceptBuyRequest
                - Print: "Request 201000000: 100 xelectronics from warehouse1 received."
            ```
        
        Timeout Behavior:
            If no message received in 20 seconds:
            - Log timeout (if verbose enabled)
            - Continue listening (cyclic behaviour doesn't terminate)
        
        Note:
            This behaviour never terminates (cyclic), continuously listening for
            warehouse requests throughout the supplier's lifecycle.
        """
        async def run(self):
            agent : Supplier = self.agent
        
            if agent.verbose:
                print("Awaiting buy request from warehouses...")
            msg = await self.receive(timeout=20)
            if msg != None:
                """
                Messages with metadata ("performative", "warehouse-buy") have body
                with the following format:
                
                "product_quantity product_type"
                
                request_id is in metadata["request_id"]
                """
                request_id = int(msg.get_metadata("request_id"))
                request = msg.body.split(" ")
                quant = int(request[0])
                product = request[1]
                # Essential print - request received
                print(f"{agent.jid}> Request {request_id}: {quant} x{product} from {msg.sender} received.")
                
                # Supplier has infinite stock - always accept
                accept_behav = agent.AcceptBuyRequest(msg)
                
                # Track total supplied (no need to lock since infinite)
                if product in agent.total_supplied:
                    agent.total_supplied[product] += quant
                else:
                    agent.total_supplied[product] = quant

                if agent.verbose:
                    print(f"Total {product} supplied: {agent.total_supplied[product]}")
                    agent.print_stats()
                
                agent.add_behaviour(accept_behav)
            else:
                if agent.verbose:
                    print(f"{agent.jid}> Did not get any buy requests in 20 seconds.")

    class AcceptBuyRequest(OneShotBehaviour):
        """
        Behaviour that sends proposal acceptance to warehouse (FIPA propose).
        
        This behaviour implements the proposal submission in the FIPA Contract Net
        Protocol where the supplier, acting as a participant, sends its proposal
        to fulfill the warehouse's request. Since the supplier has infinite stock,
        this is always an acceptance. It then sets up to receive the warehouse's
        decision (accept-proposal or reject-proposal).
        
        FIPA Protocol Phase: **Proposal Submission - Participant Role**
            - Role: Participant (Supplier proposing to Warehouse)
            - Sends: supplier-accept (FIPA propose)
            - Purpose: "I can fulfill your request" (always true for supplier)
            - Next Phase: Await warehouse's award or rejection decision
        
        Attributes:
            request_id (int): Unique identifier for this request.
            quant (int): Quantity of product being proposed.
            product (str): Name of product being proposed.
            sender (str): Warehouse JID that initiated the request.
        
        Message Format (supplier-accept):
            Metadata:
                - performative: "supplier-accept" (FIPA propose)
                - supplier_id: This supplier's JID
                - warehouse_id: Requesting warehouse's JID
                - node_id: Supplier's graph location
                - request_id: Original request identifier
            Body:
                - Format: "{quantity} {product}"
                - Example: "100 electronics"
        
        Workflow:
            1. **Log Acceptance** (verbose): Print proposal details
            2. **Construct Message**: Create supplier-accept with all metadata
            3. **Send Proposal**: Transmit to requesting warehouse
            4. **Create Listener**: Initialize ReceiveConfirmationOrDenial behaviour
            5. **Setup Template**: Configure filter for this specific negotiation
            6. **Register Listener**: Add behaviour with template to agent
            7. **Return**: Don't block (listener runs independently)
        
        Template Configuration:
            Filters messages to match:
            - supplier_id: This supplier
            - warehouse_id: Specific warehouse that made request
            - request_id: This specific request
            
            Accepts both performatives:
            - warehouse-confirm (FIPA accept-proposal)
            - warehouse-deny (FIPA reject-proposal)
        
        Non-Blocking Design:
            The commented-out `await confirm_deny_behav.join()` demonstrates
            that we intentionally DON'T wait for confirmation here. This allows
            the supplier to accept multiple warehouse requests concurrently.
        
        Example:
            ```
            Input: Warehouse request for "100 electronics"
            Proposal Sent: supplier-accept with body "100 electronics"
            Listener Setup: ReceiveConfirmationOrDenial waiting for:
                - warehouse-confirm (award) OR
                - warehouse-deny (rejection)
            Result: Supplier ready to process next request
            ```
        
        Side Effects:
            - Sends SPADE message to warehouse
            - Adds ReceiveConfirmationOrDenial behaviour to agent
            - Prints debug information if verbose enabled
        
        Note:
            Unlike warehouse AcceptBuyRequest, this never needs to lock stock
            since the supplier has infinite inventory.
        """
        def __init__(self, msg : Message):
            """
            Initialize the AcceptBuyRequest behaviour.
            
            Args:
                msg (Message): The warehouse-buy request message to accept.
            """
            super().__init__()
            self.request_id = int(msg.get_metadata("request_id"))
            request = msg.body.split(" ")
            self.quant = int(request[0])
            self.product = request[1]
            self.sender = msg.sender
        
        async def run(self):
            agent : Supplier = self.agent
            
            if agent.verbose:
                print(
                    f"{agent.jid}> Accepted a request from {self.sender}: "
                    f"id={self.request_id} "
                    f"quant={self.quant} "
                    f"product={self.product}"
                )
            
            
            msg = Message(to=self.sender)
            msg.set_metadata("performative", "supplier-accept")
            msg.set_metadata("supplier_id", str(agent.jid))
            msg.set_metadata("warehouse_id", str(self.sender))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quant} {self.product}"
            
            if agent.verbose:
                print(f"{agent.jid}> Sending supplier-accept message to {self.sender}")
                print(f"{agent.jid}> Message metadata: warehouse_id={self.sender}, request_id={self.request_id}")
            
            await self.send(msg)
            if agent.verbose:
                print(f"{agent.jid}> Message sent successfully!")
            
            # Wait for either confirmation or denial
            confirm_deny_behav = agent.ReceiveConfirmationOrDenial(msg, self.sender)
            
            # Template that matches BOTH warehouse-confirm AND warehouse-deny
            template = Template()
            template.set_metadata("supplier_id", str(agent.jid))
            template.set_metadata("warehouse_id", str(self.sender))
            template.set_metadata("request_id", str(self.request_id))
            
            agent.add_behaviour(confirm_deny_behav, template)
            if agent.verbose:
                print(f"{agent.jid}> AcceptBuyRequest finished, now waiting for confirmation or denial...")
            
            # Aguardar a confirmação ser recebida antes de terminar
            # await confirm_deny_behav.join()
            
    
    class ReceiveConfirmationOrDenial(OneShotBehaviour):
        """
        Behaviour that processes warehouse's award or rejection decision (FIPA result notification).
        
        This behaviour implements the result notification reception in the FIPA Contract Net
        Protocol where the supplier, acting as a participant, receives the warehouse's final
        decision about whether its proposal was accepted or rejected.
        
        FIPA Protocol Phase: **Result Notification Reception - Participant Role**
            - Role: Participant (Supplier receiving Warehouse's decision)
            - Receives: warehouse-confirm (FIPA accept-proposal) or warehouse-deny (FIPA reject-proposal)
            - Actions:
                - If confirm: Add order to pending_deliveries, assign vehicle
                - If deny: Log rejection (no rollback needed - infinite stock)
                - If timeout: Log timeout (warehouse chose another supplier)
        
        Order State Transitions:
        
            **On warehouse-confirm (Award)**:
                1. Convert message to Order object
                2. pending_deliveries[order_id] = order
                3. Launch AssignVehicle behaviour
                4. Print confirmation message
            
            **On warehouse-deny or timeout (Rejection/Timeout)**:
                1. Log rejection/timeout (if verbose)
                2. No state changes needed (infinite stock)
                3. No further action required
        
        Attributes:
            accepted_id (int): Request ID for which we sent proposal.
            accepted_quantity (int): Quantity that was proposed.
            accepted_product (str): Product that was proposed.
            sender_jid (str): Warehouse JID that will send decision.
        
        Timeout Mechanism:
            - Wait time: 10 seconds
            - Interpretation: Warehouse chose another supplier (implicit rejection)
            - Action: Log only (no stock to unlock)
        
        Example Execution:
        
            **Scenario 1: Warehouse Confirms**
            ```
            Proposed: 100 electronics
            Message Received: warehouse-confirm "100 electronics"
            Actions:
                - Create Order object
                - pending_deliveries[301000000] = Order(...)
                - Launch AssignVehicle(301000000)
                - Print: "Order 301000000 confirmed: 100 xelectronics for warehouse1"
            ```
            
            **Scenario 2: Warehouse Denies**
            ```
            Proposed: 100 electronics
            Message Received: warehouse-deny "100 electronics"
            Actions:
                - Print: "Denial received! Warehouse chose another supplier."
                - No state changes (infinite stock)
            ```
            
            **Scenario 3: Timeout**
            ```
            Proposed: 100 electronics
            Message Received: None (10 second timeout)
            Actions:
                - Print: "Timeout: No confirmation or denial received"
                - Print: "Order not confirmed for electronics x100"
                - No state changes (infinite stock)
            ```
        
        Difference from Warehouse Behaviour:
            Unlike warehouse ReceiveConfirmationOrDenial:
            - No stock unlocking needed (infinite inventory)
            - No capacity adjustments required
            - Simpler state management
            - Only tracks confirmed orders in pending_deliveries
        
        Note:
            This behaviour is automatically filtered by template to only receive
            messages for the specific supplier, warehouse, and request_id combination.
        """
        def __init__(self, accept_msg : Message, sender_jid):
            """
            Initialize the ReceiveConfirmationOrDenial behaviour.
            
            Args:
                accept_msg (Message): The supplier-accept message we sent.
                    Used to extract proposal details for logging if needed.
                sender_jid (str): JID of the warehouse that will send the decision.
            """
            super().__init__()
            self.accepted_id = int(accept_msg.get_metadata("request_id"))
            bod = accept_msg.body.split(" ")
            self.accepted_quantity = int(bod[0])
            self.accepted_product = bod[1]
            self.sender_jid = str(sender_jid)
        
        async def run(self):
            if self.agent.verbose:
                print(f"{self.agent.jid}> Waiting for warehouse confirmation or denial...")
            msg : Message = await self.receive(timeout=10)
            
            if msg != None:
                self.agent : Supplier
                performative = msg.get_metadata("performative")
                
                # Message with body format "quantity product"
                request = msg.body.split(" ")
                quantity = int(request[0])
                product = request[1]
                
                if performative == "warehouse-confirm":
                    # Warehouse confirmed - add to pending deliveries
                    # Create Order object from message and add to pending_deliveries
                    order : Order = self.agent.message_to_order(msg)
                    self.agent.pending_deliveries[order.orderid] = order
                            
                    # Essential print - order confirmed
                    print(f"{self.agent.jid}> Order {order.orderid} confirmed: {quantity} x{product} for {order.sender}")

                    behav = self.agent.AssignVehicle(order.orderid)
                    self.agent.add_behaviour(behav)
                    
                    if self.agent.verbose:
                        self.agent.print_stats()
                    
                elif performative == "warehouse-deny":
                    # Warehouse denied (chose another supplier) - just log it
                    if self.agent.verbose:
                        print(f"{self.agent.jid}> Denial received! Warehouse chose another supplier.")
                        print(f"{self.agent.jid}> Order not confirmed for {product} x{quantity}")
                        self.agent.print_stats()
                    
            else:
                if self.agent.verbose:
                    print(f"{self.agent.jid}> Timeout: No confirmation or denial received in 10 seconds.")
                    # Since supplier has infinite stock, no need to rollback
                    # Just log that order wasn't confirmed
                    print(f"{self.agent.jid}> Order not confirmed for {self.accepted_product} x{self.accepted_quantity}")
                    self.agent.print_stats()
    
    class ReceiveVehicleArrival(CyclicBehaviour):
        """
        Cyclic behaviour that processes vehicle pickup notifications.
        
        Handles vehicle-pickup messages when vehicles arrive to collect confirmed
        orders from the supplier, removes order from pending_deliveries, and sends
        pickup confirmation back to vehicle.
        """
        def add_metadata(self, r_msg: Message, order : Order) -> Message:
            self.agent : Supplier
            
            msg = r_msg
            msg.set_metadata("performative", "pickup-confirm")
            msg.set_metadata("supplier_id", str(self.agent.jid))
            msg.set_metadata("warehouse_id", str(order.sender))
            msg.set_metadata("node_id", str(self.agent.node_id))
            msg.set_metadata("request_id", str(order.orderid))
            msg.body = json.dumps(order.__dict__)
            return msg
        
        async def run(self):
            agent : Supplier = self.agent
            
            msg : Message  = await self.receive(timeout=20)
            
            if msg:
                # Parse message body
                try:
                    data = json.loads(msg.body)
                    order = agent.dict_to_order(data)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"{agent.jid}> ERROR: Failed to parse vehicle message: {e}")
                    return
                
                # Vehicle is picking up an order to deliver to warehouse
                if order.orderid in agent.pending_deliveries:
                    del agent.pending_deliveries[order.orderid]
                    print(f"{agent.jid}> Vehicle {msg.sender} picked up order {order.orderid} "
                        f"({order.quantity}x{order.product} for {order.sender})")
                    
                    msg : Message = Message(to=msg.sender)
                    msg = self.add_metadata(msg, order)
                    await self.send(msg)
                    
                else:
                    print(f"{agent.jid}> ERROR: Order {order.orderid} not found in pending orders!")
                
    
    class AssignVehicle(OneShotBehaviour):
        """
        Behaviour that coordinates vehicle assignment for delivery to warehouse.
        
        This behaviour implements a vehicle coordination protocol where the supplier
        requests delivery quotes from available vehicles to transport materials to
        a warehouse. This is similar to a mini FIPA Contract Net but simplified.
        
        Vehicle Selection Process:
        
            **Phase 1: Vehicle Discovery**
                - Populate vehicles list from presence contacts
                - Only vehicles subscribed to supplier are eligible
            
            **Phase 2: Presence Check**
                - Send presence-info request to each vehicle
                - Receive presence-response with availability status
                - Categorize: CHAT (available) vs AWAY (busy)
            
            **Phase 3: Proposal Requests**
                - Send order-proposal to available vehicles first
                - If no available vehicles, send to AWAY vehicles
                - Broadcast pickup/delivery details
            
            **Phase 4: Collect Proposals**
                - Launch ReceiveVehicleProposals to gather responses
                - Wait for vehicle-proposal messages with can_fit and delivery_time
            
            **Phase 5: Vehicle Selection**
                - Launch ChooseBestVehicle to evaluate proposals
                - Selection criteria: can_fit capacity, then delivery_time
                - Send order-confirmation to winner
        
        Attributes:
            request_id (int): Unique identifier for the order requiring delivery.
        
        Order Information Required:
            - pickup_node: Supplier's current graph node
            - delivery_node: Warehouse's graph node location
            - product: Product type to deliver
            - quantity: Amount to deliver
            - sender: Warehouse JID expecting delivery
        
        Message Format (order-proposal):
            Metadata:
                - performative: "order-proposal"
            Body (JSON):
                - orderid: Order identifier
                - product: Product type
                - quantity: Amount to deliver
                - sender: Warehouse JID (delivery destination)
                - receiver: Supplier JID (pickup location)
                - sender_location: Warehouse node
                - receiver_location: Supplier node
        
        Presence Status Handling:
            - **PresenceShow.CHAT**: Vehicle available, prioritize for proposals
            - **PresenceShow.AWAY**: Vehicle busy, use only if no available vehicles
            - Strategy: Try available first, fallback to busy if necessary
        
        Example Execution:
        
            **Scenario: Normal Vehicle Assignment**
            ```
            Order ID: 301000000
            Pickup: Node 20 (Supplier location)
            Delivery: Node 10 (Warehouse location)
            Product: electronics
            Quantity: 100
            
            Step 1: Discover vehicles
                Found: [vehicle-1, vehicle-2, vehicle-3]
            
            Step 2: Check presence
                vehicle-1: CHAT (available)
                vehicle-2: AWAY (busy)
                vehicle-3: CHAT (available)
            
            Step 3: Send proposals
                Sent to: vehicle-1, vehicle-3 (2 available)
            
            Step 4: Collect proposals
                vehicle-1: can_fit=True, time=120s
                vehicle-3: can_fit=True, time=85s
            
            Step 5: Choose best
                Winner: vehicle-3 (lower delivery time)
                Send order-confirmation to vehicle-3
            ```
            
            **Scenario: No Available Vehicles**
            ```
            All vehicles: AWAY (busy)
            Action: Send proposals to all AWAY vehicles anyway
            Result: Best vehicle will accept when capacity available
            ```
        
        Error Handling:
            - If no vehicles found in contacts:
                - Print error message
                - Return without sending proposals
                - Order stays in pending_deliveries for retry
        
        Note:
            This behaviour launches two child behaviours (ReceiveVehicleProposals
            and ChooseBestVehicle) that implement the proposal collection and
            selection logic.
        """
        def __init__(self, request_id):
            """
            Initialize the AssignVehicle behaviour.
            
            Args:
                request_id (int): Unique identifier for the order requiring vehicle assignment.
            """
            super().__init__()
            self.request_id = request_id
        
        def populate_vehicles_from_contacts(self):
            """Populate vehicles list from presence contacts if empty"""
            agent : Supplier = self.agent
            
            # Get all vehicles from presence contacts
            vehicles = [str(jid) for jid in agent.presence.contacts.keys() if "vehicle" in str(jid)]
            
            if vehicles:
                agent.vehicles = vehicles
                if agent.verbose:
                    print(f"{agent.jid}> 🔍 Discovered {len(vehicles)} vehicle(s) from presence: {vehicles}")
            else:
                if agent.verbose:
                    print(f"{agent.jid}> ⚠️ No vehicles found in presence contacts yet!")
            
            return len(vehicles) > 0
        
        def create_presence_info_message(self, to) -> Message:
            self.agent : Supplier
            
            msg : Message = Message(to=to)
            msg.set_metadata("performative", "presence-info")
            msg.body = ""
            return msg
            
        def create_call_for_proposal_message(self, to) -> Message:
            self.agent : Supplier
            
            msg : Message = Message(to=to)
            msg.set_metadata("performative", "order-proposal")
            
            order = self.agent.pending_deliveries[self.request_id]

            new_body = {
                "orderid" : self.request_id,
                "product" : order.product,
                "quantity" : order.quantity,
                "sender" : order.receiver,
                "receiver" : order.sender,
                "sender_location" : order.receiver_location,
                "receiver_location" : order.sender_location
            }
            
            msg.body = json.dumps(new_body)
            return msg
        
        async def run(self):
            agent : Supplier = self.agent
            
            # Populate vehicles from contacts
            has_vehicles = self.populate_vehicles_from_contacts()
            
            if not has_vehicles:
                print(f"{agent.jid}> ❌ ERROR: No vehicles found in contacts!")
                print(f"{agent.jid}> Make sure vehicles are started and have subscribed to this supplier.")
                return
            
            if agent.verbose:
                print(f"{agent.jid}> 📤 Requesting vehicle proposals...")
                print(f"{agent.jid}> Vehicles to contact: {agent.vehicles}")
            
            # Enviar mensagens de proposal a todos os veículos
            # Não verificamos presença - deixamos cada veículo decidir se pode aceitar
            n_available_vehicles = 0
            away_vehicles = []
            for vehicle_jid in agent.vehicles:
                
                msg : Message = self.create_presence_info_message(to=vehicle_jid)
                await self.send(msg)
                
                behav = self.agent.ReceivePresenceInfo()
                temp : Template = Template()
                temp.set_metadata("performative", "presence-response")
                temp.set_metadata("vehicle_id", str(vehicle_jid))
                self.agent.add_behaviour(behav, temp)
                
                await behav.join()
                if agent.verbose:
                    print(f"{agent.jid}> Presence info from {vehicle_jid}: {agent.presence_infos}")
                
                if agent.presence_infos[vehicle_jid] == "PresenceShow.CHAT":
                    msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                    await self.send(msg)
                    n_available_vehicles += 1
                    print(f"{agent.jid}> ✉️ Sent order proposal to {vehicle_jid}")
                
                elif agent.presence_infos[vehicle_jid] == "PresenceShow.AWAY" and n_available_vehicles == 0:
                    away_vehicles.append(vehicle_jid)
                    if agent.verbose:
                        print(f"{agent.jid}> ⚠️ Vehicle {vehicle_jid} is away.")
                    
            if n_available_vehicles == 0:
                if agent.verbose:
                    print(f"{agent.jid}> ⚠️ No AVAILABLE vehicles found. All vehicles are AWAY.")
                for vehicle_jid in away_vehicles:
                    msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                    await self.send(msg)
                    print(f"{agent.jid}> ✉️ Sent order proposal to {vehicle_jid}")
            
            if agent.verbose:
                print(f"{agent.jid}> 📨 Sent proposals to {n_available_vehicles} vehicle(s)")
                    
            behav = self.agent.ChooseBestVehicle(self.request_id)
            self.agent.add_behaviour(behav, temp)
            
            # Waits for all vehicle proposals to be received
            await behav.join()
    
    class ReceivePresenceInfo(OneShotBehaviour):
        """
        Behaviour to receive presence information from vehicle agents.
        
        This behaviour requests and collects availability status from vehicle agents,
        which is used to determine which vehicles are available for delivery tasks
        from the supplier to warehouses.
        
        The presence information indicates whether a vehicle is busy, available, or
        in another state. This helps the supplier make intelligent vehicle assignment
        decisions based on current vehicle availability.
        
        Workflow:
            1. **Receive Message**: Wait up to 10 seconds for presence response
            2. **Parse JSON**: Extract presence_show status from message body
            3. **Store Information**: Save presence info indexed by vehicle_id
            4. **Handle Timeout**: Print warning if no response received
        
        Side Effects:
            - Updates agent.presence_infos dictionary with vehicle status
            - Prints presence information if verbose mode enabled
        
        Returns:
            None. Completes after receiving one presence message or timing out.
        
        Example:
            ```
            Message Received:
                Metadata: vehicle_id = "vehicle2@localhost"
                Body: {"presence_show": "available"}
            Processing:
                - presence_infos["vehicle2@localhost"] = "available"
            Output:
                - Print: "Received presence info response from vehicle2: available"
            ```
        
        Note:
            The 10-second timeout prevents indefinite blocking if a vehicle agent
            is offline or unresponsive.
        """
        async def run(self):
            agent : Supplier = self.agent
            
            msg : Message = await self.receive(timeout=10)
            
            if msg:
                data = json.loads(msg.body)
                presence_info = data["presence_show"]
                if agent.verbose:
                    print(f"{agent.jid}> Received presence info response from {msg.sender}:"
                          f"{presence_info}")
                agent.presence_infos[msg.get_metadata("vehicle_id")] = presence_info
            else:
                if agent.verbose:
                    print(f"{agent.jid}> No presence info response received from vehicle.")
    
    class ReceiveVehicleProposals(CyclicBehaviour):
        """
        Cyclic behaviour that collects vehicle delivery proposals for supplier orders.
        
        This behaviour implements the proposal collection phase of vehicle selection
        for deliveries from supplier to warehouses. After the supplier sends delivery
        requests to vehicles, this behaviour continuously receives and stores vehicle
        proposals containing delivery capacity and estimated delivery time information.
        
        The behaviour runs in an infinite loop within each execution, collecting all
        available proposals until a timeout occurs (no more proposals arriving). Each
        proposal is indexed by order_id and vehicle_jid for later evaluation by
        ChooseBestVehicle behaviour.
        
        Proposal Data Structure:
            ```python
            vehicle_proposals = {
                order_id: {
                    "vehicle1@localhost": (can_fit: bool, delivery_time: int),
                    "vehicle2@localhost": (can_fit: bool, delivery_time: int),
                    ...
                }
            }
            ```
        
        Message Format:
            Body (JSON):
                ```json
                {
                    "orderid": 3001000000,
                    "can_fit": true,
                    "delivery_time": 180
                }
                ```
        
        Workflow:
            1. **Receive Message**: Wait up to 5 seconds for vehicle proposal
            2. **Parse Proposal**: Extract orderid, can_fit, delivery_time
            3. **Initialize Storage**: Create order_id entry if doesn't exist
            4. **Store Proposal**: Add vehicle proposal to vehicle_proposals dict
            5. **Continue Loop**: Repeat until timeout (no more proposals)
            6. **Exit**: Break loop when timeout indicates all proposals received
        
        Side Effects:
            - Updates agent.vehicle_proposals dictionary with new proposals
            - Prints proposal details if verbose mode enabled
            - Breaks loop after 5-second timeout
        
        Returns:
            None. Exits after collecting all available proposals.
        
        Example Execution:
            ```
            Loop Iteration 1:
                - Receive from vehicle1: can_fit=True, time=150
                - Store: vehicle_proposals[3001000000]["vehicle1"] = (True, 150)
            Loop Iteration 2:
                - Receive from vehicle2: can_fit=True, time=130
                - Store: vehicle_proposals[3001000000]["vehicle2"] = (True, 130)
            Loop Iteration 3:
                - Timeout after 5 seconds
                - Break loop, all proposals collected
            ```
        
        Note:
            The 5-second timeout is optimized to collect multiple proposals quickly
            while not waiting too long for vehicles that won't respond.
        """
        
        async def run(self):
            agent : Supplier = self.agent
            
            while True:
                msg : Message = await self.receive(timeout=5)
                
                if msg:
                    if agent.verbose:
                        print(f"{agent.jid}> Received vehicle proposal from {msg.sender}")
                    data = json.loads(msg.body)
                    
                    # A proposta do veículo não é uma Order, são apenas dados da proposta
                    order_id = data["orderid"]
                    sender_jid = str(msg.sender)
                    can_fit = data["can_fit"]
                    time = data["delivery_time"]
                    
                    # Verificar se a entrada para este order_id existe, se não criar
                    if int(order_id) not in agent.vehicle_proposals:
                        agent.vehicle_proposals[int(order_id)] = {}
                    
                    agent.vehicle_proposals[int(order_id)][sender_jid] = (can_fit, time)
                    if agent.verbose:
                        print(f"{agent.jid}> Vehicle {sender_jid} proposal: can_fit={can_fit}, time={time}")
  
                else: 
                    if agent.verbose:
                        print(f"{agent.jid}> ⏱️ Timeout - no more proposals received")
                    break
                 
    class ChooseBestVehicle(OneShotBehaviour):
        """
        Behaviour that evaluates vehicle proposals and selects optimal vehicle for supplier delivery.
        
        This behaviour implements the proposal evaluation and winner selection phase of
        vehicle assignment for supplier-to-warehouse deliveries. After collecting all
        vehicle proposals via ReceiveVehicleProposals, this behaviour compares them based
        on capacity and delivery time, then notifies the selected vehicle and rejects all others.
        
        Selection Algorithm:
            1. **Priority 1**: Filter vehicles that can fit the order (can_fit=True)
            2. **Priority 2**: Among fitting vehicles, select one with minimum delivery_time
            3. **Fallback**: If no vehicles can fit, select vehicle with minimum delivery_time anyway
        
        Attributes:
            request_id (int): Unique order identifier to find proposals.
        
        Workflow:
            1. **Retrieve Proposals**: Get all proposals for this request_id
            2. **Evaluate Proposals**: Call get_best_vehicle() to select winner
            3. **Send Confirmation**: Notify selected vehicle with order-confirmation
            4. **Send Rejections**: Notify all other vehicles they were not selected
        
        Message Format (Confirmation):
            Metadata:
                - performative: "order-confirmation"
            Body (JSON):
                ```json
                {
                    "orderid": 3001000000,
                    "confirmed": true
                }
                ```
        
        Message Format (Rejection):
            Metadata:
                - performative: "order-confirmation"
            Body (JSON):
                ```json
                {
                    "orderid": 3001000000,
                    "confirmed": false
                }
                ```
        
        Side Effects:
            - Reads from agent.vehicle_proposals dictionary
            - Reads from agent.pending_deliveries for Order object
            - Sends confirmation message to selected vehicle
            - Sends rejection messages to non-selected vehicles
            - Prints selection decision if verbose mode enabled
        
        Returns:
            None. Completes after sending all confirmation/rejection messages.
        
        Example Execution:
            ```
            Proposals Received:
                - vehicle1: (can_fit=True, time=150)
                - vehicle2: (can_fit=True, time=130)
                - vehicle3: (can_fit=False, time=120)
            
            Evaluation:
                - Filter: vehicle1, vehicle2 (can fit)
                - Compare times: 130 < 150
                - Winner: vehicle2
            
            Actions:
                - Send confirmation to vehicle2 (confirmed=true)
                - Send rejection to vehicle1 (confirmed=false)
                - Send rejection to vehicle3 (confirmed=false)
            
            Output:
                - Print: "Best vehicle selected: vehicle2@localhost"
            ```
        
        Note:
            Unlike warehouse's version, this behaviour doesn't wait for proposals
            as they are already collected by ReceiveVehicleProposals before this
            behaviour is invoked.
        """
        def __init__(self, request_id):
            super().__init__()
            self.request_id = request_id
        
        def get_best_vehicle(self, proposals : dict) -> str:
            # First filter vehicles that can fit the order
            can_fit_vehicles = {jid: (fit, time) for jid, (fit, time) in proposals.items() if fit}

            if can_fit_vehicles:
                # If there are vehicles that can fit, choose the one with lowest delivery time
                best_vehicle = min(can_fit_vehicles.items(), key=lambda x: x[1][1])
                return best_vehicle[0]
            else:
                # If no vehicles can fit, choose the one with lowest delivery time anyway
                if proposals:
                    best_vehicle = min(proposals.items(), key=lambda x: x[1][1])
                    return best_vehicle[0]
                return None
        
        async def run(self):
            agent : Supplier = self.agent
            if agent.verbose:
                print(f"{agent.jid}> 📤 Comparing vehicle proposals...")
            
            # Verificar se a entrada para este order_id existe, se não criar
            if int(self.request_id) not in agent.vehicle_proposals:
                agent.vehicle_proposals[int(self.request_id)] = {}
            
            order_proposals =  agent.vehicle_proposals[int(self.request_id)]
            proposals = agent.vehicle_proposals[int(self.request_id)] # vehicle_jid : (can_fit, time)
            
            if agent.verbose:
                print(f"{agent.jid}> 📊 Total proposals received: {len(proposals)}")
            best_vehicle = self.get_best_vehicle(proposals)
            
            if best_vehicle:
                # Essential print - vehicle assigned
                print(f"{agent.jid}> Vehicle assigned: {best_vehicle} for order {self.request_id}")
                
                # Send confirmation to the selected vehicle
                msg : Message = Message(to=best_vehicle)
                msg.set_metadata("performative", "order-confirmation")
                
                order : Order = agent.pending_deliveries[self.request_id]
                order_data = {
                    "orderid" : order.orderid,
                    "confirmed" : True
                }
                msg.body = json.dumps(order_data)
                
                await self.send(msg)
                if agent.verbose:
                    print(f"{agent.jid}> ✉️ Confirmation sent to {best_vehicle} for order {self.request_id}")
                
                # Send rejection to all other vehicles
                rejected_vehicles = [jid for jid in proposals.keys() if jid != best_vehicle]
                for vehicle_jid in rejected_vehicles:
                    reject_msg : Message = Message(to=vehicle_jid)
                    reject_msg.set_metadata("performative", "order-confirmation")
                    
                    reject_data = {
                    "orderid" : order.orderid,
                    "confirmed" : False
                    }
                    
                    reject_msg.body = json.dumps(reject_data)
                    
                    await self.send(reject_msg)
                    if agent.verbose:
                        print(f"{agent.jid}> ❌ Rejection sent to {vehicle_jid} for order {self.request_id}")
            else:
                print(f"{agent.jid}> ⚠️ No vehicles available to assign!")
    
    class ReceiveTimeDelta(CyclicBehaviour):
        """
        Cyclic behaviour that synchronizes simulation time and applies traffic updates.
        
        Receives time delta messages from world agent, updates current_tick, and
        applies dynamic graph edge weight changes for traffic simulation.
        """
        async def run(self):
            agent : Supplier = self.agent
            
            msg : Message = await self.receive(timeout=20)
            
            if msg != None:
                data = json.loads(msg.body)
                
                type : str = data["type"]
                delta : int = data["time"]
                agent.current_tick += delta
                
                if type.lower() != "arrival":
                    map_updates = data["data"] 
                agent.update_graph(map_updates)
    
    # ------------------------------------------
    #           AUXILIARY FUNCTIONS
    # ------------------------------------------
    
    def print_stats(self):
        """
        Print comprehensive supplier statistics (debugging utility).
        
        Displays two key metrics:
        1. **Total Products Supplied**: Cumulative quantities per product type
        2. **Pending Deliveries**: Orders confirmed but not yet picked up by vehicles
        
        Output Format:
            ========================================
            supplier1@localhost Statistics:
            Total Products Supplied:
              electronics: 1500
              textiles: 800
              food: 1200
            
            Pending Deliveries:
              Total: 2 order(s)
                Order 301000000: 100xelectronics for warehouse1@localhost
                Order 301000001: 50xtextiles for warehouse2@localhost
            ========================================
        
        Metrics Interpretation:
            - **Total Products Supplied**: Historical record of all materials provided
            - **Pending Deliveries**: Orders awaiting vehicle pickup
                - Added when warehouse sends warehouse-confirm
                - Removed when vehicle sends vehicle-pickup
        
        Use Cases:
            - Monitoring supplier throughput
            - Tracking pending logistics operations
            - Debugging vehicle coordination issues
            - Performance analysis and reporting
        
        Example Usage:
            ```python
            # After warehouse confirms order
            supplier.pending_deliveries[order_id] = order
            supplier.print_stats()  # Shows new pending order
            
            # After vehicle pickup
            del supplier.pending_deliveries[order_id]
            supplier.print_stats()  # Shows order removed
            ```
        
        Note:
            Unlike warehouse and store, supplier statistics are simpler because
            there's no stock tracking (infinite inventory model).
        """
        print("="*40)
        
        print(f"{self.jid} Statistics:")
        print(f"Total Products Supplied:")
        if self.total_supplied:
            for product, amount in self.total_supplied.items():
                print(f"  {product}: {amount}")
        else:
            print("  None yet")
            
        print(f"\nPending Deliveries:")
        if self.pending_deliveries:
            print(f"  Total: {len(self.pending_deliveries)} order(s)")
            for order_id, order in self.pending_deliveries.items():
                print(f"    Order {order_id}: {order.quantity}x{order.product} for {order.sender}")
        else:
            print("  None")
        
        print("="*40)

    def update_graph(self, traffic_data) -> None:
        """
        Update world graph edge weights based on traffic conditions.
        
        This function applies dynamic traffic updates received from the world agent
        to the supplier's local copy of the world graph. Edge weights represent
        travel costs/times and are updated to reflect current traffic conditions.
        
        Args:
            traffic_data (dict): Traffic update data with structure:
                {
                    "edges": [
                        {
                            "node1": int,  # First node ID
                            "node2": int,  # Second node ID
                            "weight": float  # New edge weight (time/cost)
                        },
                        ...
                    ]
                }
        
        Workflow:
            1. Iterate through all edge updates in traffic_data
            2. Extract node1_id, node2_id, and new_weight
            3. Retrieve edge from graph using get_edge()
            4. Update edge.weight if edge exists
        
        Example:
            ```
            Traffic Data:
            {
                "edges": [
                    {"node1": 10, "node2": 15, "weight": 120.5},
                    {"node1": 15, "node2": 20, "weight": 95.3}
                ]
            }
            
            Actions:
                - Edge (10, 15): weight updated to 120.5
                - Edge (15, 20): weight updated to 95.3
            
            Impact:
                - Vehicle routing recalculated with new weights
                - Delivery time estimates adjusted
                - Pathfinding uses updated costs
            ```
        
        Integration:
            - Called by: ReceiveTimeDelta behaviour
            - Triggered by: time-delta messages from world agent
            - Frequency: Every simulation tick with traffic updates
        
        Note:
            Only updates existing edges. If an edge doesn't exist in the graph,
            it's silently skipped (safe behavior for malformed data).
        """
        for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge : Edge = self.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight

    def message_to_order(self, msg : Message) -> Order:
        """
        Convert warehouse-confirm message to Order object for delivery tracking.
        
        This helper function transforms a FIPA accept-proposal message from a warehouse
        into a structured Order object that can be stored in pending_deliveries
        and assigned to vehicles for transportation.
        
        FIPA Protocol Context:
            - Triggered by: warehouse-confirm message (FIPA accept-proposal)
            - Used by: ReceiveConfirmationOrDenial behaviour
            - Purpose: Create deliverable order from confirmed proposal
        
        Message Parsing:
            Body Format: "{quantity} {product}"
            Example: "100 electronics"
            
            Metadata Extracted:
                - request_id: Unique order identifier
                - node_id: Warehouse's graph location (delivery destination)
        
        Args:
            msg (Message): warehouse-confirm message with:
                - Body: "{quantity} {product}"
                - Metadata: request_id, node_id
                - Sender: Warehouse JID
        
        Returns:
            Order: Structured order object with:
                - product: Product type
                - quantity: Amount to deliver
                - orderid: Unique identifier
                - sender: Warehouse JID (delivery destination)
                - receiver: Supplier JID (pickup location)
                - sender_location: Warehouse's graph node
                - receiver_location: Supplier's graph node
        
        Order Object Structure:
            The Order uses inverted semantics for delivery context:
            - sender = Warehouse (WHERE to deliver)
            - receiver = Supplier (WHERE to pickup)
            - sender_location = Warehouse node (delivery destination)
            - receiver_location = Supplier node (pickup origin)
        
        Example:
            ```
            Input Message (warehouse-confirm):
                Body: "100 electronics"
                Metadata:
                    - request_id: "301000000"
                    - node_id: "10"
                Sender: "warehouse1@localhost"
            
            Supplier: "supplier1@localhost" at node 20
            
            Output Order:
                product: "electronics"
                quantity: 100
                orderid: "301000000"
                sender: "warehouse1@localhost"
                receiver: "supplier1@localhost"
                sender_location: 10 (warehouse node)
                receiver_location: 20 (supplier node)
            ```
        
        Integration:
            Created Order is added to self.pending_deliveries[order_id]
            and passed to AssignVehicle behaviour for transportation.
        
        Note:
            This mirrors the message_to_order function in warehouse.py but
            processes warehouse-confirm instead of store-confirm messages.
        """
        body = msg.body
        parts = body.split(" ")
        quantity = int(parts[0])
        product = parts[1]
        
        order_id = msg.get_metadata("request_id")
        sender = str(msg.sender)  # Warehouse JID
        receiver = str(self.jid)  # Supplier JID
        warehouse_location = int(msg.get_metadata("node_id"))
        supplier_location = self.node_id
        tick = self.current_tick
        
        order = Order(
            product=product,
            quantity=quantity,
            orderid=order_id,
            sender=sender,
            receiver=receiver
        )
        
        # Set locations
        order.sender_location = warehouse_location  # Warehouse location
        order.receiver_location = supplier_location  # Supplier location
        
        return order
    
    
    def dict_to_order(self, data : dict) -> Order:
        """
        Convert dictionary data to Order object (for vehicle communication).
        
        This helper function reconstructs an Order object from dictionary data,
        typically received from vehicle messages (vehicle-pickup). It's the
        inverse operation of serializing an order to JSON.
        
        Args:
            data (dict): Dictionary containing order information with keys:
                - product (str): Product type
                - quantity (int): Amount to deliver
                - orderid (int): Unique order identifier
                - sender (str): Warehouse JID (delivery destination)
                - receiver (str): Supplier JID (pickup location)
                - sender_location (int, optional): Warehouse graph node
                - receiver_location (int, optional): Supplier graph node
        
        Returns:
            Order: Reconstructed Order object with all attributes populated.
        
        Example:
            ```
            Input Dictionary:
            {
                "product": "electronics",
                "quantity": 100,
                "orderid": 301000000,
                "sender": "warehouse1@localhost",
                "receiver": "supplier1@localhost",
                "sender_location": 10,
                "receiver_location": 20
            }
            
            Output Order:
                order.product = "electronics"
                order.quantity = 100
                order.orderid = 301000000
                order.sender = "warehouse1@localhost"
                order.receiver = "supplier1@localhost"
                order.sender_location = 10
                order.receiver_location = 20
            ```
        
        Use Cases:
            - Parsing vehicle-pickup messages
            - Reconstructing orders from JSON body
            - Vehicle coordination communication
        
        Note:
            Uses safe dictionary access (.get()) for location fields to handle
            cases where location data might not be present.
        """
        order =  Order(
            product=data["product"],
            quantity=data["quantity"],
            orderid=data["orderid"],
            sender=data["sender"],
            receiver=data["receiver"]
        )
        order.sender_location = data.get("sender_location")
        order.receiver_location = data.get("receiver_location")
        return order
    
    # ------------------------------------------
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False, contact_list = [], verbose = False):
        """
        Initialize the Supplier agent with connection parameters and world state.
        
        The constructor configures the supplier's identity, location, and initial
        state. It implements the ID encoding system for generating unique request
        identifiers compatible with the FIPA Contract Net Protocol.
        
        ID Encoding System:
            Formula: `agent_type * 100_000_000 + instance_id * 1_000_000 + counter`
            - Agent Type Code: 3 (for Supplier agents)
            - Instance ID: Extracted from JID (e.g., "supplier2" -> 2)
            - Base ID Calculation: `3 * 100_000_000 + instance_id * 1_000_000`
            
            Examples:
                - supplier1: base = 301_000_000 (first request: 301_000_000)
                - supplier2: base = 302_000_000 (first request: 302_000_000)
                - supplier5: base = 305_000_000 (first request: 305_000_000)
            
            This encoding allows agents to identify:
                1. What type of agent created the request (300M range = supplier)
                2. Which specific supplier instance (next 1M range)
                3. Which request in sequence (counter increments)
        
        Args:
            jid (str): Jabber ID for XMPP communication (e.g., "supplier1@localhost").
            password (str): Authentication password for XMPP server.
            map (Graph): Reference to the world graph for pathfinding and locations.
            node_id (int): Graph node representing the supplier's physical location.
            port (int, optional): XMPP server port. Defaults to 5222.
            verify_security (bool, optional): Enable SSL/TLS verification. Defaults to False.
            contact_list (list[str], optional): JIDs of warehouses and vehicles for presence
                subscription. Defaults to empty list.
            verbose (bool, optional): Enable detailed debug logging. Defaults to False.
        
        Attributes Initialized:
            Core Identity:
                - node_id: Supplier location on graph
                - map: World graph reference
                - contact_list: Agents for presence subscription
                - verbose: Debug output flag
            
            Position (Legacy):
                - pos_x: X coordinate from node (TODO: marked for removal)
                - pos_y: Y coordinate from node (TODO: marked for removal)
            
            ID Encoding:
                - id_base: Base value for generating unique request IDs
        
        Example:
            ```python
            supplier = Supplier(
                jid="supplier1@localhost",
                password="password123",
                map=world_graph,
                node_id=20,
                contact_list=[
                    "warehouse1@localhost",
                    "warehouse2@localhost",
                    "vehicle1@localhost"
                ],
                verbose=True
            )
            # ID base calculated: 3 * 100_000_000 + 1 * 1_000_000 = 301_000_000
            # First request ID will be: 301_000_000
            # Second request ID will be: 301_000_001
            ```
        
        Note:
            The constructor only initializes essential attributes. Most supplier
            state (total_supplied, pending_deliveries, behaviours) is configured
            in the setup() method which runs after the agent connects to the XMPP server.
        """
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
        node : Node = self.map.get_node(node_id) # TODO -- remove
        self.pos_x = node.x # TODO -- remove
        self.pos_y = node.y # TODO -- remove
        self.contact_list = contact_list
        self.verbose = verbose
        # Extract instance number from JID for ID encoding (e.g., "supplier1@localhost" -> 1)
        jid_name = str(jid).split('@')[0]
        instance_id = int(''.join(filter(str.isdigit, jid_name)))
        
        # Calculate ID base: Supplier type code = 3
        self.id_base = (3 * 100_000_000) + (instance_id * 1_000_000)
    
    async def setup(self):
        """
        Configure supplier state and register all FIPA protocol behaviours.
        
        This method is automatically called by SPADE after the agent successfully
        connects to the XMPP server. It initializes the supplier's operational
        state and registers all cyclic behaviours needed for the FIPA Contract Net
        Protocol implementation as a participant.
        
        Setup Process:
        
            **Phase 1: Presence Management**
                - Enable auto-approval of presence subscriptions
                - Subscribe to all contacts (warehouses and vehicles)
                - Enables presence-based availability checking
            
            **Phase 2: State Initialization**
                - total_supplied: Dictionary tracking cumulative supply per product
                - current_tick: Simulation time (starts at 0)
                - pending_deliveries: Orders confirmed but not picked up
                - vehicle_proposals: Vehicle delivery quotes per order
                - vehicles: List of vehicle JIDs (populated dynamically)
                - presence_infos: Vehicle availability cache
            
            **Phase 3: Behaviour Registration**
                1. ReceiveBuyRequest (Warehouse Interaction - FIPA Participant)
                2. ReceiveVehicleProposals (Vehicle Coordination - Proposal Collection)
                3. ReceiveVehicleArrival (Vehicle Coordination - Pickup Handling)
        
        Behaviour Registration Details:
        
            **ReceiveBuyRequest** (CyclicBehaviour):
                - Template: performative = "warehouse-buy"
                - Purpose: Listen for warehouse purchase requests (FIPA CFP)
                - Role: FIPA Participant (responds to warehouses)
                - Action: Always accepts (infinite stock)
            
            **ReceiveVehicleProposals** (CyclicBehaviour):
                - Template: performative = "vehicle-proposal"
                - Purpose: Collect vehicle delivery quotes
                - Role: Coordinator for vehicle selection
                - Action: Store proposals in vehicle_proposals dictionary
            
            **ReceiveVehicleArrival** (CyclicBehaviour):
                - Template: performative = "vehicle-pickup"
                - Purpose: Handle vehicle pickup notifications
                - Action: Remove order from pending_deliveries, confirm pickup
        
        Infinite Stock Model:
            Unlike warehouse agents:
            - No stock initialization required
            - No capacity constraints
            - No resupply mechanism needed
            - Only tracks what's been supplied (statistics)
        
        State Initialization Example:
            ```
            After setup():
                total_supplied: {} (empty, will populate as orders fulfilled)
                current_tick: 0
                pending_deliveries: {} (empty, will populate as orders confirmed)
                vehicle_proposals: {} (empty, will populate per order)
                vehicles: [] (will populate from presence contacts)
                presence_infos: {} (will populate during vehicle coordination)
            
            Print Output:
                "supplier1@localhost> Supplier initialized with INFINITE stock"
            ```
        
        Presence Subscription Example:
            ```
            contact_list: [
                "warehouse1@localhost",
                "warehouse2@localhost",
                "vehicle1@localhost",
                "vehicle2@localhost"
            ]
            
            Actions:
                1. Subscribe to all 4 contacts
                2. Enable auto-approval for incoming subscriptions
                3. Print: "Sent subscription request to warehouse1@localhost"
                4. Print: "Sent subscription request to warehouse2@localhost"
                5. Print: "Sent subscription request to vehicle1@localhost"
                6. Print: "Sent subscription request to vehicle2@localhost"
                7. Print: "Supplier setup complete. Will auto-accept all presence subscriptions."
            ```
        
        Template Configuration:
            Templates use metadata filtering to route messages to correct behaviours:
            - ReceiveBuyRequest: performative="warehouse-buy"
            - ReceiveVehicleProposals: performative="vehicle-proposal"
            - ReceiveVehicleArrival: performative="vehicle-pickup"
        
        Side Effects:
            - Prints initialization message with INFINITE stock notice
            - Prints statistics if verbose=True
            - Begins listening for warehouse requests immediately
            - Begins listening for vehicle messages immediately
        
        Note:
            This method must complete before the supplier can participate in any
            FIPA protocol interactions. All behaviours are registered but don't
            execute until the main agent event loop processes them.
        """
        self.presence.approve_all = True
        
        for contact in self.contact_list:
            self.presence.subscribe(contact)
            if self.verbose:
                print(f"{self.jid}> Sent subscription request to {contact}")
        if self.verbose:
            print(f"{self.jid}> Supplier setup complete. Will auto-accept all presence subscriptions.")
        
        # Supplier has infinite stock - no need to track stock levels
        # Just track what's been supplied
        self.total_supplied = {}
        self.current_tick = 0
        
        # Track pending deliveries by order_id
        self.pending_deliveries : dict[int, Order] = {}
        self.vehicle_proposals : dict[int, dict[str, tuple[bool, int]]] = {}
        # Identify vehicles from presence contacts (will be populated dynamically)
        self.vehicles = []
        self.presence_infos : dict[str, str] = {}
        print(f"{self.jid}> Supplier initialized with INFINITE stock")
        if self.verbose:
            self.print_stats()
        
        # Add behaviour to receive buy requests from warehouses
        behav = self.ReceiveBuyRequest()
        template = Template()
        template.set_metadata("performative", "warehouse-buy")
        self.add_behaviour(behav, template)
        
        # Add behaviour to receive vehicle proposals
        vehicle_proposal_behav = self.ReceiveVehicleProposals()
        vehicle_proposal_template = Template()
        vehicle_proposal_template.set_metadata("performative", "vehicle-proposal")
        self.add_behaviour(vehicle_proposal_behav, vehicle_proposal_template)
        
        # Add behaviour to receive vehicle pickup notifications
        pickup_behav = self.ReceiveVehicleArrival()
        pickup_template = Template()
        pickup_template.set_metadata("performative", "vehicle-pickup")
        self.add_behaviour(pickup_behav, pickup_template)