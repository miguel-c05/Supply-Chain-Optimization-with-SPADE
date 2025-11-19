"""
Warehouse Agent Module for Supply Chain Optimization System.

This module implements the Warehouse agent, which serves as an intermediary in the supply
chain between stores and suppliers. The Warehouse manages inventory, accepts orders from
stores, purchases materials from suppliers, and coordinates vehicle delivery logistics.

The module implements dual FIPA Contract Net Protocol roles:
1. **Participant** (with Stores): Responds to store purchase requests
2. **Initiator** (with Suppliers): Initiates purchase requests for restocking

Typical usage example:
    ```python
    from world.graph import Graph
    
    # Initialize graph and warehouse agent
    map_graph = Graph()
    warehouse = Warehouse(
        jid="warehouse1@localhost",
        password="warehouse_password",
        map=map_graph,
        node_id=10,
        contact_list=["store1@localhost", "supplier1@localhost", "vehicle1@localhost"],
        verbose=True
    )
    await warehouse.start()
    ```
"""

import asyncio
import random
import json
import queue
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.template import Template
from spade.presence import PresenceShow
from world.graph import Graph, Edge
from veiculos.veiculos import Order
import config
from logger_utils import MessageLogger, InventoryLogger, OrderLifecycleLogger

class Warehouse(Agent):
    """
    Warehouse Agent for Supply Chain Management System.
    
    The Warehouse agent acts as a critical intermediary in the supply chain, managing
    inventory, fulfilling store orders, and coordinating with suppliers and vehicles.
    It implements dual FIPA Contract Net Protocol roles, acting as both participant
    and initiator depending on the interaction context.
    
    FIPA Contract Net Protocol - Dual Role Implementation:
    
    1. **As Participant (with Stores)**:
        - **Proposal Phase**: Receives store-buy CFP from stores
        - **Proposal Submission**: Sends warehouse-accept (propose) or warehouse-reject (refuse)
        - **Result Reception**: Receives store-confirm (accept-proposal) or store-deny (reject-proposal)
        - **Execution**: Assigns vehicles for confirmed orders
    
    2. **As Initiator (with Suppliers)**:
        - **CFP Phase**: Sends warehouse-buy CFP to suppliers for restocking
        - **Proposal Collection**: Receives supplier-accept (propose) or supplier-reject (refuse)
        - **Evaluation**: Scores suppliers based on delivery time
        - **Award**: Sends warehouse-confirm (accept-proposal) or warehouse-deny (reject-proposal)
    
    Stock Management Strategy:
        The warehouse uses a three-tier stock system:
        1. **Available Stock** (self.stock): Products available for new orders
        2. **Locked Stock** (self.locked_stock): Reserved for pending negotiations
        3. **Pending Deliveries** (self.pending_deliveries): Confirmed orders awaiting pickup
    
    ID Encoding System:
        Similar to Store agent, uses hierarchical encoding:
        - Formula: `agent_type * 100_000_000 + instance_id * 1_000_000 + request_counter`
        - Agent type code for Warehouse: 2
        - Example: warehouse1's first request = 2_001_000_000
    
    Attributes:
        jid (str): Jabber ID of the warehouse agent (e.g., "warehouse1@localhost").
        node_id (int): Graph node ID representing the warehouse's physical location.
        map (Graph): Reference to the world graph for pathfinding calculations.
        contact_list (list[str]): JIDs for stores, suppliers, and vehicles.
        verbose (bool): Flag to control debug output verbosity.
        id_base (int): Base value for generating unique request IDs.
        stock (dict[str, int]): Available inventory (not locked or pending).
        locked_stock (dict[str, int]): Stock reserved during store negotiations.
        current_capacity (dict[str, int]): Remaining capacity per product.
        pending_deliveries (dict[int, Order]): Confirmed orders awaiting vehicle pickup.
        vehicle_proposals (dict[int, dict[str, tuple[bool, int]]]): Vehicle delivery proposals.
            Format: {order_id: {vehicle_jid: (can_fit, delivery_time)}}
        vehicles (list[str]): List of vehicle JIDs discovered from contacts.
        suppliers (list[str]): List of supplier JIDs discovered from contacts.
        request_counter (int): Monotonic counter for unique request IDs.
        current_buy_request (Message): Most recent supplier purchase request.
        failed_requests (queue.Queue): Queue of failed supplier requests for retry.
        presence_infos (dict[str, str]): Vehicle presence status cache.
        current_tick (int): Current simulation time, synchronized by world agent.
    
    Behaviours:
        Store Interaction:
            - ReceiveBuyRequest: Processes store purchase requests (FIPA participant)
            - AcceptBuyRequest: Sends proposal to store (FIPA propose)
            - RejectBuyRequest: Sends refusal to store (FIPA refuse)
            - ReceiveConfirmationOrDenial: Handles store's award/rejection
            - AssignVehicle: Coordinates vehicle assignment for deliveries
            - ReceivePresenceInfo: Checks vehicle availability
            - ReceiveVehicleProposals: Collects vehicle delivery proposals
            - ChooseBestVehicle: Selects optimal vehicle using scoring algorithm
        
        Supplier Interaction:
            - BuyMaterial: Initiates purchase requests to suppliers (FIPA initiator)
            - CollectSupplierResponses: Coordinator for supplier negotiation
            - ReceiveAllSupplierResponses: Worker collecting supplier responses
            - SendWarehouseConfirmation: Awards contract to supplier (FIPA accept-proposal)
            - SendWarehouseDenial: Rejects supplier proposals (FIPA reject-proposal)
            - RetryPreviousBuy: Retries failed supplier requests
            - HandleResupply: Monitors stock and triggers restocking
        
        Vehicle & Time Management:
            - ReceiveVehicleArrival: Handles vehicle pickup and delivery notifications
            - ReceiveTimeDelta: Synchronizes time and applies traffic updates
    
    Message Protocols:
        Incoming from Stores:
            - store-buy: Purchase request (FIPA CFP)
            - store-confirm: Order confirmation (FIPA accept-proposal)
            - store-deny: Order rejection (FIPA reject-proposal)
        
        Outgoing to Stores:
            - warehouse-accept: Order proposal (FIPA propose)
            - warehouse-reject: Order refusal (FIPA refuse)
        
        Outgoing to Suppliers:
            - warehouse-buy: Purchase request (FIPA CFP)
            - warehouse-confirm: Supplier confirmation (FIPA accept-proposal)
            - warehouse-deny: Supplier rejection (FIPA reject-proposal)
        
        Incoming from Suppliers:
            - supplier-accept: Material proposal (FIPA propose)
            - supplier-reject: Material refusal (FIPA refuse)
        
        Vehicle Communication:
            - order-proposal: Request vehicle delivery quote
            - vehicle-proposal: Vehicle delivery proposal
            - order-confirmation: Confirm vehicle assignment
            - vehicle-pickup: Vehicle picks up order
            - vehicle-delivery: Vehicle delivers supplies
            - presence-info: Request vehicle availability
            - presence-response: Vehicle availability status
    
    Example:
        ```python
        warehouse = Warehouse(
            jid="warehouse1@localhost",
            password="password",
            map=world_graph,
            node_id=10,
            contact_list=["store1@localhost", "supplier1@localhost", "vehicle1@localhost"],
            verbose=True
        )
        await warehouse.start()
        ```
    
    Note:
        The warehouse automatically restocks when inventory falls below
        config.WAREHOUSE_RESUPPLY_THRESHOLD, maintaining operational capacity.
    """
    
    # ------------------------------------------
    #           WAREHOUSE <-> STORE
    # ------------------------------------------
    
    class ReceiveBuyRequest(CyclicBehaviour):
        """
        Cyclic behaviour that processes incoming purchase requests from stores.
        
        This behaviour implements the proposal phase of the FIPA Contract Net Protocol
        where the warehouse acts as a **Participant**. It receives CFP messages from
        stores, evaluates inventory availability, and responds with either a proposal
        (warehouse-accept) or refusal (warehouse-reject).
        
        FIPA Protocol Phase: **Proposal Phase - Participant Role**
            - Role: Participant (Warehouse responding to Store's CFP)
            - Receives: store-buy messages (FIPA CFP)
            - Evaluates: Stock availability vs requested quantity
            - Responds: warehouse-accept (propose) or warehouse-reject (refuse)
        
        Stock Locking Mechanism:
            When accepting a request, stock is immediately moved from available to locked:
            - Prevents overselling (race condition protection)
            - Reserved during negotiation (awaiting confirmation)
            - Released if store sends denial or timeout occurs
            - Transferred to pending_deliveries if store confirms
        
        Decision Logic:
            Accept if: (product in stock) AND (stock[product] >= quantity)
            Reject if: Product unavailable OR insufficient quantity
        
        Message Format (store-buy):
            Metadata:
                - performative: "store-buy"
                - request_id: Unique request identifier
            Body:
                - Format: "{quantity} {product}"
                - Example: "50 electronics"
        
        Workflow:
            1. **Receive**: Wait up to 20 seconds for store-buy message
            2. **Parse**: Extract request_id, quantity, product from message
            3. **Evaluate**: Check if product exists and quantity available
            4. **Accept Path**:
                a. Lock stock: stock[product] -= quantity
                b. Update locked_stock: locked_stock[product] += quantity
                c. Launch AcceptBuyRequest behaviour (send warehouse-accept)
            5. **Reject Path**:
                a. Launch RejectBuyRequest behaviour with reason
                b. No stock changes
        
        Concurrency Handling:
            - Processes multiple requests concurrently (cyclic behaviour)
            - Stock locking prevents double-allocation
            - Each request launches independent OneShot behaviours
        
        Example Execution:
            ```
            Request Received: "50 electronics" (request_id=1001000000)
            Stock Check: electronics: 100 available
            Decision: ACCEPT
            Actions:
                - stock[electronics]: 100 -> 50
                - locked_stock[electronics]: 0 -> 50
                - Launch AcceptBuyRequest
                - Wait for store-confirm or store-deny
            ```
        
        Note:
            This behaviour never terminates (cyclic), continuously listening for
            store requests throughout the warehouse's lifecycle.
        """
        async def run(self):
            agent : Warehouse = self.agent
        
            if agent.verbose:
                print("Awaiting buy request...")
            msg = await self.receive(timeout=20)
            if msg != None:
                """
                Messages with metadata ("performative", "store-buy") have body
                with the following format:
                
                "product_quantity product_type"
                
                request_id is in metadata["request_id"]
                """
                request_id = int(msg.get_metadata("request_id"))
                request = msg.body.split(" ")
                quant = int(request[0])
                product = request[1]
                print(f"{agent.jid}> Got request {request_id} for {quant} x{product} from {msg.sender}")
                
                if (product in agent.stock.keys()) and agent.stock[product] >= quant:
                    accept_behav = agent.AcceptBuyRequest(msg)
                    if agent.verbose:
                        print(f"{self.agent.jid}> Locking {quant} of {product}...")
                    
                    # Log inventory change - stock locking
                    stock_before = agent.stock[product]
                    agent.stock[product] -= quant
                    
                    try:
                        inventory_logger = InventoryLogger.get_instance()
                        inventory_logger.log_inventory_change(
                            agent_jid=str(agent.jid),
                            agent_type="warehouse",
                            product=product,
                            change_type="lock",
                            quantity=quant,
                            stock_before=stock_before,
                            stock_after=agent.stock[product],
                            timestamp_sim=agent.current_tick
                        )
                    except Exception:
                        pass
                    
                    if product in agent.locked_stock:
                        agent.locked_stock[product] += quant
                    else: agent.locked_stock[product] = quant

                    if agent.verbose:
                        print(f"Items locked at {agent.jid}.")
                        agent.print_stock()
                    
                    agent.add_behaviour(accept_behav)
                else:
                    # Reject the request - insufficient stock
                    reject_behav = agent.RejectBuyRequest(msg, reason="insufficient_stock")
                    agent.add_behaviour(reject_behav)
                    if agent.verbose:
                        print(f"{agent.jid}> Could not satisfy request. Rejection sent.")
            else:
                if agent.verbose:
                    print(f"{agent.jid}> Did not get any buy requests in 20 seconds.")

    class AcceptBuyRequest(OneShotBehaviour):
        """
        Behaviour that sends proposal acceptance to store (FIPA propose).
        
        This behaviour implements the proposal submission in the FIPA Contract Net
        Protocol where the warehouse, acting as a participant, sends its proposal
        to fulfill the store's request. It then sets up to receive the store's
        decision (accept-proposal or reject-proposal).
        
        FIPA Protocol Phase: **Proposal Submission - Participant Role**
            - Role: Participant (Warehouse proposing to Store)
            - Sends: warehouse-accept (FIPA propose)
            - Purpose: "I can fulfill your request"
            - Next Phase: Await store's award or rejection decision
        
        Attributes:
            request_id (int): Unique identifier for this request.
            quant (int): Quantity of product being proposed.
            product (str): Name of product being proposed.
            sender (str): Store JID that initiated the request.
        
        Message Format (warehouse-accept):
            Metadata:
                - performative: "warehouse-accept" (FIPA propose)
                - warehouse_id: This warehouse's JID
                - store_id: Requesting store's JID
                - node_id: Warehouse's graph location
                - request_id: Original request identifier
            Body:
                - Format: "{quantity} {product}"
                - Example: "50 electronics"
        
        Workflow:
            1. **Send Proposal**: Construct and send warehouse-accept message
            2. **Setup Listener**: Create ReceiveConfirmationOrDenial behaviour
            3. **Configure Template**: Filter for this specific store and request
            4. **Register Behaviour**: Add listener with template to agent
            5. **Non-blocking**: Return immediately (don't wait for response)
        
        Template Configuration:
            Filters messages to match:
            - warehouse_id: This warehouse
            - store_id: Specific store that made request
            - request_id: This specific request
            
            Accepts both performatives:
            - store-confirm (FIPA accept-proposal)
            - store-deny (FIPA reject-proposal)
        
        Example:
            ```
            Input: Store request for "50 electronics"
            Proposal Sent: warehouse-accept with body "50 electronics"
            Listener Setup: ReceiveConfirmationOrDenial waiting for:
                - store-confirm (unlock -> pending delivery) OR
                - store-deny (unlock -> available stock)
            ```
        
        Note:
            Stock remains locked until ReceiveConfirmationOrDenial processes
            the store's decision or times out.
        """
        def __init__(self, msg : Message):
            """
            Initialize the AcceptBuyRequest behaviour.
            
            Args:
                msg (Message): The store-buy request message to accept.
                    Contains request_id in metadata and "{quantity} {product}" in body.
            """
            super().__init__()
            self.request_id = int(msg.get_metadata("request_id"))
            request = msg.body.split(" ")
            self.quant = int(request[0])
            self.product = request[1]
            self.sender = msg.sender
        
        async def run(self):
            """
            Execute the proposal sending and confirmation listener setup.
            
            This method sends the warehouse-accept (FIPA propose) message to the store
            and immediately sets up a listener behaviour to await the store's decision.
            The method returns quickly without blocking, allowing the warehouse to
            continue processing other requests concurrently.
            
            FIPA Protocol Implementation:
                - **Phase**: Proposal Submission
                - **Performative**: warehouse-accept (FIPA propose)
                - **Content**: "{quantity} {product}"
                - **Receiver**: Store that sent the CFP
                - **Next Step**: Await store's accept-proposal or reject-proposal
            
            Workflow:
                1. **Log Acceptance** (verbose): Print proposal details
                2. **Construct Message**: Create warehouse-accept with all metadata
                3. **Send Proposal**: Transmit to requesting store
                4. **Create Listener**: Initialize ReceiveConfirmationOrDenial behaviour
                5. **Setup Template**: Configure filter for this specific negotiation
                6. **Register Listener**: Add behaviour with template to agent
                7. **Return**: Don't block (listener runs independently)
            
            Template Filtering:
                The template ensures the listener only receives messages for THIS
                specific negotiation by matching:
                - warehouse_id: This warehouse's JID
                - store_id: The specific store's JID
                - request_id: This specific request's ID
            
            Non-Blocking Design:
                The commented-out `await confirm_deny_behav.join()` demonstrates
                that we intentionally DON'T wait for confirmation here. This allows
                the warehouse to accept multiple store requests concurrently.
            
            Side Effects:
                - Sends SPADE message to store
                - Adds ReceiveConfirmationOrDenial behaviour to agent
                - Prints debug information if verbose enabled
            
            Returns:
                None. Completes immediately after setting up the listener.
            
            Example:
                ```
                Input: Request for "50 electronics" from store1
                Actions:
                    1. Send warehouse-accept to store1
                    2. Setup listener with template matching:
                       - warehouse_id=warehouse1@localhost
                       - store_id=store1@localhost
                       - request_id=1001000000
                    3. Return (warehouse ready for next request)
                Listener waits independently for store's decision
                ```
            """
            agent : Warehouse = self.agent
            
            if agent.verbose:
                print(
                    f"{agent.jid}> Accepted a request from {self.sender}: "
                    f"id={self.request_id} "
                    f"quant={self.quant} "
                    f"product={self.product}"
                )
            
            
            msg = Message(to=self.sender)
            msg.set_metadata("performative", "warehouse-accept")
            msg.set_metadata("warehouse_id", str(agent.jid))
            msg.set_metadata("store_id", str(self.sender))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quant} {self.product}"
            
            await self.send(msg)
            try:
                msg_logger = MessageLogger.get_instance()
                msg_logger.log_message(
                    sender=str(self.agent.jid),
                    receiver=str(msg.to),
                    message_type="Confirmation",
                    performative="warehouse-accept",
                    body=msg.body
                )
            except Exception:
                pass  # Don't crash on logging errors
            # Wait for either confirmation or denial
            confirm_deny_behav = agent.ReceiveConfirmationOrDenial(msg, self.sender)
            
            # Template that matches BOTH store-confirm AND store-deny
            template = Template()
            template.set_metadata("warehouse_id", str(agent.jid))
            template.set_metadata("store_id", str(self.sender))
            template.set_metadata("request_id", str(self.request_id))
            
            agent.add_behaviour(confirm_deny_behav, template)
            if agent.verbose:
                print(f"{agent.jid}> AcceptBuyRequest finished, now waiting for confirmation or denial...")
            
            # Aguardar a confirmação ser recebida antes de terminar
            # await confirm_deny_behav.join()
    
    class RejectBuyRequest(OneShotBehaviour):
        """
        Behaviour that sends proposal refusal to store (FIPA refuse).
        
        This behaviour implements the refusal response in the FIPA Contract Net Protocol
        where the warehouse, acting as a participant, declines to fulfill the store's
        request due to insufficient inventory or other constraints.
        
        FIPA Protocol Phase: **Proposal Phase - Refusal**
            - Role: Participant (Warehouse declining Store's CFP)
            - Sends: warehouse-reject (FIPA refuse)
            - Purpose: "I cannot fulfill your request"
            - Reason: Typically "insufficient_stock"
            - Result: Store will try other warehouses
        
        Attributes:
            request_id (int): Unique identifier for this request.
            quant (int): Requested quantity that cannot be fulfilled.
            product (str): Requested product that is unavailable/insufficient.
            sender (str): Store JID that initiated the request.
            reason (str): Rejection reason (default: "insufficient_stock").
        
        Message Format (warehouse-reject):
            Metadata:
                - performative: "warehouse-reject" (FIPA refuse)
                - warehouse_id: This warehouse's JID
                - store_id: Requesting store's JID
                - node_id: Warehouse's graph location
                - request_id: Original request identifier
            Body:
                - Format: "{quantity} {product} {reason}"
                - Example: "50 electronics insufficient_stock"
        
        Common Rejection Reasons:
            - "insufficient_stock": Not enough product available
            - "product_unavailable": Product not carried by this warehouse
            - "capacity_exceeded": Order too large for capacity constraints
        
        Example:
            ```
            Request: "100 electronics" (only 50 available)
            Decision: REJECT
            Message Sent: warehouse-reject
                Body: "100 electronics insufficient_stock"
            Result: Stock unchanged, store tries other warehouses
            ```
        
        Note:
            Unlike AcceptBuyRequest, this behaviour does NOT set up any listeners
            because no further interaction is expected after refusal.
        """
        def __init__(self, msg : Message, reason : str = "insufficient_stock"):
            """
            Initialize the RejectBuyRequest behaviour.
            
            Args:
                msg (Message): The store-buy request message to reject.
                reason (str, optional): Reason for rejection. Defaults to "insufficient_stock".
            """
            super().__init__()
            self.request_id = int(msg.get_metadata("request_id"))
            request = msg.body.split(" ")
            self.quant = int(request[0])
            self.product = request[1]
            self.sender = msg.sender
            self.reason = reason
        
        async def run(self):
            """
            Send warehouse-reject message to requesting store.
            
            FIPA Protocol Implementation:
                - Phase: Proposal Refusal
                - Performative: warehouse-reject (FIPA refuse)
                - Direction: Warehouse → Store
            
            Workflow:
                1. **Log Rejection** (verbose): Print rejection details
                2. **Construct Message**: Create warehouse-reject with metadata
                3. **Include Reason**: Add rejection reason to message body
                4. **Send Refusal**: Transmit to requesting store
                5. **Complete**: No further interaction (one-shot behaviour)
            
            Side Effects:
                - No stock changes (was never locked for insufficient stock)
                - No listeners created (conversation ends with refusal)
                - Store receives refusal and tries other warehouses
                - Prints debug information if verbose enabled
            
            Returns:
                None. Completes immediately after sending message.
            """
            agent : Warehouse = self.agent
            
            if agent.verbose:
                print(
                    f"{agent.jid}> Rejected request from {self.sender}: "
                    f"id={self.request_id} "
                    f"quant={self.quant} "
                    f"product={self.product} "
                    f"reason={self.reason}"
                )
            
            msg = Message(to=self.sender)
            msg.set_metadata("performative", "warehouse-reject")
            msg.set_metadata("warehouse_id", str(agent.jid))
            msg.set_metadata("store_id", str(self.sender))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quant} {self.product} {self.reason}"
            
            await self.send(msg)
            try:
                msg_logger = MessageLogger.get_instance()
                msg_logger.log_message(
                    sender=str(self.agent.jid),
                    receiver=str(msg.to),
                    message_type="Confirmation",
                    performative="warehouse-reject",
                    body=msg.body
                )
            except Exception:
                pass  # Don't crash on logging errors
            if agent.verbose:
                print(f"{agent.jid}> RejectBuyRequest sent to {self.sender}")           
    
    class ReceiveConfirmationOrDenial(OneShotBehaviour):
        """
        Behaviour that processes store's award or rejection decision (FIPA result notification).
        
        This behaviour implements the result notification reception in the FIPA Contract Net
        Protocol where the warehouse, acting as a participant, receives the store's final
        decision about whether its proposal was accepted or rejected.
        
        FIPA Protocol Phase: **Result Notification Reception - Participant Role**
            - Role: Participant (Warehouse receiving Store's decision)
            - Receives: store-confirm (FIPA accept-proposal) or store-deny (FIPA reject-proposal)
            - Actions:
                - If confirm: Transfer locked stock to pending deliveries, assign vehicle
                - If deny: Release locked stock back to available inventory
                - If timeout: Release locked stock (store chose another warehouse)
        
        Stock State Transitions:
        
            **On store-confirm (Award)**:
                1. locked_stock[product] -= quantity (release lock)
                2. current_capacity[product] += quantity (update capacity tracking)
                3. Create Order object from message
                4. pending_deliveries[order_id] = order (await vehicle pickup)
                5. Launch AssignVehicle behaviour
            
            **On store-deny or timeout (Rejection/Timeout)**:
                1. locked_stock[product] -= quantity (release lock)
                2. stock[product] += quantity (return to available)
                3. No further action needed
        
        Attributes:
            accepted_id (int): Request ID for which we sent proposal.
            accepted_quantity (int): Quantity that was proposed.
            accepted_product (str): Product that was proposed.
            sender_jid (str): Store JID that will send decision.
        
        Timeout Mechanism:
            - Wait time: 10 seconds
            - Interpretation: Store chose another warehouse (implicit rejection)
            - Action: Unlock stock automatically
        
        Example Execution:
        
            **Scenario 1: Store Confirms**
            ```
            Proposed: 50 electronics
            Message Received: store-confirm "50 electronics"
            Actions:
                - locked_stock[electronics]: 50 -> 0
                - pending_deliveries[1001000000] = Order(...)
                - Launch AssignVehicle(1001000000)
                - Print: "Order 1001000000 confirmed..."
            ```
            
            **Scenario 2: Store Denies**
            ```
            Proposed: 50 electronics
            Message Received: store-deny "50 electronics"
            Actions:
                - locked_stock[electronics]: 50 -> 0
                - stock[electronics]: 50 -> 100
                - Print: "Store chose another warehouse"
            ```
            
            **Scenario 3: Timeout**
            ```
            Proposed: 50 electronics
            Message Received: None (10 second timeout)
            Actions:
                - locked_stock[electronics]: 50 -> 0
                - stock[electronics]: 50 -> 100
                - Print: "No confirmation received, unlocking stock"
            ```
        
        Note:
            This behaviour is automatically filtered by template to only receive
            messages for the specific warehouse, store, and request_id combination.
        """
        def __init__(self, accept_msg : Message, sender_jid):
            """
            Initialize the ReceiveConfirmationOrDenial behaviour.
            
            Args:
                accept_msg (Message): The warehouse-accept message we sent.
                    Used to extract proposal details for stock unlocking if needed.
                sender_jid (str): JID of the store that will send the decision.
            """
            super().__init__()
            self.accepted_id = int(accept_msg.get_metadata("request_id"))
            bod = accept_msg.body.split(" ")
            self.accepted_quantity = int(bod[0])
            self.accepted_product = bod[1]
            self.sender_jid = str(sender_jid)
        
        async def run(self):
            if self.agent.verbose:
                print(f"{self.agent.jid}> Waiting for store confirmation or denial...")
            msg : Message = await self.receive(timeout=10)
            
            if msg != None:
                self.agent : Warehouse
                performative = msg.get_metadata("performative")
                
                # Message with body format "quantity product"
                request = msg.body.split(" ")
                quantity = int(request[0])
                product = request[1]
                
                if performative == "store-confirm":
                    # Store confirmed - update locked stock and add to pending orders
                    self.agent.locked_stock[product] -= quantity
                    self.agent.current_capacity[product] += quantity
                    
                    # Create Order object from message
                    order = self.agent.message_to_order(msg)
                    
                    # Add to pending_deliveries dict with order_id as key
                    self.agent.pending_deliveries[order.orderid] = order
                            
                    # Essential print - order confirmed
                    print(f"{self.agent.jid}> Order {order.orderid} confirmed: {quantity} x{product} for {order.sender}")
                    
                    behav = self.agent.AssignVehicle(order.orderid)
                    self.agent.add_behaviour(behav)

                    if self.agent.verbose:
                        self.agent.print_stock()
                    
                elif performative == "store-deny":
                    # Store denied (chose another warehouse) - unlock the stock
                    if self.agent.verbose:
                        print(f"{self.agent.jid}> Denial received! Store chose another warehouse.")
                        print(f"{self.agent.jid}> Unlocking stock: {product} += {quantity}")
                    
                    self.agent.locked_stock[product] -= quantity
                    stock_before = self.agent.stock[product]
                    self.agent.stock[product] += quantity
                    
                    # Log inventory change - stock unlock (denied)
                    try:
                        inventory_logger = InventoryLogger.get_instance()
                        inventory_logger.log_inventory_change(
                            agent_jid=str(self.agent.jid),
                            agent_type="warehouse",
                            product=product,
                            change_type="unlock_denied",
                            quantity=quantity,
                            stock_before=stock_before,
                            stock_after=self.agent.stock[product],
                            timestamp_sim=self.agent.current_tick
                        )
                    except Exception:
                        pass
                    
                    if self.agent.verbose:
                        self.agent.print_stock()
                    
            else:
                if self.agent.verbose:
                    print(f"{self.agent.jid}> Timeout: No confirmation or denial received in 10 seconds. Unlocking stock...")
                self.agent.locked_stock[self.accepted_product] -= self.accepted_quantity
                stock_before = self.agent.stock[self.accepted_product]
                self.agent.stock[self.accepted_product] += self.accepted_quantity
                
                # Log inventory change - stock unlock (timeout)
                try:
                    inventory_logger = InventoryLogger.get_instance()
                    inventory_logger.log_inventory_change(
                        agent_jid=str(self.agent.jid),
                        agent_type="warehouse",
                        product=self.accepted_product,
                        change_type="unlock_timeout",
                        quantity=self.accepted_quantity,
                        stock_before=stock_before,
                        stock_after=self.agent.stock[self.accepted_product],
                        timestamp_sim=self.agent.current_tick
                    )
                except Exception:
                    pass
                
                if self.agent.verbose:
                    self.agent.print_stock()            
    
    class AssignVehicle(OneShotBehaviour):
        def __init__(self, request_id):
            super().__init__()
            self.request_id = request_id
        
        def populate_vehicles_from_contacts(self):
            """Populate vehicles list from presence contacts if empty"""
            agent : Warehouse = self.agent
            
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
            self.agent : Warehouse
            
            msg : Message = Message(to=to)
            msg.set_metadata("performative", "presence-info")
            msg.body = ""
            return msg
            
        def create_call_for_proposal_message(self, to) -> Message:
            self.agent : Warehouse
            
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
            agent : Warehouse = self.agent
            
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
            n_sent_messages = 0
            away_vehicles = []
            for vehicle_jid in agent.vehicles:
                
                msg : Message = self.create_presence_info_message(to=vehicle_jid)
                await self.send(msg)
                try:
                    msg_logger = MessageLogger.get_instance()
                    msg_logger.log_message(
                        sender=str(self.agent.jid),
                        receiver=str(msg.to),
                        message_type="Request",
                        performative="presence-info",
                        body=msg.body
                    )
                except Exception: 
                    pass  # Don't crash on logging errors
                
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
                    try:
                        msg_logger = MessageLogger.get_instance()
                        msg_logger.log_message(
                            sender=str(self.agent.jid),
                            receiver=str(msg.to),
                            message_type="Request",
                            performative="order-proposal",
                            body=msg.body
                        )
                    except Exception:
                        pass  # Don't crash on logging errors
                    n_available_vehicles += 1
                    n_sent_messages += 1
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
                    try:
                        msg_logger = MessageLogger.get_instance()
                        msg_logger.log_message(
                            sender=str(self.agent.jid),
                            receiver=str(msg.to),
                            message_type="Request",
                            performative="order-proposal",
                            body=msg.body
                        )
                    except Exception:
                        pass  # Don't crash on logging errors
                    n_sent_messages += 1
                    print(f"{agent.jid}> ✉️ Sent order proposal to {vehicle_jid}")
            
            if agent.verbose:
                print(f"{agent.jid}> 📨 Sent proposals to {n_sent_messages} vehicle(s)")
                    
            behav = self.agent.ChooseBestVehicle(self.request_id, n_sent_messages)
            self.agent.add_behaviour(behav, temp)
            
            # Waits for all vehicle proposals to be received
            await behav.join()
    
    class ReceivePresenceInfo(OneShotBehaviour):
        """
        Behaviour to receive presence information from vehicle agents.
        
        This behaviour requests and collects availability status from vehicle agents,
        which is used to determine which vehicles are available for delivery tasks.
        The presence information indicates whether a vehicle is busy, available, or
        in another state.
        
        The behaviour waits for a single response from a vehicle agent containing
        its current presence status. This information is stored in the warehouse's
        presence_infos dictionary for later use in vehicle selection.
        
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
                Metadata: vehicle_id = "vehicle1@localhost"
                Body: {"presence_show": "available"}
            Processing:
                - presence_infos["vehicle1@localhost"] = "available"
            Output:
                - Print: "Received presence info response from vehicle1: available"
            ```
        
        Note:
            The 10-second timeout prevents indefinite blocking if a vehicle agent
            is offline or unresponsive.
        """
        async def run(self):
            agent : Warehouse = self.agent
            
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
        Cyclic behaviour that collects vehicle delivery proposals for orders.
        
        This behaviour implements the proposal collection phase of vehicle selection.
        After the warehouse sends delivery requests to vehicles, this behaviour
        continuously receives and stores vehicle proposals containing delivery capacity
        and estimated delivery time information.
        
        The behaviour runs in an infinite loop within each execution, collecting all
        available proposals until a timeout occurs (no more proposals arriving). Each
        proposal is indexed by order_id and vehicle_jid for later evaluation.
        
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
                    "orderid": 2001000000,
                    "can_fit": true,
                    "delivery_time": 150
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
                - Receive from vehicle1: can_fit=True, time=120
                - Store: vehicle_proposals[2001000000]["vehicle1"] = (True, 120)
            Loop Iteration 2:
                - Receive from vehicle2: can_fit=False, time=180
                - Store: vehicle_proposals[2001000000]["vehicle2"] = (False, 180)
            Loop Iteration 3:
                - Timeout after 5 seconds
                - Break loop, all proposals collected
            ```
        
        Note:
            The 5-second timeout is optimized to collect multiple proposals quickly
            while not waiting too long for vehicles that won't respond.
        """
        
        async def run(self):
            agent : Warehouse = self.agent
            
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
        Behaviour that evaluates vehicle proposals and selects the optimal vehicle for delivery.
        
        This behaviour implements the proposal evaluation and winner selection phase of
        vehicle assignment. After collecting all vehicle proposals via ReceiveVehicleProposals,
        this behaviour compares them based on capacity and delivery time, then notifies
        the selected vehicle and rejects all others.
        
        Selection Algorithm:
            1. **Priority 1**: Filter vehicles that can fit the order (can_fit=True)
            2. **Priority 2**: Among fitting vehicles, select one with minimum delivery_time
            3. **Fallback**: If no vehicles can fit, select vehicle with minimum delivery_time anyway
        
        Attributes:
            request_id (int): Unique order identifier to find proposals.
            n_sent_messages (int): Expected number of vehicle responses to wait for.
        
        Workflow:
            1. **Wait for Proposals**: Loop until n_sent_messages proposals received
            2. **Evaluate Proposals**: Call get_best_vehicle() to select winner
            3. **Send Confirmation**: Notify selected vehicle with order-confirmation
            4. **Send Rejections**: Notify all other vehicles they were not selected
        
        Message Format (Confirmation):
            Metadata:
                - performative: "order-confirmation"
            Body (JSON):
                ```json
                {
                    "orderid": 2001000000,
                    "confirmed": true
                }
                ```
        
        Message Format (Rejection):
            Metadata:
                - performative: "order-confirmation"
            Body (JSON):
                ```json
                {
                    "orderid": 2001000000,
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
                - vehicle1: (can_fit=True, time=120)
                - vehicle2: (can_fit=True, time=150)
                - vehicle3: (can_fit=False, time=100)
            
            Evaluation:
                - Filter: vehicle1, vehicle2 (can fit)
                - Compare times: 120 < 150
                - Winner: vehicle1
            
            Actions:
                - Send confirmation to vehicle1 (confirmed=true)
                - Send rejection to vehicle2 (confirmed=false)
                - Send rejection to vehicle3 (confirmed=false)
            
            Output:
                - Print: "Best vehicle selected: vehicle1@localhost"
            ```
        
        Note:
            The behaviour waits actively (1-second sleep intervals) until all expected
            proposals arrive before making a decision. This ensures fair comparison
            of all available vehicles.
        """
        def __init__(self, request_id, n_sent_messages):
            super().__init__()
            self.request_id = request_id
            self.n_sent_messages = n_sent_messages
        
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
            agent : Warehouse = self.agent
            if agent.verbose:
                print(f"{agent.jid}> 📤 Comparing vehicle proposals...")
            
            # Verificar se a entrada para este order_id existe, se não criar
            if int(self.request_id) not in agent.vehicle_proposals:
                agent.vehicle_proposals[int(self.request_id)] = {}
            
            proposals = agent.vehicle_proposals[int(self.request_id)] # vehicle_jid : (can_fit, time)
            
            while len(proposals) < self.n_sent_messages:
                if agent.verbose:
                    print(f"{agent.jid}> Waiting for more proposals... "
                          f"({len(proposals)}/{self.n_sent_messages})")
                await asyncio.sleep(1)
                proposals = agent.vehicle_proposals[int(self.request_id)]
            

            
            if agent.verbose:
                print(f"{agent.jid}> 📊 Total proposals received: {len(proposals)}")
            best_vehicle = self.get_best_vehicle(proposals)
            
            if best_vehicle:
                print(f"{agent.jid}> 🏆 Best vehicle selected: {best_vehicle}")
                
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
                try:
                    msg_logger = MessageLogger.get_instance()
                    msg_logger.log_message(
                        sender=str(self.agent.jid),
                        receiver=str(msg.to),
                        message_type="Confirmation",
                        performative="order-confirmation",
                        body=msg.body
                    )
                except Exception:
                    pass  # Don't crash on logging errors
                
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

                    try:
                        msg_logger = MessageLogger.get_instance()
                        msg_logger.log_message(
                            sender=str(self.agent.jid),
                            receiver=str(reject_msg.to),
                            message_type="Confirmation",
                            performative="order-confirmation",
                            body=reject_msg.body
                        )
                    except Exception:
                        pass  # Don't crash on logging errors
                
    # ------------------------------------------
    #         WAREHOUSE <-> SUPPLIER
    # ------------------------------------------
        
    class BuyMaterial(OneShotBehaviour):
        """
        Behaviour that initiates material purchase from suppliers (FIPA CFP - Initiator Role).
        
        This behaviour implements the FIPA Contract Net Protocol with the warehouse acting
        as the INITIATOR role. The warehouse broadcasts a Call For Proposals (CFP) to
        suppliers to replenish inventory. This is the dual role mentioned in the class
        docstring - the warehouse is a participant when dealing with stores but becomes
        an initiator when dealing with suppliers.
        
        FIPA Protocol: **Contract Net - Initiator Role**
            - Role: Initiator (Warehouse requesting materials from Suppliers)
            - Sends: warehouse-buy (FIPA CFP) with quantity and product
            - Receives: supplier-accept (FIPA propose) or supplier-reject (FIPA refuse)
            - Selection: Choose best supplier based on price and availability
            - Award: Send warehouse-confirm (FIPA accept-proposal) to winner
        
        Dual FIPA Role Context:
            - **As Participant** (Store ↔ Warehouse): Warehouse responds to store CFPs
            - **As Initiator** (Warehouse ↔ Supplier): Warehouse sends CFPs to suppliers
            
            This dual role makes the warehouse a critical intermediary in the supply chain,
            translating downstream demand into upstream procurement.
        
        Attributes:
            quantity (int): Amount of material to purchase from suppliers.
            product (str): Type of material/product needed for restocking.
        
        Message Format (warehouse-buy):
            Metadata:
                - performative: "warehouse-buy" (FIPA CFP)
                - warehouse_id: This warehouse's JID
                - request_id: Unique request identifier (ID encoding)
            Body:
                - Format: "{quantity} {product}"
                - Example: "100 raw_materials"
        
        ID Encoding for Request:
            Uses the warehouse's ID encoding scheme:
            - request_id = warehouse.id_base + warehouse.request_counter
            - Format: 1 (warehouse type) * 100_000_000 + instance * 1_000_000 + counter
            - Example: 101000000 (warehouse 1, request 0)
        
        Workflow:
            1. **Populate Suppliers**: Auto-discover suppliers from presence contacts
            2. **Generate Request ID**: Create unique ID for this procurement
            3. **Broadcast CFP**: Send warehouse-buy to all available suppliers
            4. **Set Metadata**: Store request for retry mechanism (current_buy_request)
            5. **Launch Coordinator**: Start CollectSupplierResponses to gather proposals
            6. **Non-blocking**: Return immediately (coordinator handles responses)
        
        Coordinator/Worker Pattern:
            - **Initiator (this)**: Sends CFP and launches coordinator
            - **Coordinator**: CollectSupplierResponses (manages collection process)
            - **Worker**: ReceiveAllSupplierResponses (collects individual proposals)
            - **Decision**: SendWarehouseConfirmation (award) or SendWarehouseDenial (reject)
        
        Supplier Discovery:
            Automatically populates supplier list from presence contacts:
            - Filters contacts for JIDs containing "supplier"
            - Updates agent.suppliers list if empty
            - Requires presence subscription to be active
        
        Example Execution:
        
            **Scenario 1: Normal Procurement**
            ```
            Trigger: stock[electronics] < restock_threshold
            Request: BuyMaterial(100, "electronics")
            
            Step 1: Populate suppliers
                Discovered: [supplier1@localhost, supplier2@localhost]
            
            Step 2: Generate ID
                request_id: 101000000
            
            Step 3: Broadcast CFP
                To: supplier1, supplier2
                Message: warehouse-buy "100 electronics"
            
            Step 4: Launch coordinator
                CollectSupplierResponses(101000000, 100, "electronics")
                Coordinator launches ReceiveAllSupplierResponses worker
            
            Step 5: Wait for proposals (handled by coordinator)
            ```
            
            **Scenario 2: No Suppliers Available**
            ```
            Request: BuyMaterial(100, "electronics")
            Suppliers: [] (empty list, none in presence)
            
            Result: ERROR logged, no messages sent
            Action: Retry later when suppliers available
            ```
        
        Retry Mechanism:
            Sets agent.current_buy_request with:
            - quantity: Amount requested
            - product: Product type
            - request_id: Request identifier
            
            Used by RetryPreviousBuy if procurement fails.
        
        Note:
            This behaviour implements the same FIPA protocol that stores use when
            buying from warehouses, but with reversed roles. The message format and
            workflow mirror the store-warehouse interaction.
        """
        def __init__(self, quantity, product):
            """
            Initialize the BuyMaterial behaviour.
            
            Args:
                quantity (int): Amount of material to purchase.
                product (str): Type of material/product to procure.
            """
            super().__init__()
            self.quantity = quantity
            self.product = product
        
        def populate_suppliers_from_contacts(self):
            """Populate suppliers list from presence contacts if empty"""
            agent : Warehouse = self.agent
            if not agent.suppliers:
                agent.suppliers = [jid for jid in agent.presence.contacts.keys() if "supplier" in str(jid)]
                if agent.suppliers and agent.verbose:
                    print(f"{agent.jid}> Auto-populated suppliers from contacts: {agent.suppliers}")
        
        async def run(self):
            agent : Warehouse = self.agent
            
            # Populate suppliers from contacts if list is empty
            self.populate_suppliers_from_contacts()
            
            if not agent.suppliers:
                if agent.verbose:
                    print(f"{agent.jid}> ERROR: No suppliers found in contacts!")
                return
            
            # Get request_id before sending - use ID encoding
            request_id_for_template = agent.id_base + agent.request_counter
            agent.request_counter += 1
            
            msg = None  # Will store the last sent message for current_buy_request
            # Only send to suppliers, not all contacts
            for supplier_jid in agent.suppliers:
                msg = Message(to=supplier_jid)
                msg.set_metadata("performative", "warehouse-buy")
                msg.set_metadata("warehouse_id", str(agent.jid))
                msg.set_metadata("request_id", str(request_id_for_template))
                msg.set_metadata("node_id", str(agent.node_id))
                msg.body = f"{self.quantity} {self.product}"
                
                if agent.verbose:
                    print(f"{agent.jid}> Sent request (id={msg.get_metadata('request_id')}):"
                          f"\"{msg.body}\" to {msg.to}")
                
                await self.send(msg)
                try:
                    msg_logger = MessageLogger.get_instance()
                    msg_logger.log_message(
                        sender=str(self.agent.jid),
                        receiver=str(msg.to),
                        message_type="Request",
                        performative="warehouse-buy",
                        body=msg.body
                    )
                except Exception:
                    pass  # Don't crash on logging errors
            # Store the last message (or could store all if needed)
            if msg:
                agent.current_buy_request = msg
        
                # Collect responses from all suppliers
                behav = agent.CollectSupplierResponses(
                    msg, 
                    request_id_for_template, 
                    len(agent.suppliers),
                    self.quantity,
                    self.product
                )
                agent.add_behaviour(behav)
                
                await behav.join()
    
    class CollectSupplierResponses(OneShotBehaviour):
        """
        Coordinator behaviour that manages supplier proposal collection and evaluation.
        
        Launches ReceiveAllSupplierResponses worker to collect proposals from all suppliers,
        then evaluates responses and selects the best supplier based on delivery time.
        Sends confirmation to winner and denials to others. Implements FIPA initiator role.
        """
        def __init__(self, msg : Message, request_id : int, num_suppliers : int, quantity : int, product : str):
            super().__init__()
            self.request_id = request_id
            self.buy_msg = msg.body
            self.num_suppliers = num_suppliers
            self.quantity = quantity
            self.product = product
            self.acceptances = []  # List of (supplier_jid, msg)
            self.rejections = []   # List of (supplier_jid, msg, reason)
            
        async def run(self):
            agent : Warehouse = self.agent
            
            # Setup template that accepts BOTH supplier-accept AND supplier-reject
            template = Template()
            template.set_metadata("warehouse_id", str(agent.jid))
            template.set_metadata("request_id", str(self.request_id))
            # Don't filter by performative - we want both accept and reject
            
            if agent.verbose:
                print(f"{agent.jid}> Setting up to receive supplier responses for request_id={self.request_id}")
            
            # Create a combined behaviour to listen for both
            combined_behav = agent.ReceiveAllSupplierResponses(
                self.request_id,
                self.num_suppliers,
                self.acceptances,
                self.rejections
            )
            
            # Add with template that matches both performatives
            agent.add_behaviour(combined_behav, template)
            
            # Wait for collection to complete
            await combined_behav.join()
            
            # Now evaluate and choose best supplier
            if self.acceptances:
                if agent.verbose:
                    print(f"{agent.jid}> Received {len(self.acceptances)} acceptance(s) and {len(self.rejections)} rejection(s)")
                
                # Calculate scores for each supplier that accepted
                best_supplier = None
                best_score = float('inf')
                
                for supplier_jid, msg in self.acceptances:
                    score = agent.calculate_supplier_score(msg)
                    if agent.verbose:
                        print(f"{agent.jid}> Warehouse {supplier_jid} score: {score}")
                    
                    if score < best_score:
                        best_score = score
                        best_supplier = (supplier_jid, msg)
                
                if best_supplier:
                    supplier_jid, accept_msg = best_supplier
                    # Essential print - supplier selected
                    print(f"{agent.jid}> Selected supplier {supplier_jid} for {self.quantity}x{self.product}")
                    
                    # Send confirmation to the chosen supplier
                    confirm_behav = agent.SendWarehouseConfirmation(accept_msg)
                    agent.add_behaviour(confirm_behav)
                    await confirm_behav.join()
                    
                    # Send denial to other suppliers that accepted but weren't chosen
                    for other_supplier_jid, other_msg in self.acceptances:
                        if other_supplier_jid != supplier_jid:
                            deny_behav = agent.SendWarehouseDenial(other_msg)
                            agent.add_behaviour(deny_behav)
                            if agent.verbose:
                                print(f"{agent.jid}> Sent denial to {other_supplier_jid}")
                    
            else:
                if agent.verbose:
                    print(f"{agent.jid}> No acceptances received. All suppliers rejected or timed out.")
                    print(f"{agent.jid}> Request saved in self.failed_requests")
                
                # Add to failed requests
                if hasattr(agent, 'current_buy_request') and agent.current_buy_request:
                    agent.failed_requests.put(agent.current_buy_request)

    class ReceiveAllSupplierResponses(OneShotBehaviour):
        """
        Worker behaviour that collects supplier-accept and supplier-reject responses.
        
        Waits for responses from all suppliers (with timeout), categorizing them into
        acceptances and rejections lists shared with CollectSupplierResponses coordinator.
        """
        def __init__(self, request_id : int, num_suppliers : int, acceptances : list, rejections : list):
            super().__init__()
            self.request_id = request_id
            self.num_suppliers = num_suppliers
            self.acceptances = acceptances  # Shared list
            self.rejections = rejections    # Shared list
            self.responses_received = 0
            self.timeout = 5  # seconds to wait for all responses
            
        async def run(self):
            agent : Warehouse = self.agent
            
            if agent.verbose:
                print(f"{agent.jid}> ReceiveAllSupplierResponses starting - waiting for {self.num_suppliers} responses (request_id={self.request_id})")
            
            import time
            start_time = time.time()
            
            while self.responses_received < self.num_suppliers:
                elapsed = time.time() - start_time
                remaining_timeout = self.timeout - elapsed
                
                if remaining_timeout <= 0:
                    if agent.verbose:
                        print(f"{agent.jid}> Timeout: Only received {self.responses_received}/{self.num_suppliers} responses")
                    break
                
                if agent.verbose:
                    print(f"{agent.jid}> Waiting for supplier response... (timeout={remaining_timeout:.1f}s)")
                msg : Message = await self.receive(timeout=remaining_timeout)
                
                if msg:
                    performative = msg.get_metadata("performative")
                    supplier_jid = str(msg.sender)
                    
                    if agent.verbose:
                        print(f"{agent.jid}> Received message from {supplier_jid} with performative={performative}")
                    
                    if performative == "supplier-accept":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        
                        if agent.verbose:
                            print(f"{agent.jid}> Received acceptance from {supplier_jid}: {quantity} {product}")
                        self.acceptances.append((supplier_jid, msg))
                        
                    elif performative == "supplier-reject":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        reason = parts[2] if len(parts) > 2 else "unknown"
                        
                        if agent.verbose:
                            print(f"{agent.jid}> Received rejection from {supplier_jid}: {quantity} {product} (reason: {reason})")
                        self.rejections.append((supplier_jid, msg, reason))
                    else:
                        if agent.verbose:
                            print(f"{agent.jid}> WARNING: Received unknown performative: {performative}")
                    
                    self.responses_received += 1
                else:
                    # No more messages, timeout
                    if agent.verbose:
                        print(f"{agent.jid}> No message received in timeout window")
                    break
            
            if agent.verbose:
                print(f"{agent.jid}> Finished collecting responses: {len(self.acceptances)} accepts, {len(self.rejections)} rejects")               
    
    class SendWarehouseConfirmation(OneShotBehaviour):
        """
        Sends warehouse-confirm (FIPA accept-proposal) to selected supplier.
        
        Awards the contract to the best supplier, updates stock immediately,
        and notifies the supplier that their proposal was accepted.
        """
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
            
        
        async def run(self):
            agent : Warehouse = self.agent
            
            if self.product in agent.stock:
                agent.stock[self.product] += self.quantity
            else:
                agent.stock[self.product] = self.quantity           
            
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "warehouse-confirm")
            msg.set_metadata("supplier_id", str(self.dest))
            msg.set_metadata("warehouse_id", str(agent.jid))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            try:
                msg_logger = MessageLogger.get_instance()
                msg_logger.log_message(
                    sender=str(self.agent.jid),
                    receiver=str(msg.to),
                    message_type="Confirmation",
                    performative="warehouse-confirm",
                    body=msg.body
                )
            except Exception:
                pass  # Don't crash on logging errors
            
            if agent.verbose:
                print(f"{agent.jid}> Confirmation sent to {self.dest} for request: {msg.body}")
    
    class SendWarehouseDenial(OneShotBehaviour):
        """
        Sends warehouse-deny (FIPA reject-proposal) to non-selected suppliers.
        
        Notifies suppliers that their proposal was not accepted, allowing them
        to release any resources they may have reserved.
        """
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
        
        async def run(self):
            agent : Warehouse = self.agent
            
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "warehouse-deny")
            msg.set_metadata("supplier_id", str(self.dest))
            msg.set_metadata("warehouse_id", str(agent.jid))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            try:
                msg_logger = MessageLogger.get_instance()
                msg_logger.log_message(
                    sender=str(self.agent.jid),
                    receiver=str(msg.to),
                    message_type="Confirmation",
                    performative="warehouse-deny",
                    body=msg.body
                )
            except Exception:
                pass  # Don't crash on logging errors
            
            if agent.verbose:
                print(f"{agent.jid}> Denial sent to {self.dest} for request: {msg.body}")
    
    class RetryPreviousBuy(OneShotBehaviour):
        """
        Retries failed supplier purchase requests from the failed_requests queue.
        
        Dequeues one failed request and re-initiates the FIPA Contract Net Protocol
        with suppliers, reusing the same request_id for traceability.
        """
        async def run(self):
            agent : Warehouse = self.agent
            
            if not agent.failed_requests.empty():
                request : Message = agent.failed_requests.get()
                request_id = int(request.get_metadata("request_id"))
                
                # Parse quantity and product from request body
                parts = request.body.split(" ")
                quantity = int(parts[0])
                product = parts[1]
                
                # Only send to suppliers, not all contacts
                num_suppliers = len(agent.suppliers)
                
                msg = None
                for supplier_jid in agent.suppliers:
                    msg = Message(to=supplier_jid)
                    msg.set_metadata("performative", "warehouse-buy")
                    msg.set_metadata("warehouse_id", str(agent.jid))
                    msg.set_metadata("request_id", str(request_id))
                    msg.set_metadata("node_id", str(agent.node_id))
                    msg.body = request.body

                    if agent.verbose:
                        print(f"{agent.jid}> Retrying request (id={request_id}):"
                              f"\"{msg.body}\" to {msg.to}")

                    await self.send(msg)
                    try:
                        msg_logger = MessageLogger.get_instance()
                        msg_logger.log_message(
                            sender=str(self.agent.jid),
                            receiver=str(msg.to),
                            message_type="Request",
                            performative="warehouse-buy",
                            body=msg.body
                        )
                    except Exception:
                        pass  # Don't crash on logging errors
                # Use CollectSupplierResponses with all required parameters
                if msg:
                    behav = agent.CollectSupplierResponses(
                        msg,
                        request_id,
                        num_suppliers,
                        quantity,
                        product
                    )
                    agent.add_behaviour(behav)

                    await behav.join()
    
    class HandleResupply(PeriodicBehaviour):
        """
        Periodic behaviour that monitors stock levels and triggers restocking.
        
        Checks each product's stock against WAREHOUSE_RESUPPLY_THRESHOLD and
        launches BuyMaterial behaviour when inventory falls below threshold.
        """
        async def run(self):
            agent : Warehouse = self.agent
            
            # Check stock levels
            for product, amount in agent.stock.items():
                if amount < config.WAREHOUSE_RESUPPLY_THRESHOLD:
                    # Need to restock this product
                    restock_amount = config.WAREHOUSE_MAX_PRODUCT_CAPACITY - amount
                    # Essential print - warehouse restocking
                    print(f"{agent.jid}> Restocking {product}: {amount} -> {config.WAREHOUSE_MAX_PRODUCT_CAPACITY} (buying {restock_amount})")
                    
                    buy_behav = agent.BuyMaterial(restock_amount, product)
                    agent.add_behaviour(buy_behav)
                    
                    await buy_behav.join()
    
    # ------------------------------------------
    #         COMMON / OTHER BEHAVIORS
    # ------------------------------------------

    class ReceiveVehicleArrival(CyclicBehaviour):
        """
        Cyclic behaviour that processes vehicle pickup and delivery notifications.
        
        Handles vehicle-pickup messages (vehicle collects order from warehouse) and
        vehicle-delivery messages (vehicle delivers supplies from supplier), updating
        pending_deliveries and stock accordingly.
        """
        async def run(self):
            agent : Warehouse = self.agent
            msg : Message = await self.receive(timeout=20)
            
            if msg:
                performative = msg.get_metadata("performative")
                
                # Double-check (should already be filtered by templates)
                if performative not in ["vehicle-pickup", "vehicle-delivery"]:
                    print(f"{agent.jid}> ERROR: Received unexpected performative '{performative}'")
                    return
                
                # Parse message body
                try:
                    data = json.loads(msg.body)
                    orderid = data["orderid"]
                    order = agent.pending_deliveries[orderid] 
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"{agent.jid}> ERROR: Failed to parse vehicle message: {e}")
                    return
                
                # Handle based on performative
                if performative == "vehicle-pickup":
                    # Vehicle is picking up an order to deliver to store
                    if order.orderid in agent.pending_deliveries:
                        del agent.pending_deliveries[order.orderid]
                        # Essential print - vehicle pickup
                        print(f"{agent.jid}> Vehicle {msg.sender} picked up order {order.orderid} "
                            f"({order.quantity}x{order.product} for {order.sender})")
                    else:
                        print(f"{agent.jid}> ERROR: Order {order.orderid} not found in pending orders!")
                
                elif performative == "vehicle-delivery":
                    # Vehicle is delivering supplies from supplier
                    product = order.product
                    quantity = order.quantity
                    
                    stock_before = agent.stock.get(product, 0)
                    if product in agent.stock:
                        agent.stock[product] += quantity
                    else:
                        agent.stock[product] = quantity
                    
                    # Log inventory change - delivery from supplier
                    try:
                        inventory_logger = InventoryLogger.get_instance()
                        inventory_logger.log_inventory_change(
                            agent_jid=str(agent.jid),
                            agent_type="warehouse",
                            product=product,
                            change_type="delivery",
                            quantity=quantity,
                            stock_before=stock_before,
                            stock_after=agent.stock[product],
                            timestamp_sim=agent.current_tick
                        )
                    except Exception:
                        pass
                    
                    print(f"{agent.jid}> Vehicle {msg.sender} delivered {quantity} units of {product}")
                    agent.print_stock()                            
    
    class ReceiveTimeDelta(CyclicBehaviour):
        """
        Cyclic behaviour that synchronizes simulation time and applies traffic updates.
        
        Receives time delta messages from world agent, updates current_tick, and
        applies dynamic graph edge weight changes for traffic simulation.
        """
        async def run(self):
            agent : Warehouse = self.agent
            
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
    #           AUXILARY FUNCTIONS
    # ------------------------------------------
    
    def calculate_supplier_score(self, accept_msg : Message) -> float:
        """
        Calculate supplier score based on delivery time (used in FIPA supplier selection).
        
        This function evaluates supplier proposals in the FIPA Contract Net Protocol
        by computing the estimated delivery time from supplier to warehouse using
        Dijkstra's algorithm on the world graph. Lower scores indicate faster delivery.
        
        FIPA Protocol Context:
            - Phase: Proposal Evaluation (Initiator evaluating participants)
            - Used by: CollectSupplierResponses and ReceiveAllSupplierResponses
            - Purpose: Select best supplier from multiple proposals
        
        Scoring Algorithm:
            1. Extract supplier's node_id from message metadata
            2. Run Dijkstra's algorithm: supplier_node → warehouse_node
            3. Return estimated travel time as score
            4. Lower score = shorter delivery time = better supplier
        
        Args:
            accept_msg (Message): supplier-accept message containing:
                - Metadata: "node_id" (supplier's graph location)
                - Body: "{quantity} {product}"
        
        Returns:
            float: Estimated delivery time (seconds). Lower is better.
        
        Example:
            ```
            Warehouse at node 10
            Supplier1 at node 5: delivery_time = 120s
            Supplier2 at node 8: delivery_time = 85s
            
            calculate_supplier_score(supplier1_msg) → 120.0
            calculate_supplier_score(supplier2_msg) → 85.0
            
            Winner: Supplier2 (lower score)
            ```
        
        Note:
            Currently uses time as the scoring metric. Could be extended to use
            fuel cost or a weighted combination of multiple factors.
        """
        
        supplier_node_id = int(accept_msg.get_metadata("node_id"))
        path, fuel, time = self.map.djikstra(supplier_node_id, self.node_id)
        
        return time  # Use time as score (could also use fuel)

    def message_to_order(self, msg : Message) -> Order:
        """
        Convert store-confirm message to Order object for delivery tracking.
        
        This helper function transforms a FIPA accept-proposal message from a store
        into a structured Order object that can be stored in pending_deliveries
        and assigned to vehicles for transportation.
        
        FIPA Protocol Context:
            - Triggered by: store-confirm message (FIPA accept-proposal)
            - Used by: ReceiveConfirmationOrDenial behaviour
            - Purpose: Create deliverable order from confirmed proposal
        
        Message Parsing:
            Body Format: "{quantity} {product}"
            Example: "50 electronics"
            
            Metadata Extracted:
                - request_id: Unique order identifier
                - node_id: Store's graph location (delivery destination)
        
        Args:
            msg (Message): store-confirm message with:
                - Body: "{quantity} {product}"
                - Metadata: request_id, node_id
                - Sender: Store JID
        
        Returns:
            Order: Structured order object with:
                - product: Product type
                - quantity: Amount to deliver
                - orderid: Unique identifier
                - sender: Store JID (delivery destination)
                - receiver: Warehouse JID (pickup location)
                - sender_location: Store's graph node
                - receiver_location: Warehouse's graph node
        
        Order Object Structure:
            The Order uses inverted semantics for delivery context:
            - sender = Store (WHERE to deliver)
            - receiver = Warehouse (WHERE to pickup)
            - sender_location = Store node (delivery destination)
            - receiver_location = Warehouse node (pickup origin)
        
        Example:
            ```
            Input Message (store-confirm):
                Body: "50 electronics"
                Metadata:
                    - request_id: "201000000"
                    - node_id: "15"
                Sender: "store1@localhost"
            
            Warehouse: "warehouse1@localhost" at node 10
            
            Output Order:
                product: "electronics"
                quantity: 50
                orderid: 201000000
                sender: "store1@localhost"
                receiver: "warehouse1@localhost"
                sender_location: 15 (store node)
                receiver_location: 10 (warehouse node)
            ```
        
        Integration:
            Created Order is added to self.pending_deliveries[order_id]
            and passed to AssignVehicle behaviour for transportation.
        """
        body = msg.body
        parts = body.split(" ")
        quantity = int(parts[0])
        product = parts[1]
        
        order_id = int(msg.get_metadata("request_id"))
        sender = str(msg.sender)  # Store JID
        receiver = str(self.jid)  # Warehouse JID
        store_location = int(msg.get_metadata("node_id"))
        warehouse_location = self.node_id
        
        order = Order(
            product=product,
            quantity=quantity,
            orderid=order_id,
            sender=sender,
            receiver=receiver
        )
        
        # Set locations
        order.sender_location = store_location  # Store location
        order.receiver_location = warehouse_location  # Warehouse location
        
        return order
        
    def set_buy_metadata(self, msg : Message):
        msg.set_metadata("performative", "warehouse-buy")
        msg.set_metadata("warehouse_id", str(self.jid))
        msg.set_metadata("request_id", str(self.request_counter))
    
    def update_graph(self, traffic_data) -> None:
        for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge : Edge = self.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight

    def print_stock(self):
        """
        Print comprehensive warehouse inventory status (debugging utility).
        
        Displays the three-tier stock management system:
        1. **Unlocked Stock**: Available for new orders
        2. **Locked Stock**: Reserved during FIPA negotiations
        3. **Pending Orders**: Confirmed deliveries awaiting vehicle pickup
        
        Output Format:
            ==============================
            Current warehouse1@localhost UNLOCKED stock:
            electronics: 75/150
            textiles: 120/150
            food: 40/150
            ------------------------------
            Current warehouse1@localhost LOCKED stock:
            electronics: 25/100
            textiles: 0/120
            ------------------------------
            Current warehouse1@localhost PENDING ORDERS:
            Order 201000000: 25xelectronics from store1@localhost to warehouse1@localhost
            Order 201000001: 50xtextiles from store2@localhost to warehouse1@localhost
            ==============================
        
        Stock Interpretation:
            - Unlocked: X/MAX_CAPACITY
            - Locked: X/Total_Available (stock + locked)
            - Pending: Formatted as "{order_id}: {quantity}x{product} from {sender} to {receiver}"
        
        Use Cases:
            - Debugging stock state transitions
            - Verifying FIPA protocol effects on inventory
            - Monitoring pending delivery queue
            - Tracking resource availability
        
        Example Usage:
            ```python
            # After accepting store request
            warehouse.locked_stock[product] = 50
            warehouse.print_stock()  # Shows locked stock increased
            
            # After store confirmation
            warehouse.pending_deliveries[order_id] = order
            warehouse.print_stock()  # Shows new pending order
            
            # After vehicle pickup
            del warehouse.pending_deliveries[order_id]
            warehouse.print_stock()  # Shows order removed
            ```
        """
        print("="*30)
        
        print(f"Current {self.jid} UNLOCKED stock:")
        for product, amount in self.stock.items():
            print(f"{product}: {amount}/{config.WAREHOUSE_MAX_PRODUCT_CAPACITY}")
        print("-"*30)
        
        print(f"Current {self.jid} LOCKED stock:")
        for product, amount in self.locked_stock.items():
            print(f"{product}: {amount}/{self.stock[product] + amount}")
        print("-"*30)
                
        print(f"Current {self.jid} PENDING ORDERS:")
        if self.pending_deliveries:
            for order_id, order in self.pending_deliveries.items():
                print(f"Order {order_id}: {order.quantity}x{order.product} "
                      f"from {order.sender} to {order.receiver}")
        else:
            print("No pending orders")
        
        print("="*30) 
    
    def dict_to_order(self, data : dict) -> Order:
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
        Initialize the Warehouse agent with connection parameters and world state.
        
        The constructor configures the warehouse's identity, location, and initial
        state. It implements the ID encoding system for generating unique request
        identifiers compatible with the FIPA Contract Net Protocol.
        
        ID Encoding System:
            Formula: `agent_type * 100_000_000 + instance_id * 1_000_000 + counter`
            - Agent Type Code: 2 (for Warehouse agents)
            - Instance ID: Extracted from JID (e.g., "warehouse3" -> 3)
            - Base ID Calculation: `2 * 100_000_000 + instance_id * 1_000_000`
            
            Examples:
                - warehouse1: base = 201_000_000 (first request: 201_000_000)
                - warehouse2: base = 202_000_000 (first request: 202_000_000)
                - warehouse5: base = 205_000_000 (first request: 205_000_000)
            
            This encoding allows agents to identify:
                1. What type of agent created the request (200M range = warehouse)
                2. Which specific warehouse instance (next 1M range)
                3. Which request in sequence (counter increments)
        
        Args:
            jid (str): Jabber ID for XMPP communication (e.g., "warehouse1@localhost").
            password (str): Authentication password for XMPP server.
            map (Graph): Reference to the world graph for pathfinding and locations.
            node_id (int): Graph node representing the warehouse's physical location.
            port (int, optional): XMPP server port. Defaults to 5222.
            verify_security (bool, optional): Enable SSL/TLS verification. Defaults to False.
            contact_list (list[str], optional): JIDs of stores, suppliers, vehicles for presence
                subscription. Defaults to empty list.
            verbose (bool, optional): Enable detailed debug logging. Defaults to False.
        
        Attributes Initialized:
            Core Identity:
                - node_id: Warehouse location on graph
                - map: World graph reference
                - contact_list: Agents for presence subscription
                - verbose: Debug output flag
            
            ID Encoding:
                - id_base: Base value for generating unique request IDs
                - request_counter: Monotonic counter for requests
            
            Order Management:
                - pending_deliveries: Dict mapping order_id -> Order objects
                - vehicle_proposals: Dict mapping order_id -> vehicle proposals
            
            Contact Discovery:
                - vehicles: List of vehicle JIDs (populated during setup)
                - suppliers: List of supplier JIDs (populated during setup)
        
        Example:
            ```python
            warehouse = Warehouse(
                jid="warehouse1@localhost",
                password="password123",
                map=world_graph,
                node_id=10,
                contact_list=[
                    "store1@localhost",
                    "store2@localhost",
                    "supplier1@localhost",
                    "vehicle1@localhost"
                ],
                verbose=True
            )
            # ID base calculated: 2 * 100_000_000 + 1 * 1_000_000 = 201_000_000
            # First request ID will be: 201_000_000
            # Second request ID will be: 201_000_001
            ```
        
        Note:
            The constructor only initializes essential attributes. Most warehouse
            state (stock, locked_stock, behaviours) is configured in the setup()
            method which runs after the agent connects to the XMPP server.
        """
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
        self.contact_list = contact_list
        self.verbose = verbose
        # Extract instance number from JID for ID encoding (e.g., "warehouse1@localhost" -> 1)
        jid_name = str(jid).split('@')[0]
        instance_id = int(''.join(filter(str.isdigit, jid_name)))

        # Calculate ID base: Warehouse type code = 2
        self.id_base = (2 * 100_000_000) + (instance_id * 1_000_000)
        
        # Initialize critical attributes early to avoid AttributeError
        self.pending_deliveries : dict[int, Order] = {} # order_id as key and Order object as value
        self.vehicle_proposals : dict[int, dict[str, tuple[bool]]] = {}
        self.vehicles = []
        self.suppliers = []
        self.request_counter : int = 0
    
    async def setup(self):
        """
        Configure warehouse state and register all FIPA protocol behaviours.
        
        This method is automatically called by SPADE after the agent successfully
        connects to the XMPP server. It initializes the warehouse's operational
        state and registers all cyclic and periodic behaviours needed for the
        dual FIPA Contract Net Protocol implementation.
        
        Setup Process:
        
            **Phase 1: Presence Management**
                - Enable auto-approval of presence subscriptions
                - Subscribe to all contacts (stores, suppliers, vehicles)
                - Enables presence-based availability checking
            
            **Phase 2: Stock Initialization**
                - Randomize initial stock for each product
                - Range: [WAREHOUSE_RESUPPLY_THRESHOLD+1, WAREHOUSE_MAX_PRODUCT_CAPACITY]
                - Calculate current_capacity per product
                - Initialize locked_stock dictionary (empty)
            
            **Phase 3: State Initialization**
                - current_tick: Simulation time (starts at 0)
                - presence_infos: Vehicle availability cache
                - current_buy_request: Last supplier purchase request
                - failed_requests: Queue for retry mechanism
            
            **Phase 4: Contact Discovery**
                - Parse presence.contacts to identify vehicles and suppliers
                - Filter by JID string matching ("vehicle", "supplier")
                - Populate vehicles and suppliers lists
            
            **Phase 5: Behaviour Registration**
                1. ReceiveBuyRequest (Store Interaction - FIPA Participant)
                2. HandleResupply (Inventory Management - Triggers FIPA Initiator)
                3. ReceiveVehicleArrival (Logistics Coordination)
                4. ReceiveTimeDelta (Time Synchronization)
        
        Behaviour Registration Details:
        
            **ReceiveBuyRequest** (CyclicBehaviour):
                - Template: performative = "store-buy"
                - Purpose: Listen for store purchase requests (FIPA CFP)
                - Role: FIPA Participant (responds to stores)
            
            **HandleResupply** (PeriodicBehaviour):
                - Period: 5 seconds
                - Purpose: Monitor stock levels and trigger restocking
                - Role: Launches BuyMaterial (FIPA Initiator with suppliers)
            
            **ReceiveVehicleArrival** (CyclicBehaviour):
                - Template: performative = "vehicle-pickup" OR "vehicle-delivery"
                - Purpose: Handle vehicle logistics notifications
                - Actions:
                    - vehicle-pickup: Remove order from pending_deliveries
                    - vehicle-delivery: Add delivered materials to stock
            
            **ReceiveTimeDelta** (CyclicBehaviour):
                - Template: performative = "time-delta"
                - Purpose: Synchronize simulation time with world agent
                - Actions: Update current_tick, apply traffic conditions
        
        Stock Initialization Example:
            ```
            Products: [electronics, textiles, food]
            WAREHOUSE_MAX_PRODUCT_CAPACITY: 150
            WAREHOUSE_RESUPPLY_THRESHOLD: 30
            
            Initial Stock (randomized):
                electronics: 87  (available)
                textiles:    45  (available)
                food:        120 (available)
            
            Current Capacity (calculated):
                electronics: 150 - 87 = 63
                textiles:    150 - 45 = 105
                food:        150 - 120 = 30
            
            Locked Stock (initialized empty):
                electronics: 0
                textiles:    0
                food:        0
            ```
        
        Presence Subscription Example:
            ```
            contact_list: [
                "store1@localhost",
                "store2@localhost",
                "supplier1@localhost",
                "vehicle1@localhost",
                "vehicle2@localhost"
            ]
            
            Actions:
                1. Subscribe to all 5 contacts
                2. Parse contacts for types:
                   - vehicles: ["vehicle1@localhost", "vehicle2@localhost"]
                   - suppliers: ["supplier1@localhost"]
                3. Stores automatically discovered via presence system
            ```
        
        Template Configuration:
            Templates use metadata filtering to route messages to correct behaviours:
            - ReceiveBuyRequest: performative="store-buy"
            - ReceiveVehicleArrival: performative in ["vehicle-pickup", "vehicle-delivery"]
            - ReceiveTimeDelta: performative="time-delta"
        
        Side Effects:
            - Prints initial stock levels if verbose=True
            - Begins listening for store requests immediately
            - Starts periodic inventory monitoring
            - Enables vehicle coordination capability
        
        Note:
            This method must complete before the warehouse can participate in any
            FIPA protocol interactions. All behaviours are registered but don't
            execute until the main agent event loop processes them.
        """
        self.presence.approve_all = True
        for contact in self.contact_list:
            self.presence.subscribe(contact)
            if self.verbose:
                print(f"{self.jid}> Subscribed to presence of {contact}")
        # Initialize stock and time
        self.stock = {}
        self.current_tick = 0
        
        # Set the starting stock randomly
        product_max = config.WAREHOUSE_MAX_PRODUCT_CAPACITY
        for prod in config.PRODUCTS:
            self.stock[prod] = random.randint(config.WAREHOUSE_RESUPPLY_THRESHOLD + 1,
                                              product_max)
        
        self.current_capacity = {prod: product_max - quant for prod, quant in self.stock.items()}
        
        # Dict with products as keys and the sum of requested items as values
        self.locked_stock = {}
        self.print_stock()
        
        
        self.presence_infos : dict[str, str] = {}
        self.current_buy_request : Message = None
        self.failed_requests : queue.Queue = queue.Queue()
        
        # Identify vehicles from presence contacts
        self.vehicles = []
        self.suppliers  = []
        for vehicle in self.presence.contacts.keys():
            if "vehicle" in str(vehicle):
                self.vehicles.append(vehicle)
            if "supplier" in str(vehicle):
                self.suppliers.append(vehicle)
        
        # Run ReceiveBuyRequest behaviour
        behav = self.ReceiveBuyRequest()
        template = Template()
        template.set_metadata("performative", "store-buy")
        self.add_behaviour(behav, template)
        
        # Run HandleResupply behaviour
        behav = self.HandleResupply(period=5)
        self.add_behaviour(behav)
        
        # Run ReceiveVehicleArrival behaviour for pickups
        behav = self.ReceiveVehicleArrival()
        template = Template()
        template.set_metadata("performative", "vehicle-pickup")
        self.add_behaviour(behav, template)
        
        # Run ReceiveVehicleProposals behaviour
        vehicle_proposal_behav = self.ReceiveVehicleProposals()
        vehicle_proposal_template = Template()
        vehicle_proposal_template.set_metadata("performative", "vehicle-proposal")
        self.add_behaviour(vehicle_proposal_behav, vehicle_proposal_template)

        # Run ReceiveVehicleArrival behaviour for deliveries
        behav = self.ReceiveVehicleArrival()
        template = Template()
        template.set_metadata("performative", "vehicle-delivery")
        self.add_behaviour(behav, template)
        
        # Run ReceiveTimeDelta
        behav = self.ReceiveTimeDelta()
        template = Template()
        template.set_metadata("performative", "inform")
        self.add_behaviour(behav, template)
