"""
Store Agent Module for Supply Chain Optimization System.

This module implements the Store agent, which represents a retail point in the supply chain.
The Store agent is responsible for managing inventory, purchasing products from warehouses,
and interacting with the transportation system for product delivery.

The module follows the FIPA (Foundation for Intelligent Physical Agents) Contract Net Protocol
for warehouse selection and negotiation, implementing the roles of Initiator in procurement
processes.

Typical usage example:
    ```python
    from world.graph import Graph
    
    # Initialize graph and store agent
    map_graph = Graph()
    store = Store(
        jid="store1@localhost",
        password="store_password",
        map=map_graph,
        node_id=1,
        contact_list=["warehouse1@localhost", "warehouse2@localhost"],
        verbose=True
    )
    await store.start()
    ```
"""

import asyncio
import random
import queue
from aiohttp_jinja2 import template
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, PeriodicBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template
from world.graph import Graph, Edge
from veiculos.veiculos import Order
import config
import json
from datetime import datetime, timedelta
import csv
import os
from typing import Optional 

class Store(Agent):
    """
    Retail Store Agent for Supply Chain Management System.
    
    The Store agent represents a retail point in the supply chain network. It manages
    inventory, purchases products from warehouses using a negotiation protocol, and
    coordinates with vehicle agents for product delivery. The agent operates on a
    graph-based world representation where each store has a specific node location.
    
    FIPA Contract Net Protocol Implementation:
        This agent acts as the **Initiator** in the FIPA Contract Net Protocol:
        
        1. **Call for Proposals (CFP)**: Store broadcasts purchase requests to all warehouses
           using the `store-buy` performative, which corresponds to the FIPA CFP message.
           
        2. **Proposal Reception**: Warehouses respond with either `warehouse-accept` (propose)
           or `warehouse-reject` (refuse) performatives.
           
        3. **Proposal Evaluation**: Store evaluates all proposals using a distance-based
           scoring function to select the optimal warehouse.
           
        4. **Award/Rejection**: Store sends `store-confirm` (accept-proposal) to the winner
           and `store-deny` (reject-proposal) to non-selected participants.
    
    ID Encoding System:
        The Store uses a hierarchical ID encoding for unique request identification:
        - Formula: `agent_type * 100_000_000 + instance_id * 1_000_000 + request_counter`
        - Agent type code for Store: 1
        - Example: store1's first request = 1_001_000_000
        - This ensures globally unique request IDs across the multi-agent system.
    
    Attributes:
        jid (str): Jabber ID of the store agent (e.g., "store1@localhost").
        node_id (int): Graph node ID representing the store's physical location.
        map (Graph): Reference to the world graph for pathfinding and distance calculations.
        contact_list (list[str]): List of warehouse JIDs for subscription and communication.
        verbose (bool): Flag to control debug output verbosity. When True, detailed logs
            are printed; when False, only essential information is shown.
        id_base (int): Base value for generating unique request IDs using encoding formula.
            Computed as `(1 * 100_000_000) + (instance_id * 1_000_000)`.
        stock (dict[str, int]): Current inventory mapping product names to quantities.
        request_counter (int): Monotonic counter for generating unique request IDs.
            Incremented with each purchase request.
        current_buy_request (Message): Reference to the most recent buy request message.
        failed_requests (queue.Queue): FIFO queue holding failed purchase requests for retry.
            Requests are enqueued when no warehouse accepts the order.
        pending_deliveries (dict[int, Order]): Orders awaiting vehicle delivery, keyed by order ID.
        order_timings (dict[int, int]): Tick timestamps when orders were confirmed, used for
            calculating time-to-delivery statistics.
        current_tick (int): Current simulation time tick, updated by world agent.
        product_list (list[str]): Available products for purchase (from config.PRODUCTS).
        buy_prob (float): Probability (0-1) of initiating a purchase each period
            (from config.STORE_BUY_PROBABILITY).
        max_buy_quantity (int): Maximum quantity that can be purchased in a single order
            (from config.STORE_MAX_BUY_QUANTITY).
        stats_path (str): Directory path for statistics CSV files.
        stats_filename (str): Filename for order statistics CSV ("store_stats.csv").
    
    Behaviours:
        BuyProduct: Periodic behaviour that initiates purchase requests based on probability.
        CollectWarehouseResponses: Coordinator for FIPA Contract Net Protocol implementation.
        ReceiveAllResponses: Worker behaviour that collects all warehouse responses.
        SendStoreConfirmation: Sends confirmation to selected warehouse (FIPA accept-proposal).
        SendStoreDenial: Sends rejection to non-selected warehouses (FIPA reject-proposal).
        RetryPreviousBuy: Periodic behaviour that retries failed purchase requests.
        ReceiveTimeDelta: Cyclic behaviour that processes simulation time updates and traffic data.
        ReceiveVehicleArrival: Cyclic behaviour that handles vehicle delivery notifications.
    
    Message Protocols:
        Outgoing Messages:
            - `store-buy`: Purchase request to warehouses (FIPA CFP).
                Body format: "{quantity} {product}"
                Metadata: store_id, node_id, request_id
                
            - `store-confirm`: Confirmation to selected warehouse (FIPA accept-proposal).
                Body format: "{quantity} {product}"
                Metadata: warehouse_id, store_id, node_id, request_id
                
            - `store-deny`: Rejection to non-selected warehouses (FIPA reject-proposal).
                Body format: "{quantity} {product}"
                Metadata: warehouse_id, store_id, node_id, request_id
        
        Incoming Messages:
            - `warehouse-accept`: Warehouse accepts order (FIPA propose).
                Body format: "{quantity} {product}"
                
            - `warehouse-reject`: Warehouse rejects order (FIPA refuse).
                Body format: "{quantity} {product} {reason}"
                
            - `vehicle-delivery`: Vehicle delivers products.
                Body format: JSON with orderid, time (ETA)
                
            - `inform`: Time delta and traffic updates from world agent.
                Body format: JSON with type, time, data
    
    Notes:
        - Only ONE purchase request should be active at a time to avoid conflicts.
        - Failed requests are automatically retried by the RetryPreviousBuy behaviour.
        - Stock is updated only upon vehicle delivery, not upon order confirmation.
        - All order statistics are saved to CSV for post-simulation analysis.
        - The agent subscribes to all warehouses in contact_list during setup.
    
    Example:
        ```python
        store = Store(
            jid="store1@localhost",
            password="password",
            map=world_graph,
            node_id=5,
            contact_list=["warehouse1@localhost", "warehouse2@localhost"],
            verbose=True
        )
        await store.start()
        ```
    """
    
    # ------------------------------------------
    #         WAREHOUSE <-> STORE
    # ------------------------------------------
    
    class BuyProduct(PeriodicBehaviour):
        """
        Periodic behaviour that initiates product purchase requests to warehouses.
        
        This behaviour implements the initiation phase of the FIPA Contract Net Protocol.
        It sends a Call for Proposals (CFP) to all available warehouses, requesting quotes
        for a specific product and quantity. The behaviour executes periodically but only
        proceeds with a purchase based on a configured probability threshold.
        
        FIPA Protocol Phase: **Call for Proposals (CFP)**
            - Role: Initiator (Store agent)
            - Participants: All warehouses in contact list
            - Message type: `store-buy` (FIPA CFP equivalent)
            - Protocol: FIPA Contract Net Protocol
        
        The behaviour uses randomization to select products and quantities for each purchase,
        ensuring varied and realistic purchasing patterns. It then delegates response collection
        and warehouse selection to the CollectWarehouseResponses coordinator behaviour.
        
        Attributes:
            quantity (Optional[int]): Fixed quantity to purchase. If None, randomizes each run
                between 1 and max_buy_quantity.
            product (Optional[str]): Fixed product to purchase. If None, randomly selects from
                config.PRODUCTS each run.
            period (float): Time interval between executions in seconds (from config).
            start_at (datetime): Timestamp when the behaviour should first execute.
        
        Message Format (FIPA CFP):
            Metadata:
                - performative: "store-buy" (FIPA CFP)
                - store_id: Store's JID
                - node_id: Store's graph node ID
                - request_id: Unique request ID using hierarchical encoding
            Body:
                - Format: "{quantity} {product}"
                - Example: "50 electronics"
        
        Workflow:
            1. Roll random number (1-100) to determine if purchase should occur
            2. Compare roll against buy_prob threshold; skip if roll fails
            3. Randomize or use fixed quantity and product
            4. Generate unique request_id using ID encoding: id_base + request_counter
            5. Broadcast CFP to all warehouses in contact list
            6. Launch CollectWarehouseResponses to handle FIPA negotiation protocol
            7. Wait for negotiation to complete
        
        Notes:
            - Uses local variables (not self.quantity/self.product) to ensure proper
              randomization on each execution cycle.
            - Each execution generates a new request_id to avoid conflicts.
            - Waits for CollectWarehouseResponses to complete before finishing.
            - Probability mechanism prevents constant purchasing, simulating realistic demand.
        
        Example:
            ```python
            # Random purchases from config product list
            buy_behav = store.BuyProduct()
            
            # Fixed product and quantity for testing
            buy_behav = store.BuyProduct(quantity=100, product="electronics")
            ```
        """

        def __init__(self,
                     quantity : Optional[int] = None,
                     product : Optional[str] = None,
                     period=config.STORE_BUY_FREQUENCY,
                     start_at=datetime.now() + timedelta(seconds=5)):
            """
            Initialize the BuyProduct periodic behaviour.
            
            Args:
                quantity (Optional[int], optional): Fixed quantity to purchase each period.
                    If None, quantity is randomized between 1 and max_buy_quantity each run.
                    Defaults to None for varied purchasing patterns.
                product (Optional[str], optional): Fixed product name to purchase each period.
                    If None, product is randomly selected from config.PRODUCTS each run.
                    Defaults to None for varied product selection.
                period (float, optional): Time interval between executions in seconds.
                    Controls how frequently purchase attempts are made.
                    Defaults to config.STORE_BUY_FREQUENCY.
                start_at (datetime, optional): Timestamp when behaviour should first execute.
                    Allows delayed start for synchronized simulation initialization.
                    Defaults to 5 seconds from initialization time.
            
            Note:
                Using None for quantity and product (default) creates varied purchasing
                patterns that simulate realistic retail demand, while fixed values create
                predictable repeated orders useful for testing specific scenarios.
            """
            super().__init__(period=period, start_at=start_at)
            self.quantity = quantity
            self.product = product
        
        async def run(self):
            """
            Execute one cycle of the purchase request behaviour.
            
            This method implements the probabilistic purchase initiation logic and
            broadcasts FIPA CFP messages to all warehouses. It uses randomization for
            both the purchase decision (based on buy_prob) and the product/quantity
            selection (unless fixed values were provided in __init__).
            
            FIPA Protocol Implementation:
                - **Phase**: Call for Proposals (CFP) - Initiation
                - **Role**: Initiator
                - **Performative**: store-buy (FIPA CFP)
                - **Content**: "{quantity} {product}"
                - **Receivers**: All warehouses in contact list (broadcast)
                - **Protocol**: FIPA Contract Net Protocol
            
            The method generates a unique request_id using the Store's hierarchical ID
            encoding system before broadcasting to ensure all responses can be properly
            matched to this specific request.
            
            Workflow:
                1. **Probability Check**: Roll random number (1-100) for purchase decision
                2. **Threshold Comparison**: Compare roll against buy_prob * 100
                3. **Early Return**: If roll fails, abort and wait for next period
                4. **Randomization**: Generate or use fixed quantity and product
                5. **ID Generation**: Create unique request_id from id_base + request_counter
                6. **CFP Broadcast**: Send store-buy message to all warehouses
                7. **Coordinator Launch**: Start CollectWarehouseResponses for negotiation
                8. **Synchronization**: Wait for coordinator to complete FIPA protocol
            
            Side Effects:
                - Increments agent.request_counter (ensures unique IDs)
                - Updates agent.current_buy_request with last sent message
                - Adds CollectWarehouseResponses behaviour to agent
                - May print debug information if verbose mode is enabled
            
            Returns:
                None. Completes when CollectWarehouseResponses finishes the negotiation
                process and a warehouse is selected (or request fails).
            
            Note:
                Uses local variables (quantity, product) instead of instance variables
                to ensure proper randomization on each execution. This prevents the bug
                where the same product/quantity would be used repeatedly.
            """
            agent : Store = self.agent
            
            roll = random.randint(1,100)
            # Decide whether to buy this turn based on probability
            if roll > agent.buy_prob * 100:
                if agent.verbose:
                    print(f"{agent.jid}> Decided NOT to buy this turn (roll={roll} > buy_prob={agent.buy_prob})")
                return
            else: pass
            
            # Randomize quantity and product for each purchase
            if self.quantity is None: 
                quantity = random.randint(1, agent.max_buy_quantity)
            else:
                quantity = self.quantity
                
            if self.product is None:
                product = random.choice(agent.product_list)
            else:
                product = self.product
                
            print(f"{agent.jid}> Preparing to buy {quantity} units of {product}")
            
            contacts = list(agent.presence.contacts.keys())
            
            # Get request_id before sending - use ID encoding
            request_id_for_template = agent.id_base + agent.request_counter
            agent.request_counter += 1
            
            msg = None  # Will store the last sent message for current_buy_request
            for contact in contacts:
                msg = Message(to=contact)
                msg.set_metadata("performative", "store-buy")
                msg.set_metadata("store_id", str(agent.jid))
                msg.set_metadata("node_id", str(agent.node_id))
                msg.set_metadata("request_id", str(request_id_for_template))
                msg.body = f"{quantity} {product}"
                
                if agent.verbose:
                    print(f"{agent.jid}> Sent request (id={msg.get_metadata('request_id')}):"
                          f"\"{msg.body}\" to {msg.to}")
                
                await self.send(msg)
            
            # Store the last message (or could store all if needed)
            if msg:
                agent.current_buy_request = msg
        
                # Collect responses from all warehouses
                behav = agent.CollectWarehouseResponses(
                    msg, 
                    request_id_for_template, 
                    len(contacts),
                    quantity,
                    product
                )
                agent.add_behaviour(behav)
                
                await behav.join()

    class CollectWarehouseResponses(OneShotBehaviour):
        """
        Coordinator behaviour for FIPA Contract Net Protocol implementation.
        
        This behaviour orchestrates the proposal collection, evaluation, and award phases
        of the FIPA Contract Net Protocol. It acts as the coordinator (initiator) that
        manages the negotiation process with multiple warehouses, collects their responses,
        and selects the best proposal based on a distance-based scoring function.
        
        FIPA Protocol Phases Implemented:
            1. **Proposal Reception**: Collects warehouse responses (propose/refuse)
            2. **Proposal Evaluation**: Scores each acceptance using Dijkstra pathfinding
            3. **Award Decision**: Sends accept-proposal to winner, reject-proposal to losers
        
        The behaviour uses a coordinator/worker pattern:
            - **Coordinator** (this class): Manages overall protocol flow, evaluates proposals
            - **Worker** (ReceiveAllResponses): Handles actual message reception
        
        Scoring Algorithm:
            Uses Dijkstra pathfinding to calculate delivery time from each warehouse to store.
            - Formula: score = delivery_time (from warehouse to store)
            - Lower score = better choice (shorter delivery time)
            - Tie-breaking: First warehouse with minimum score wins
        
        FIPA Contract Net Protocol Flow:
            1. **Setup**: Create template matching request_id and store_id
            2. **Collection**: Launch ReceiveAllResponses worker to gather proposals
            3. **Wait**: Synchronize on worker completion (timeout: 5 seconds)
            4. **Evaluation**: Calculate scores for all acceptances
            5. **Selection**: Choose warehouse with minimum score
            6. **Award**: Send store-confirm to winner (FIPA accept-proposal)
            7. **Rejection**: Send store-deny to losers (FIPA reject-proposal)
            8. **Failure Handling**: Enqueue for retry if no acceptances received
        
        Attributes:
            request_id (int): Unique identifier for this purchase request from ID encoding.
            buy_msg (str): Original purchase message body ("{quantity} {product}").
            num_warehouses (int): Expected number of warehouse responses for timeout logic.
            quantity (int): Quantity of product being purchased.
            product (str): Name of product being purchased.
            acceptances (list[tuple[str, Message]]): Warehouses that proposed.
                Format: [(warehouse_jid, acceptance_msg), ...]
            rejections (list[tuple[str, Message, str]]): Warehouses that refused.
                Format: [(warehouse_jid, rejection_msg, reason), ...]
        
        Failure Handling:
            - If no warehouses accept: Request added to failed_requests queue
            - RetryPreviousBuy behaviour will automatically retry with same request_id
            - Failed requests maintain original request_id for tracking
        
        Example Workflow:
            ```
            CFP Sent: "50 electronics" (request_id=1001000000)
            Responses Received:
                - warehouse1: propose (distance=100, score=100)
                - warehouse2: propose (distance=50, score=50) <- WINNER
                - warehouse3: refuse (reason: out_of_stock)
            Actions Taken:
                - Send accept-proposal to warehouse2
                - Send reject-proposal to warehouse1
                - warehouse3 already refused, no action needed
            ```
        
        Note:
            This coordinator behaviour is essential for implementing the FIPA Contract Net
            Protocol correctly, separating concerns between message collection (worker) and
            decision-making (coordinator).
        """
        def __init__(self, msg : Message, request_id : int, num_warehouses : int, quantity : int, product : str):
            """
            Initialize the CollectWarehouseResponses coordinator behaviour.
            
            Args:
                msg (Message): Original purchase request message sent to warehouses.
                    Stored as reference for reconstructing failed requests if needed.
                request_id (int): Unique request identifier from hierarchical ID encoding system.
                    Used to match incoming responses to this specific CFP.
                num_warehouses (int): Expected number of warehouse responses.
                    Used to determine when all proposals have been received (or timeout).
                quantity (int): Quantity of product being purchased.
                    Needed for order processing and statistics tracking.
                product (str): Name of product being purchased.
                    Needed for order processing and statistics tracking.
            
            Note:
                Initializes empty acceptances and rejections lists that will be
                populated by the ReceiveAllResponses worker behaviour through
                shared reference (list objects are mutable).
            """
            super().__init__()
            self.request_id = request_id
            self.buy_msg = msg.body
            self.num_warehouses = num_warehouses
            self.quantity = quantity
            self.product = product
            self.acceptances = []  # List of (warehouse_jid, msg)
            self.rejections = []   # List of (warehouse_jid, msg, reason)
            
        async def run(self):
            """
            Execute the warehouse proposal collection and evaluation process.
            
            This method coordinates the entire FIPA Contract Net Protocol workflow
            for warehouse selection. It sets up message filtering, launches the worker
            behaviour for response collection, evaluates all proposals using a scoring
            algorithm, and sends confirmations/rejections to participants according to
            the FIPA protocol specification.
            
            FIPA Contract Net Protocol Implementation:
            
            1. **Setup Phase** (FIPA: Preparation):
                - Creates template matching request_id and store_id metadata
                - Allows both warehouse-accept (propose) and warehouse-reject (refuse)
                - Ensures only responses for THIS specific request are collected
                - Prevents cross-contamination between concurrent requests
            
            2. **Collection Phase** (FIPA: Proposal Reception):
                - Delegates to ReceiveAllResponses worker behaviour
                - Worker populates acceptances (proposals) and rejections (refusals) lists
                - Implements timeout mechanism (5 seconds total)
                - Handles partial responses gracefully (some warehouses may not respond)
            
            3. **Evaluation Phase** (FIPA: Proposal Evaluation):
                - Calculates score for each acceptance using calculate_warehouse_score()
                - Score based on Dijkstra pathfinding: delivery_time from warehouse to store
                - Selects warehouse with lowest score (shortest delivery time)
                - Implements best-proposal selection strategy from FIPA specification
            
            4. **Award Phase** (FIPA: Result Notification):
                - Sends store-confirm to winner (FIPA accept-proposal performative)
                - Sends store-deny to all other acceptors (FIPA reject-proposal performative)
                - Rejected participants (warehouse-reject) are not contacted again
                - Winner proceeds to order confirmation and vehicle assignment
            
            5. **Failure Handling**:
                - If no acceptances received: Adds request to failed_requests queue
                - Failed requests automatically retried by RetryPreviousBuy behaviour
                - Maintains same request_id for tracking across retry attempts
            
            Template Configuration:
                - **Matches**: store_id (this store) AND request_id (this specific request)
                - **Accepts**: Both warehouse-accept AND warehouse-reject performatives
                - **Purpose**: Filters responses to avoid conflicts with concurrent requests
                - **Design**: Intentionally doesn't filter by performative to collect all responses
            
            Scoring Process (Distance-Based Selection):
                For each warehouse that sent propose (warehouse-accept):
                1. Extract warehouse node_id from message metadata
                2. Use Dijkstra algorithm: calculate (path, fuel, time) warehouse -> store
                3. Score = delivery time (lower is better)
                4. Select warehouse with minimum score
                5. Tie-breaking: First warehouse with minimum score wins
            
            Side Effects:
                - Adds ReceiveAllResponses worker behaviour to agent (with template)
                - Adds SendStoreConfirmation behaviour for winner
                - Adds SendStoreDenial behaviour for each non-winner
                - May enqueue failed request to failed_requests queue
                - Prints evaluation details if verbose mode enabled
            
            Returns:
                None. Completes when all confirmations/denials are sent, or when
                failed request is enqueued for retry.
            
            Example Execution:
                ```
                CFP: "50 electronics" to 3 warehouses
                Responses:
                    - warehouse1: accept (node_id=10, distance=150, score=150)
                    - warehouse2: accept (node_id=5, distance=80, score=80) <- WINNER
                    - warehouse3: reject (reason=out_of_stock)
                Actions:
                    - SendStoreConfirmation(warehouse2) -> accept-proposal
                    - SendStoreDenial(warehouse1) -> reject-proposal
                    - No action for warehouse3 (already refused)
                Result: Order placed with warehouse2
                ```
            
            Note:
                This method implements the core decision-making logic of the FIPA Contract
                Net Protocol, transforming raw proposals into a concrete purchase order with
                the optimal warehouse.
            """
            agent : Store = self.agent
            
            # Setup template that accepts BOTH warehouse-accept AND warehouse-reject
            template = Template()
            template.set_metadata("store_id", str(agent.jid))
            template.set_metadata("request_id", str(self.request_id))
            # Don't filter by performative - we want both accept and reject
            
            # Create a combined behaviour to listen for both
            combined_behav = agent.ReceiveAllResponses(
                self.request_id,
                self.num_warehouses,
                self.acceptances,
                self.rejections
            )
            
            # Add with template that matches both performatives
            agent.add_behaviour(combined_behav, template)
            
            # Wait for collection to complete
            await combined_behav.join()
            
            # Now evaluate and choose best warehouse
            if self.acceptances:
                if agent.verbose:
                    print(f"{agent.jid}> Received {len(self.acceptances)} acceptance(s) and {len(self.rejections)} rejection(s)")
                
                # Calculate scores for each warehouse that accepted
                best_warehouse = None
                best_score = float('inf')
                
                
                for warehouse_jid, msg in self.acceptances:
                    score = agent.calculate_warehouse_score(msg)
                    if agent.verbose:
                        print(f"{agent.jid}> Warehouse {warehouse_jid} score: {score}")
                    
                    if score < best_score:
                        best_score = score
                        best_warehouse = (warehouse_jid, msg)
                
                if best_warehouse:
                    warehouse_jid, accept_msg = best_warehouse
                    if agent.verbose:
                        print(f"{agent.jid}> Selected warehouse {warehouse_jid} with score {best_score}")
                    
                    # Send confirmation to the chosen warehouse
                    confirm_behav = agent.SendStoreConfirmation(accept_msg)
                    agent.add_behaviour(confirm_behav)
                    await confirm_behav.join()
                    
                    # Send denial to other warehouses that accepted but weren't chosen
                    for other_warehouse_jid, other_msg in self.acceptances:
                        if other_warehouse_jid != warehouse_jid:
                            deny_behav = agent.SendStoreDenial(other_msg)
                            agent.add_behaviour(deny_behav)
                            await deny_behav.join()
                            if agent.verbose:
                                print(f"{agent.jid}> Sent denial to {other_warehouse_jid}")
                    
            else:
                if agent.verbose:
                    print(f"{agent.jid}> No acceptances received. All warehouses rejected or timed out.")
                    print(f"{agent.jid}> Request saved in self.failed_requests")
                
                # Add to failed requests
                failed_msg = Message(to=agent.current_buy_request.to)
                agent.set_buy_metadata(failed_msg)
                failed_msg.set_metadata("request_id", str(self.request_id))
                failed_msg.body = self.buy_msg
                agent.failed_requests.put(failed_msg)

    class ReceiveAllResponses(OneShotBehaviour):
        """
        Worker behaviour for collecting warehouse responses in FIPA Contract Net Protocol.
        
        This behaviour acts as the worker component in a coordinator/worker pattern,
        handling the actual message reception during the proposal collection phase of
        the FIPA Contract Net Protocol. It listens for both proposals (warehouse-accept)
        and refusals (warehouse-reject) from warehouses, populating shared lists that
        the coordinator (CollectWarehouseResponses) will evaluate.
        
        FIPA Protocol Phase: **Proposal Reception**
            - Role: Participant response collector (worker)
            - Coordinator: CollectWarehouseResponses
            - Expected messages: warehouse-accept (propose) and warehouse-reject (refuse)
            - Timeout: 5 seconds total for all responses
        
        The behaviour implements a timeout mechanism to handle scenarios where some
        warehouses may be slow to respond or unavailable. It collects responses until
        either all expected warehouses respond or the timeout expires.
        
        Attributes:
            request_id (int): Unique request identifier for filtering messages.
                Ensures only responses for this specific CFP are processed.
            num_warehouses (int): Expected number of warehouse responses.
                Used to determine when collection is complete.
            acceptances (list[tuple[str, Message]]): Shared list with coordinator.
                Populated with (warehouse_jid, message) for each propose.
            rejections (list[tuple[str, Message, str]]): Shared list with coordinator.
                Populated with (warehouse_jid, message, reason) for each refuse.
            responses_received (int): Counter tracking received responses.
                Incremented for both accepts and rejects.
            timeout (int): Maximum seconds to wait for all responses (default: 5).
        
        Message Processing:
            - **warehouse-accept** (FIPA propose):
                Body format: "{quantity} {product}"
                Action: Append (warehouse_jid, msg) to acceptances
            
            - **warehouse-reject** (FIPA refuse):
                Body format: "{quantity} {product} {reason}"
                Action: Append (warehouse_jid, msg, reason) to rejections
        
        Timeout Logic:
            - Tracks elapsed time from start
            - Calculates remaining_timeout for each receive() call
            - Breaks early if remaining_timeout <= 0
            - Allows partial responses (fewer than num_warehouses)
        
        Example Execution:
            ```
            Expected: 3 warehouses
            Timeline:
                t=0.5s: warehouse1 -> accept (1/3 received)
                t=1.2s: warehouse2 -> reject (2/3 received)
                t=5.0s: timeout reached (warehouse3 no response)
            Result:
                acceptances = [(warehouse1, msg1)]
                rejections = [(warehouse2, msg2, "out_of_stock")]
                responses_received = 2
            ```
        
        Note:
            This worker behaviour uses shared list references (not copies) to communicate
            with the coordinator, following the coordinator/worker pattern for efficient
            data sharing between behaviours.
        """
        def __init__(self, request_id : int, num_warehouses : int, acceptances : list, rejections : list):
            """
            Initialize the ReceiveAllResponses worker behaviour.
            
            Args:
                request_id (int): Unique request identifier from ID encoding system.
                    Used to filter incoming messages to only this CFP's responses.
                num_warehouses (int): Expected number of warehouse responses.
                    Used to determine when all responses received (early termination).
                acceptances (list[tuple[str, Message]]): Shared list reference with coordinator.
                    Worker appends (warehouse_jid, msg) for each warehouse-accept received.
                    Modifications visible to coordinator through shared reference.
                rejections (list[tuple[str, Message, str]]): Shared list reference with coordinator.
                    Worker appends (warehouse_jid, msg, reason) for each warehouse-reject.
                    Modifications visible to coordinator through shared reference.
            
            Note:
                Lists are shared by reference (mutable), enabling communication between
                worker and coordinator without explicit return values. This is a common
                pattern in concurrent programming with SPADE behaviours.
            """
            super().__init__()
            self.request_id = request_id
            self.num_warehouses = num_warehouses
            self.acceptances = acceptances  # Shared list
            self.rejections = rejections    # Shared list
            self.responses_received = 0
            self.timeout = 5  # seconds to wait for all responses
            
        async def run(self):
            """
            Execute the message collection loop for warehouse responses.
            
            This method implements the core collection logic for the FIPA Contract Net
            Protocol proposal reception phase. It continuously receives messages from
            warehouses until either all expected responses arrive or a timeout occurs,
            properly categorizing each response as either a proposal or refusal.
            
            FIPA Protocol Implementation:
                - **Phase**: Proposal Reception (collecting propose/refuse messages)
                - **Role**: Worker (collects data for coordinator evaluation)
                - **Timeout**: 5 seconds total (not per message)
                - **Partial Completion**: Accepts fewer responses than expected
            
            Algorithm:
                1. **Initialization**: Record start time for timeout calculation
                2. **Collection Loop**: While responses_received < num_warehouses:
                    a. Calculate remaining timeout based on elapsed time
                    b. Check for timeout expiration (remaining_timeout <= 0)
                    c. Receive message with dynamically calculated timeout
                    d. Parse message: extract performative, sender, and body
                    e. Categorize as acceptance or rejection
                    f. Append to appropriate shared list
                    g. Increment responses_received counter
                3. **Termination**: Break on timeout or no more messages
            
            Message Processing:
            
                **warehouse-accept** (FIPA propose):
                    - Body format: "{quantity} {product}"
                    - Parsing: Split on space, extract quantity (int) and product (str)
                    - Action: Append (warehouse_jid, msg) to acceptances list
                    - Meaning: Warehouse agrees to fulfill order
                
                **warehouse-reject** (FIPA refuse):
                    - Body format: "{quantity} {product} {reason}"
                    - Parsing: Split on space, extract quantity, product, and optional reason
                    - Action: Append (warehouse_jid, msg, reason) to rejections list
                    - Default reason: "unknown" if not provided
                    - Meaning: Warehouse cannot or will not fulfill order
            
            Timeout Mechanism:
                - **Total Timeout**: 5 seconds from method start
                - **Dynamic Calculation**: remaining_timeout = total_timeout - elapsed_time
                - **Per-Message Timeout**: Each receive() uses remaining_timeout
                - **Early Termination**: Breaks immediately if remaining_timeout <= 0
                - **Graceful Handling**: Allows partial responses without error
            
            Example Execution Timeline:
                ```
                t=0.0s: Start collection (expecting 3 responses)
                t=0.3s: Receive warehouse1 accept -> acceptances.append()
                t=0.8s: Receive warehouse2 reject -> rejections.append()
                t=5.0s: Timeout reached (warehouse3 silent)
                Result: 2/3 responses collected
                ```
            
            Side Effects:
                - Populates self.acceptances shared list with proposals
                - Populates self.rejections shared list with refusals
                - Increments self.responses_received counter
                - Prints debug information if verbose mode enabled
                - May terminate early due to timeout
            
            Returns:
                None. Results communicated through shared list references.
            
            Note:
                The timeout is global (not per-message), ensuring the entire collection
                process completes within 5 seconds regardless of warehouse count. This
                prevents indefinite waiting when warehouses are unresponsive.
            """
            agent : Store = self.agent
            
            import time
            start_time = time.time()
            
            while self.responses_received < self.num_warehouses:
                elapsed = time.time() - start_time
                remaining_timeout = self.timeout - elapsed
                
                if remaining_timeout <= 0:
                    if agent.verbose:
                        print(f"{agent.jid}> Timeout: Only received {self.responses_received}/{self.num_warehouses} responses")
                    break
                
                msg : Message = await self.receive(timeout=remaining_timeout)
                
                if msg:
                    performative = msg.get_metadata("performative")
                    warehouse_jid = str(msg.sender)
                    
                    if performative == "warehouse-accept":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        
                        if agent.verbose:
                            print(f"{agent.jid}> Received acceptance from {warehouse_jid}: {quantity} {product}")
                        self.acceptances.append((warehouse_jid, msg))
                        
                    elif performative == "warehouse-reject":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        reason = parts[2] if len(parts) > 2 else "unknown"
                        
                        if agent.verbose:
                            print(f"{agent.jid}> Received rejection from {warehouse_jid}: {quantity} {product} (reason: {reason})")
                        self.rejections.append((warehouse_jid, msg, reason))
                    
                    self.responses_received += 1
                else:
                    # No more messages, timeout
                    break
            
            if agent.verbose:
                print(f"{agent.jid}> Finished collecting responses: {len(self.acceptances)} accepts, {len(self.rejections)} rejects")

    class SendStoreConfirmation(OneShotBehaviour):
        """
        Behaviour to send confirmation to the selected warehouse (FIPA accept-proposal).
        
        This behaviour implements the award notification phase of the FIPA Contract Net
        Protocol, informing the winning warehouse that its proposal has been accepted.
        It sends the FIPA accept-proposal message and registers the order as pending
        delivery, waiting for a vehicle to transport the goods.
        
        FIPA Protocol Phase: **Result Notification - Award**
            - Performative: store-confirm (FIPA accept-proposal)
            - Recipient: Selected warehouse (winner of proposal evaluation)
            - Purpose: Officially award the contract to the best proposal
            - Protocol: FIPA Contract Net Protocol
        
        This behaviour does NOT update stock immediately. Stock updates occur only when
        the vehicle delivers the products (upon receiving vehicle-delivery message).
        This design accurately models real-world supply chains where confirmation precedes
        actual inventory arrival.
        
        Attributes:
            dest (str): Warehouse JID (winner's address).
            request_id (str): Unique request identifier from original CFP.
            quantity (int): Quantity of product in the confirmed order.
            product (str): Name of product in the confirmed order.
            msg (Message): Original warehouse-accept message (for Order conversion).
        
        Message Format (FIPA accept-proposal):
            Metadata:
                - performative: "store-confirm" (FIPA accept-proposal)
                - warehouse_id: Destination warehouse JID
                - store_id: This store's JID
                - node_id: This store's graph location
                - request_id: Original CFP request identifier
            Body:
                - Format: "{quantity} {product}"
                - Example: "50 electronics"
        
        Side Effects:
            - Converts message to Order object using message_to_order()
            - Adds order to agent.pending_deliveries dict (key: order_id)
            - Records confirmation timestamp in agent.order_timings (for statistics)
            - Sends store-confirm message to warehouse
            - Prints confirmation details (always visible, not verbose-only)
        
        Workflow:
            1. Convert warehouse-accept message to Order object
            2. Register order in pending_deliveries (awaiting vehicle)
            3. Record current tick in order_timings (for time-to-delivery calculation)
            4. Construct store-confirm message with proper metadata
            5. Send confirmation to warehouse
            6. Print success message with order details
        
        Example:
            ```
            Warehouse: warehouse2@localhost
            Request: "50 electronics" (ID: 1001000000)
            Action: Send store-confirm to warehouse2
            Result: Order 1001000000 pending delivery
            Print: "Successfully bought 50 xelectronics from warehouse2..."
            ```
        
        Note:
            The confirmation message triggers the warehouse to assign a vehicle for
            delivery. The store then waits for vehicle-delivery message to update stock.
        """
        def __init__(self, msg : Message):
            """
            Initialize the SendStoreConfirmation behaviour.
            
            Args:
                msg (Message): The warehouse-accept message from the winning warehouse.
                    Contains all necessary information: sender, request_id, quantity, product.
                    Used to construct the confirmation message and create Order object.
            
            Note:
                Extracts and stores all relevant fields from the message for use in run().
                The original message is preserved for Order object conversion.
            """
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
            self.msg : Message = msg
            
        
        async def run(self):
            """
            Execute the confirmation sending process (FIPA accept-proposal).
            
            This method sends the FIPA accept-proposal message to the winning warehouse,
            registers the order as pending delivery, and records timing information for
            statistics. It implements the award notification phase of the FIPA Contract
            Net Protocol.
            
            FIPA Protocol Implementation:
                - **Phase**: Result Notification - Award
                - **Performative**: store-confirm (FIPA accept-proposal)
                - **Meaning**: "Your proposal is accepted, prepare the order"
                - **Expected Response**: Warehouse assigns vehicle for delivery
            
            Important Design Decision:
                Stock is NOT updated immediately upon confirmation. Stock updates occur
                only when the vehicle delivers the products (vehicle-delivery message).
                This accurately models real-world logistics where confirmation ≠ possession.
            
            Workflow:
                1. **Order Conversion**: Convert warehouse-accept message to Order object
                    - Extracts: product, quantity, orderid, sender, receiver, locations
                    - Uses message_to_order() helper method
                
                2. **Order Registration**: Add to pending_deliveries dict
                    - Key: order.orderid (unique request ID)
                    - Value: Order object with full details
                    - Purpose: Track orders awaiting vehicle delivery
                
                3. **Timing Record**: Store current tick in order_timings
                    - Key: order.orderid
                    - Value: agent.current_tick (simulation time)
                    - Purpose: Calculate time-to-delivery for statistics
                
                4. **Message Construction**: Build store-confirm message
                    - Performative: store-confirm (FIPA accept-proposal)
                    - Metadata: warehouse_id, store_id, node_id, request_id
                    - Body: "{quantity} {product}"
                
                5. **Message Transmission**: Send confirmation to warehouse
                    - Triggers warehouse to assign vehicle
                    - Initiates delivery logistics process
                
                6. **Status Logging**: Print confirmation details
                    - Verbose message: Confirmation sent details
                    - Essential message: Order success with order ID
            
            Side Effects:
                - Modifies agent.pending_deliveries (adds order)
                - Modifies agent.order_timings (records timestamp)
                - Sends SPADE message to warehouse
                - Prints status information to console
            
            Returns:
                None. Completes when confirmation message is sent.
            
            Example Execution:
                ```
                Input: warehouse-accept from warehouse2
                    Body: "50 electronics"
                    request_id: 1001000000
                Processing:
                    - Create Order(orderid=1001000000, quantity=50, product="electronics")
                    - pending_deliveries[1001000000] = Order(...)
                    - order_timings[1001000000] = 42 (current tick)
                Output:
                    - Send store-confirm to warehouse2
                    - Print: "Successfully bought 50 xelectronics from warehouse2 under order id 1001000000"
                ```
            
            Note:
                The order remains in pending_deliveries until ReceiveVehicleArrival
                processes the vehicle-delivery message and updates stock. This maintains
                separation between contract award and physical delivery.
            """
            agent : Store = self.agent
            
            # Don't update stock here - wait for vehicle delivery
            # Stock will be updated when vehicle-delivery message is received
            order : Order = agent.message_to_order(self.msg)
            agent.pending_deliveries[order.orderid] = order
            agent.order_timings[order.orderid] = agent.current_tick
            
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "store-confirm")
            msg.set_metadata("warehouse_id", str(self.dest))
            msg.set_metadata("store_id", str(agent.jid))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            
            if agent.verbose:
                print(f"{agent.jid}> Confirmation sent to {self.dest} for request: {msg.body}")
            
            print(f"{agent.jid}> Successully bought {self.quantity} x{self.product} from {self.dest} under order id {order.orderid}")

    class SendStoreDenial(OneShotBehaviour):
        """
        Behaviour to send rejection to non-selected warehouses (FIPA reject-proposal).
        
        This behaviour implements the rejection notification phase of the FIPA Contract
        Net Protocol, informing warehouses that submitted proposals that their bids were
        not selected. This is an essential part of the protocol, providing feedback to
        all participants about the outcome of the negotiation.
        
        FIPA Protocol Phase: **Result Notification - Rejection**
            - Performative: store-deny (FIPA reject-proposal)
            - Recipients: Warehouses that proposed but were not selected
            - Purpose: Inform participants their proposal was rejected
            - Protocol: FIPA Contract Net Protocol
            - Note: Warehouses that refused (warehouse-reject) do NOT receive this
        
        This message allows warehouses to release any resources they may have reserved
        for this order and update their internal state accordingly.
        
        Attributes:
            dest (str): Warehouse JID (non-selected participant's address).
            request_id (str): Unique request identifier from original CFP.
            quantity (int): Quantity of product in the rejected order.
            product (str): Name of product in the rejected order.
        
        Message Format (FIPA reject-proposal):
            Metadata:
                - performative: "store-deny" (FIPA reject-proposal)
                - warehouse_id: Destination warehouse JID
                - store_id: This store's JID
                - node_id: This store's graph location
                - request_id: Original CFP request identifier
            Body:
                - Format: "{quantity} {product}"
                - Example: "50 electronics"
        
        Side Effects:
            - Sends store-deny message to warehouse
            - Prints denial confirmation (verbose mode only)
        
        Example:
            ```
            Scenario: 3 warehouses proposed, warehouse2 won
            Recipients: warehouse1, warehouse3 (both receive store-deny)
            Message: "50 electronics"
            Result: warehouse1 and warehouse3 know they were not selected
            ```
        
        Note:
            This notification is important for warehouses to maintain accurate internal
            state and avoid waiting indefinitely for a confirmation that will never come.
        """
        def __init__(self, msg : Message):
            """
            Initialize the SendStoreDenial behaviour.
            
            Args:
                msg (Message): The warehouse-accept message from the non-selected warehouse.
                    Contains sender information and order details needed for rejection message.
            
            Note:
                Extracts only the essential fields needed to construct the rejection.
                Unlike SendStoreConfirmation, this doesn't need to create an Order object.
            """
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
        
        async def run(self):
            """
            Execute the rejection sending process (FIPA reject-proposal).
            
            This method sends the FIPA reject-proposal message to non-selected warehouses,
            completing the result notification phase of the FIPA Contract Net Protocol.
            
            FIPA Protocol Implementation:
                - **Phase**: Result Notification - Rejection
                - **Performative**: store-deny (FIPA reject-proposal)
                - **Meaning**: "Your proposal was not selected"
                - **Expected Response**: Warehouse releases resources, updates state
            
            Workflow:
                1. **Message Construction**: Build store-deny message
                    - Performative: store-deny (FIPA reject-proposal)
                    - Metadata: warehouse_id, store_id, node_id, request_id
                    - Body: "{quantity} {product}"
                
                2. **Message Transmission**: Send rejection to warehouse
                    - Notifies warehouse of negative outcome
                    - Allows warehouse to handle rejection gracefully
                
                3. **Status Logging**: Print denial confirmation (verbose only)
            
            Side Effects:
                - Sends SPADE message to warehouse
                - Prints status information if verbose mode enabled
            
            Returns:
                None. Completes when rejection message is sent.
            
            Example Execution:
                ```
                Input: warehouse-accept from warehouse1 (not selected)
                    Body: "50 electronics"
                    request_id: 1001000000
                Processing:
                    - Create store-deny message
                    - Set metadata and body
                Output:
                    - Send store-deny to warehouse1
                    - Print (if verbose): "Denial sent to warehouse1 for request: 50 electronics"
                ```
            """
            agent : Store = self.agent
            
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "store-deny")
            msg.set_metadata("warehouse_id", str(self.dest))
            msg.set_metadata("store_id", str(agent.jid))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            
            if agent.verbose:
                print(f"{agent.jid}> Denial sent to {self.dest} for request: {msg.body}")
    
    class RetryPreviousBuy(PeriodicBehaviour):
        """
        Periodic behaviour that retries failed purchase requests.
        
        This behaviour implements automatic retry logic for purchase requests that failed
        due to all warehouses rejecting or timing out. It periodically checks the
        failed_requests queue and re-initiates the FIPA Contract Net Protocol for any
        pending failed requests.
        
        Failure Scenarios:
            - All warehouses sent warehouse-reject (refuse)
            - All warehouses timed out (no response)
            - Mix of rejects and timeouts with zero acceptances
        
        The behaviour maintains the original request_id for tracking and statistics,
        allowing correlation between original attempt and retry attempts in logs.
        
        Attributes:
            Inherited from PeriodicBehaviour:
                - period (float): Time between retry attempts (default: 5 seconds)
                - Executes continuously while agent is running
        
        Retry Logic:
            - Checks failed_requests queue (FIFO)
            - Dequeues one request per execution
            - Preserves original request_id (no new ID generated)
            - Re-broadcasts CFP to all warehouses
            - Launches CollectWarehouseResponses coordinator
        
        FIPA Protocol:
            Restarts the entire FIPA Contract Net Protocol:
            1. Call for Proposals (CFP) - re-broadcast with same request_id
            2. Proposal Reception - collect new responses
            3. Proposal Evaluation - score and select best warehouse
            4. Result Notification - confirm winner, deny losers
        
        Workflow:
            1. **Queue Check**: Test if failed_requests queue is empty
            2. **Dequeue**: Get oldest failed request from queue
            3. **Parse**: Extract request_id, quantity, product from message
            4. **Re-broadcast**: Send store-buy to all warehouses (same request_id)
            5. **Coordinate**: Launch CollectWarehouseResponses for this retry
            6. **Synchronize**: Wait for coordinator to complete
            7. **Repeat**: Next period, check queue again
        
        Example Execution:
            ```
            Initial Attempt (t=10s):
                - Request "50 electronics" (ID: 1001000000)
                - All warehouses reject or timeout
                - Added to failed_requests queue
            
            Retry Attempt (t=15s):
                - Dequeue request 1001000000
                - Re-broadcast to all warehouses (same ID)
                - New responses: warehouse2 accepts
                - Success: Order placed with warehouse2
            ```
        
        Side Effects:
            - Dequeues from agent.failed_requests
            - Sends store-buy messages to all warehouses
            - Adds CollectWarehouseResponses behaviour
            - Prints retry information if verbose mode enabled
        
        Notes:
            - Retries use the SAME request_id as original attempt
            - No limit on retry attempts (will retry until success)
            - Failed retries are re-enqueued by CollectWarehouseResponses
            - Period of 5 seconds prevents overwhelming warehouses
        """
        async def run(self):
            """
            Execute one retry cycle for failed purchase requests.
            
            This method checks the failed_requests queue and, if not empty, dequeues
            one request and re-initiates the FIPA Contract Net Protocol with the same
            request_id. This maintains traceability across retry attempts.
            
            Workflow:
                1. **Queue Check**: If failed_requests is empty, do nothing
                2. **Dequeue Request**: Get oldest failed request (FIFO order)
                3. **Extract Data**: Parse request_id, quantity, product from message
                4. **Count Participants**: Get number of warehouses for response tracking
                5. **Rebuild Messages**: Create new store-buy messages for each warehouse
                6. **Broadcast CFP**: Send retry request to all warehouses
                7. **Launch Coordinator**: Start CollectWarehouseResponses with same request_id
                8. **Wait**: Synchronize on coordinator completion
            
            Request ID Preservation:
                The original request_id is preserved across retries, enabling:
                - Statistics tracking (correlate original and retries)
                - Debugging (trace request lifecycle)
                - Avoiding duplicate processing (warehouses can detect retries)
            
            Side Effects:
                - Removes one message from agent.failed_requests queue
                - Sends multiple store-buy messages (one per warehouse)
                - Adds CollectWarehouseResponses behaviour to agent
                - Prints retry notifications if verbose mode enabled
            
            Returns:
                None. Completes when coordinator finishes negotiation, or immediately
                if queue is empty.
            
            Example Execution:
                ```
                Queue State: [Request(ID=1001000000, "50 electronics")]
                Processing:
                    - Dequeue: Request 1001000000
                    - Parse: quantity=50, product="electronics"
                    - Broadcast: Send to warehouse1, warehouse2, warehouse3
                    - Coordinate: Launch CollectWarehouseResponses(1001000000, ...)
                    - Wait: Until new responses collected and evaluated
                Result:
                    - If success: Order placed
                    - If failure: Re-enqueued for next retry cycle
                ```
            
            Note:
                This method processes only ONE request per execution cycle (period=5s).
                This prevents flooding warehouses with retry requests and allows
                gradual processing of the failed_requests backlog.
            """
            agent : Store = self.agent
            
            if not agent.failed_requests.empty():
                request : Message = agent.failed_requests.get()
                request_id = request.get_metadata("request_id")
                parts = request.body.split(" ")
                quantity = int(parts[0])
                product = parts[1]
                
                contacts = list(agent.presence.contacts.keys())
                num_warehouses = len(contacts)
                
                for contact in contacts:
                    msg : Message = Message(to=contact)
                    agent.set_buy_metadata(msg)
                    msg.set_metadata("node_id", str(agent.node_id))
                    msg.set_metadata("request_id", str(request_id))
                    msg.body = request.body

                    if agent.verbose:
                        print(f"{self.agent.jid}> Retrying request (id={request_id}):"
                              f"\"{msg.body}\" to {msg.to}")

                    await self.send(msg)

                # Use CollectWarehouseResponses instead
                behav = agent.CollectWarehouseResponses(msg, request_id, quantity, product, num_warehouses)
                agent.add_behaviour(behav)
                await behav.join()
    
    class ReceiveTimeDelta(CyclicBehaviour):
        """
        Cyclic behaviour that processes simulation time updates and traffic information.
        
        This behaviour listens for time synchronization messages from the world agent,
        updating the store's internal clock and applying dynamic traffic changes to the
        graph. It implements an event-driven architecture where the world agent controls
        simulation time progression.
        
        Message Types Processed:
            1. **Time Updates** (all messages):
                - Updates agent.current_tick with time delta
                - Synchronizes store with global simulation time
            
            2. **Traffic Updates** (type="Transit"):
                - Applies dynamic edge weight changes to graph
                - Updates fuel consumption values for routes
                - Reflects real-time traffic conditions
        
        Message Format:
            Metadata:
                - performative: "inform"
            Body (JSON):
                ```json
                {
                    "type": "Transit",  // or other types
                    "time": 5,          // delta in ticks
                    "data": {
                        "edges": [
                            {
                                "node1": 1,
                                "node2": 2,
                                "weight": 150,
                                "fuel_consumption": 12.5
                            },
                            ...
                        ]
                    }
                }
                ```
        
        Attributes:
            Inherits from CyclicBehaviour:
                - Runs continuously in infinite loop
                - Processes one message per cycle
                - 20-second timeout per receive attempt
        
        Workflow:
            1. **Receive Message**: Wait up to 20 seconds for inform message
            2. **Parse JSON**: Extract type, time delta, and data
            3. **Update Time**: Increment current_tick by delta
            4. **Check Type**: If type is "Transit", process traffic updates
            5. **Update Graph**: Apply edge weight changes using update_graph()
            6. **Repeat**: Return to step 1 (cyclic behaviour)
        
        Traffic Update Process:
            When type="Transit":
                - Extract edges array from data field
                - For each edge: update weight and fuel_consumption
                - Uses update_graph() helper method
                - Affects pathfinding calculations in warehouse selection
        
        Example Execution:
            ```
            Message Received:
                {
                    "type": "Transit",
                    "time": 3,
                    "data": {
                        "edges": [
                            {"node1": 5, "node2": 10, "weight": 200, "fuel_consumption": 15.0}
                        ]
                    }
                }
            Processing:
                - current_tick: 42 -> 45 (increment by 3)
                - Update edge (5, 10): weight=200, fuel=15.0
                - Next warehouse selection uses new weights
            ```
        
        Side Effects:
            - Increments agent.current_tick (time synchronization)
            - Modifies agent.map edge weights (traffic updates)
            - Affects future pathfinding and warehouse scoring
        
        Returns:
            Never returns (cyclic behaviour runs until agent stops).
        
        Note:
            The 20-second timeout prevents indefinite blocking if world agent stops
            sending updates. This is a safety mechanism for graceful degradation.
        """
        async def run(self):
            """
            Execute one cycle of time delta reception and processing.
            
            This method receives one time synchronization message, updates the store's
            internal clock, and applies any traffic updates to the graph if present.
            
            Workflow:
                1. **Receive**: Wait up to 20 seconds for inform message
                2. **Validation**: Check if message received (not None)
                3. **Parse**: Deserialize JSON body
                4. **Extract**: Get type, time delta from JSON
                5. **Sync Time**: Add delta to current_tick
                6. **Check Type**: Test if type is "Transit" (case-insensitive)
                7. **Update Graph**: If Transit, apply edge changes via update_graph()
            
            Time Synchronization:
                Every message (regardless of type) causes time advancement:
                - current_tick += delta
                - Keeps store synchronized with global simulation time
                - Used for order timing statistics
            
            Traffic Updates:
                Only Transit messages include graph updates:
                - data.edges contains array of edge changes
                - Each edge: node1, node2, new weight, fuel_consumption
                - Calls update_graph() to apply changes atomically
            
            Side Effects:
                - Always increments agent.current_tick
                - Conditionally modifies agent.map (if Transit message)
            
            Returns:
                None. Continues to next cycle after processing one message.
            
            Example:
                ```
                Input: {"type": "Transit", "time": 2, "data": {"edges": [...]}}
                Effect:
                    - current_tick: 100 -> 102
                    - Graph edges updated with new weights
                Next Cycle: Wait for next message
                ```
            """
            agent : Store = self.agent
            
            msg : Message = await self.receive(timeout=20)
            
            if msg != None:
                data = json.loads(msg.body)
                
                type : str = data["type"]
                delta : int = data["time"]
                agent.current_tick += delta
                
                if type.lower() == "transit":
                    map_updates = data["data"]
                    agent.update_graph(map_updates)         
    
    class ReceiveVehicleArrival(CyclicBehaviour):
        """
        Cyclic behaviour that handles vehicle delivery notifications.
        
        This behaviour processes delivery completion messages from vehicle agents,
        updating inventory when products arrive at the store. It represents the final
        step in the supply chain: physical delivery and stock replenishment.
        
        Message Types Accepted:
            - **vehicle-delivery**: Vehicle completed delivery to store (primary)
            - **vehicle-pickup**: Vehicle picked up goods from warehouse (informational)
        
        The behaviour is filtered by template to only receive vehicle-delivery messages,
        but includes validation as a safety mechanism.
        
        Message Format:
            Metadata:
                - performative: "vehicle-delivery"
                - sender: Vehicle JID
            Body (JSON):
                ```json
                {
                    "orderid": 1001000000,  // Unique order identifier
                    "time": 150             // ETA or delivery time
                }
                ```
        
        Attributes:
            Inherits from CyclicBehaviour:
                - Runs continuously in infinite loop
                - Processes one message per cycle
                - 20-second timeout per receive attempt
        
        Workflow:
            1. **Receive Message**: Wait up to 20 seconds for vehicle-delivery
            2. **Validate Performative**: Verify it's vehicle-delivery (should be filtered)
            3. **Parse JSON**: Extract orderid and time (ETA)
            4. **Lookup Order**: Find order in pending_deliveries by orderid
            5. **Update Stock**: Add delivered quantity to inventory
            6. **Remove Pending**: Delete order from pending_deliveries
            7. **Record Statistics**: Save delivery data to CSV
            8. **Log Delivery**: Print confirmation and current stock
            9. **Repeat**: Return to step 1 (cyclic behaviour)
        
        Stock Update Logic:
            ```python
            if product in stock:
                stock[product] += quantity  # Increment existing
            else:
                stock[product] = quantity   # Create new entry
            ```
        
        Statistics Recorded:
            - order_id: Unique identifier
            - store_jid: This store's identifier
            - vehicle_jid: Delivering vehicle identifier
            - origin_warehouse: Warehouse that fulfilled order
            - product: Product name
            - quantity: Amount delivered
            - ETA: Estimated time of arrival
            - time_to_delivery: Ticks from confirmation to delivery
            - current_tick: Current simulation time
            - final_state: "delivered" (success indicator)
        
        Error Handling:
            - **Wrong Performative**: Prints ERROR and returns early
            - **JSON Parse Failure**: Catches JSONDecodeError, prints ERROR
            - **Missing Order ID**: Catches KeyError, prints ERROR
            - Graceful degradation: Does not crash agent on malformed messages
        
        Example Execution:
            ```
            Message Received:
                {
                    "orderid": 1001000000,
                    "time": 120
                }
            Processing:
                - Find Order: product="electronics", quantity=50
                - Update Stock: electronics: 200 -> 250
                - Remove: pending_deliveries[1001000000] deleted
                - Record Stats: CSV entry with all details
                - Print: "Vehicle vehicle1@localhost delivered 50 units of electronics"
                - Print: Current stock display
            ```
        
        Side Effects:
            - Modifies agent.stock (inventory increase)
            - Removes order from agent.pending_deliveries
            - Writes statistics to CSV file
            - Prints delivery confirmation and stock status
        
        Returns:
            Never returns (cyclic behaviour runs until agent stops).
        
        Note:
            This is the ONLY place where stock is updated. Confirmations do NOT update
            stock - only physical delivery does. This accurately models real-world
            inventory management where confirmation ≠ possession.
        """
        async def run(self):
            """
            Execute one cycle of vehicle delivery message processing.
            
            This method receives one delivery notification, updates inventory, records
            statistics, and prepares for the next delivery message.
            
            Workflow:
                1. **Receive**: Wait up to 20 seconds for message
                2. **Validation**: Check performative is vehicle-delivery
                3. **Parsing**: Deserialize JSON and extract orderid, time
                4. **Order Lookup**: Find order in pending_deliveries
                5. **Stock Update**: Add quantity to inventory (create or increment)
                6. **Cleanup**: Remove order from pending_deliveries
                7. **Statistics**: Record delivery details to CSV
                8. **Logging**: Print delivery confirmation and stock display
            
            Error Handling:
                Three validation layers:
                1. Template filter (should only receive vehicle-delivery)
                2. Performative check (safety validation)
                3. Try-except for JSON parsing and order lookup
            
            Stock Update Details:
                - Retrieves product and quantity from pending order
                - If product exists: stock[product] += quantity
                - If product new: stock[product] = quantity
                - Thread-safe (single-threaded SPADE execution)
            
            Statistics Recording:
                Calls get_stats() with:
                - order: Order object with all details
                - eta: Estimated time from message
                - state: "delivered" (success indicator)
                - vehicle: Vehicle JID from message sender
            
            Side Effects:
                - Increments stock for delivered product
                - Removes order from pending_deliveries dict
                - Appends row to store_stats.csv
                - Prints to console (always visible, not verbose-only)
            
            Returns:
                None. Continues to next cycle after processing one delivery.
            
            Example:
                ```
                Input: vehicle-delivery from vehicle1
                    Body: {"orderid": 1001000000, "time": 120}
                Pending Order: Order(product="electronics", quantity=50, ...)
                Processing:
                    - Stock before: {"electronics": 200, "food": 100}
                    - Update: electronics += 50
                    - Stock after: {"electronics": 250, "food": 100}
                    - Remove from pending_deliveries
                    - Write CSV row
                Output:
                    Print: "Vehicle vehicle1@localhost delivered 50 units of electronics"
                    Print: "Current stock: electronics: 250 units, food: 100 units"
                ```
            """
            agent : Store = self.agent
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
                    eta = data["time"]          
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"{agent.jid}> ERROR: Failed to parse vehicle message: {e}")
                    return

                # Vehicle is delivering supplies from supplier
                product = order.product
                quantity = order.quantity
                
                if product in agent.stock:
                    agent.stock[product] += quantity
                else:
                    agent.stock[product] = quantity
                del agent.pending_deliveries[order.orderid]
                
                # Save order stats
                agent.get_stats(order, eta,"delivered", msg.sender)
                
                print(f"{agent.jid}> Vehicle {msg.sender} delivered {quantity} units of {product}")
                agent.print_stock()    

    class HighDemand(PeriodicBehaviour):
        """
        Periodic behaviour that simulates high demand by generating random orders.
        
        This behaviour periodically creates random purchase requests for products to
        simulate high demand scenarios in the store. It helps test the store's ability
        to handle multiple concurrent orders and manage inventory under stress.
        
        Attributes:
            Inherited from PeriodicBehaviour:
                - period (float): Time between order generations (default: 10 seconds)
                - Executes continuously while agent is running
        """
        def __init__(self,
                     period=config.STORE_HIGH_DEMAND_FREQUENCY,
                     start_at=datetime.now() + timedelta(seconds=config.STORE_HIGH_DEMAND_FREQUENCY / 2)):
            super().__init__(period=period, start_at=start_at)
        
        async def run(self):
            agent : Store = self.agent
            prev_high_demand = agent.high_demand
            
            # Reset to normal demand
            agent.high_demand = False
            agent.buy_prob = config.STORE_BUY_PROBABILITY
            
            # Check if we should activate high demand
            roll = random.randint(1,100)
            if roll > config.STORE_HIGH_DEMAND_PROBABILITY:
                if agent.verbose: print(f"{agent.jid}> Decided to not activate High Demand mode (roll={roll})")
                return
            else: high_demand = True
            
            if prev_high_demand: prev_frequency = config.STORE_HIGH_DEMAND_FREQUENCY
            else: prev_frequency = config.STORE_BUY_FREQUENCY
            
            # Set new frequency and buy probability
            if agent.high_demand:
                current_frequency = config.STORE_HIGH_DEMAND_FREQUENCY
                agent.buy_prob = config.STORE_HIGH_DEMAND_BUY_PROBABILITY
            else:
                current_frequency = config.STORE_BUY_FREQUENCY
                agent.buy_prob = config.STORE_BUY_PROBABILITY
            
            # If state changed, update buy behaviour
            if prev_high_demand != high_demand:
                # Kill previous buy behaviour
                buy_behav = agent.BuyProduct(period=prev_frequency)
                agent.remove_behaviour(buy_behav)
                await buy_behav.kill()
                
                if agent.verbose and high_demand:
                        print(f"{agent.jid}> High Demand mode ACTIVATED")
                elif agent.verbose and not high_demand:
                        print(f"{agent.jid}> High Demand mode DEACTIVATED")
                
                # Start new buy behaviour
                buy_behav = agent.BuyProduct(period=current_frequency)
                agent.add_behaviour(buy_behav)
            else: pass

    # ------------------------------------------
    #           AUXILARY FUNCTIONS
    # ------------------------------------------
    
    def calculate_warehouse_score(self, accept_msg : Message) -> float:
        """
        Calculate the score for a warehouse proposal based on delivery time.
        
        This method implements the proposal evaluation logic for the FIPA Contract Net
        Protocol, scoring each warehouse that submitted a proposal (warehouse-accept).
        The score is based on the estimated delivery time using Dijkstra's shortest path
        algorithm on the world graph.
        
        Scoring Algorithm:
            - Uses Dijkstra pathfinding: warehouse_node -> store_node
            - Returns: (path, fuel_cost, delivery_time)
            - Score = delivery_time (lower is better)
            - Optimization goal: Minimize delivery time
        
        FIPA Contract Net Protocol Context:
            - Phase: Proposal Evaluation
            - Purpose: Compare multiple proposals objectively
            - Decision Criteria: Distance-based (delivery time)
            - Result: Enables selection of optimal warehouse
        
        Args:
            accept_msg (Message): The warehouse-accept message from a warehouse.
                Contains metadata with node_id of the warehouse's location.
        
        Returns:
            float: Delivery time score. Lower values indicate better proposals
                (shorter delivery time).
        
        Scoring Details:
            - Extracts warehouse node_id from message metadata
            - Calls Dijkstra: map.djikstra(warehouse_id, store_id)
            - Returns time component (ignores path and fuel for scoring)
            - Units: Simulation ticks (time units in the simulation)
        
        Example:
            ```python
            # Warehouse at node 10, Store at node 5
            msg = warehouse_accept_message  # node_id = 10
            score = store.calculate_warehouse_score(msg)
            # Dijkstra returns: ([10, 8, 5], 12.5, 120)
            # score = 120 (delivery time)
            ```
        
        Note:
            This method is called by CollectWarehouseResponses during proposal
            evaluation. All warehouses that sent warehouse-accept are scored,
            and the one with the lowest score (minimum time) is selected.
        
        Alternative Scoring Strategies:
            The algorithm could be extended to consider:
            - Weighted combination: time * w1 + fuel * w2
            - Multi-criteria: time, fuel, warehouse reputation
            - Dynamic weights: Based on urgency or fuel costs
        """
        
        warehouse_id = int(accept_msg.get_metadata("node_id"))
        path, fuel, time = self.map.djikstra(warehouse_id, self.node_id)
        
        return time
    
    def dict_to_order(self, data : dict) -> Order:
        """
        Convert a dictionary representation to an Order object.
        
        This helper method deserializes order data from dictionary format into
        an Order object instance, setting all required fields and optional location
        information if present.
        
        Args:
            data (dict): Dictionary containing order information with keys:
                - product (str): Product name
                - quantity (int): Quantity ordered
                - orderid (int): Unique order identifier
                - sender (str): Sender's JID
                - receiver (str): Receiver's JID
                - sender_location (int, optional): Sender's graph node ID
                - receiver_location (int, optional): Receiver's graph node ID
        
        Returns:
            Order: Fully populated Order object with all fields from dictionary.
        
        Example:
            ```python
            data = {
                "product": "electronics",
                "quantity": 50,
                "orderid": 1001000000,
                "sender": "warehouse1@localhost",
                "receiver": "store1@localhost",
                "sender_location": 10,
                "receiver_location": 5
            }
            order = store.dict_to_order(data)
            # order.product == "electronics", order.quantity == 50, etc.
            ```
        
        Note:
            Uses dict.get() for optional location fields to handle cases where
            location information is not provided (returns None by default).
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
    
    def message_to_order(self, msg : Message) -> Order:
        """
        Convert a warehouse-accept message to an Order object.
        
        This helper method transforms a SPADE message received during the FIPA Contract
        Net Protocol into a structured Order object suitable for tracking and processing.
        It extracts all relevant information from the message metadata and body.
        
        The method is used after a warehouse is selected (during SendStoreConfirmation)
        to create an Order object for tracking in pending_deliveries.
        
        Args:
            msg (Message): The warehouse-accept message containing order details.
                Metadata includes: request_id, node_id (warehouse location)
                Body format: "{quantity} {product}"
        
        Returns:
            Order: Fully populated Order object with:
                - product: Extracted from message body
                - quantity: Extracted from message body
                - orderid: From request_id metadata
                - sender: Warehouse JID (message sender)
                - receiver: Store JID (this store)
                - sender_location: Warehouse node ID (from metadata)
                - receiver_location: Store node ID (this store's location)
        
        Message Parsing:
            Body:
                - Format: "{quantity} {product}"
                - Split on space: parts[0] = quantity, parts[1] = product
                - Example: "50 electronics" -> quantity=50, product="electronics"
            
            Metadata:
                - request_id: Used as orderid for correlation
                - node_id: Warehouse's graph location
                - sender: Warehouse's JID
        
        Location Assignment:
            - sender_location: Warehouse node (from message node_id)
            - receiver_location: Store node (this store's node_id)
            - Note: Reversed compared to dict_to_order perspective
        
        Example:
            ```python
            # Warehouse-accept message
            msg.body = "50 electronics"
            msg.sender = "warehouse2@localhost"
            msg.metadata["request_id"] = "1001000000"
            msg.metadata["node_id"] = "10"
            
            order = store.message_to_order(msg)
            # order.product = "electronics"
            # order.quantity = 50
            # order.orderid = 1001000000
            # order.sender = "warehouse2@localhost"
            # order.receiver = "store1@localhost"
            # order.sender_location = 10 (warehouse)
            # order.receiver_location = 5 (store)
            ```
        
        Note:
            The Order object is used for:
            - Tracking in pending_deliveries dict (awaiting vehicle delivery)
            - Recording timing information for statistics
            - Providing vehicle with delivery instructions
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
    
    def set_buy_metadata(self, msg : Message) -> None:
        """
        Set standard metadata for purchase request messages (FIPA CFP).
        
        This helper method populates common metadata fields for store-buy messages,
        ensuring consistency across all purchase requests. It sets the performative
        and store identifier, with the caller responsible for setting the request_id.
        
        FIPA Protocol:
            This prepares the message for the Call for Proposals (CFP) phase of the
            FIPA Contract Net Protocol.
        
        Args:
            msg (Message): The message to populate with metadata. Modified in-place.
        
        Side Effects:
            Modifies msg metadata:
                - performative: Set to "store-buy" (FIPA CFP)
                - store_id: Set to this store's JID
        
        Note:
            The request_id must be set separately by the caller to ensure unique
            identification for each purchase request. This separation allows for
            proper ID encoding and avoids duplication.
        
        Example:
            ```python
            msg = Message(to="warehouse1@localhost")
            store.set_buy_metadata(msg)
            msg.set_metadata("request_id", "1001000000")  # Caller sets this
            msg.body = "50 electronics"
            # Message ready to send as FIPA CFP
            ```
        """
        msg.set_metadata("performative", "store-buy")
        msg.set_metadata("store_id", str(self.jid))
        # NOTE: request_id should be set separately by the caller
    
    def update_graph(self, traffic_data) -> None:
        """
        Apply dynamic traffic updates to the world graph.
        
        This method processes transit messages from the world agent, updating edge
        weights in the graph to reflect current traffic conditions. These updates
        affect pathfinding calculations used in warehouse selection, making the
        system responsive to real-time network conditions.
        
        Traffic Data Format:
            ```json
            {
                "edges": [
                    {
                        "node1": 5,
                        "node2": 10,
                        "weight": 200,
                        "fuel_consumption": 15.0
                    },
                    ...
                ]
            }
            ```
        
        Args:
            traffic_data (dict): Dictionary containing edge updates with key "edges"
                mapping to a list of edge information dictionaries.
        
        Edge Processing:
            For each edge in traffic_data["edges"]:
                - Extract: node1, node2, new_weight
                - Lookup: Find edge in graph using get_edge(node1, node2)
                - Update: Set edge.weight = new_weight if edge exists
                - Skip: If edge not found (graceful handling)
        
        Side Effects:
            - Modifies edge weights in self.map (world graph)
            - Affects future Dijkstra calculations
            - Changes warehouse scoring results
            - Does NOT modify fuel_consumption (current implementation)
        
        Example:
            ```python
            traffic_data = {
                "edges": [
                    {"node1": 5, "node2": 10, "weight": 200, "fuel_consumption": 15.0},
                    {"node1": 10, "node2": 15, "weight": 150, "fuel_consumption": 12.0}
                ]
            }
            store.update_graph(traffic_data)
            # Edge (5, 10) weight updated to 200
            # Edge (10, 15) weight updated to 150
            # Future pathfinding uses new weights
            ```
        
        Note:
            Currently only updates weight, not fuel_consumption. Future enhancement
            could update fuel_consumption as well for more realistic simulation:
            ```python
            if edge:
                edge.weight = new_weight
                edge.fuel_consumption = new_fuel  # Not currently implemented
            ```
        
        Impact on System:
            - Dynamic responsiveness to traffic conditions
            - Warehouses with congested routes become less attractive
            - Enables simulation of rush hours, accidents, road closures
            - Realistic supply chain behavior under varying conditions
        """
        for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge : Edge = self.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight
    
    def get_stats(self, order : Order, eta, state, vehicle) -> None:
        """
        Record order statistics to CSV file for post-simulation analysis.
        
        This method captures comprehensive metrics about each order, including timing,
        participants, and outcome. Statistics are appended to a CSV file for later
        analysis of supply chain performance, bottlenecks, and optimization opportunities.
        
        Args:
            order (Order): The order object containing product, quantity, and IDs.
            eta (int): Estimated time of arrival or delivery time in simulation ticks.
            state (str): Final state of the order. Possible values:
                - "delivered": Successfully completed
                - "pending": Awaiting delivery
                - "failed": Order failed (not currently used)
            vehicle (str): JID of the vehicle that handled the delivery.
        
        Statistics Captured:
            - order_id: Unique request identifier
            - store_jid: This store's identifier (without @domain)
            - vehicle_jid: Delivering vehicle's identifier (without @domain)
            - origin_warehouse: Warehouse that fulfilled order (without @domain)
            - product: Product name
            - quantity: Amount ordered/delivered
            - ETA: Estimated time of arrival from vehicle
            - time_to_delivery: Total ticks from confirmation to delivery
            - current_tick: Simulation time when stats recorded
            - final_state: Outcome indicator (delivered/pending/failed)
        
        CSV File Format:
            - Location: stats/store_stats.csv
            - Encoding: UTF-8
            - Headers: Written automatically on first write
            - Mode: Append (preserves previous records)
        
        Time-to-Delivery Calculation:
            ```python
            time_to_delivery = current_tick - order_timings[orderid]
            # order_timings[orderid] set during SendStoreConfirmation
            # Measures: Confirmation -> Delivery complete
            ```
        
        Side Effects:
            - Creates stats/ directory if it doesn't exist
            - Creates or appends to store_stats.csv
            - Prints confirmation if verbose mode enabled
            - Prints error if file operation fails
        
        Error Handling:
            - Wraps file operations in try-except
            - Catches all exceptions (broad handling for robustness)
            - Prints error message with exception details
            - Does not crash agent on statistics failure
        
        Example CSV Output:
            ```csv
            order_id,store_jid,vehicle_jid,origin_warehouse,product,quantity,ETA,time_to_delivery,current_tick,final_state
            1001000000,store1,vehicle1,warehouse2,electronics,50,120,125,345,delivered
            1001000001,store1,vehicle2,warehouse1,food,30,80,85,430,delivered
            ```
        
        Performance Metrics Enabled:
            - Average delivery time per product
            - Warehouse performance comparison
            - Vehicle efficiency analysis
            - Bottleneck identification
            - Demand pattern analysis
        
        Example Usage:
            ```python
            # Called from ReceiveVehicleArrival after delivery
            order = pending_deliveries[orderid]
            eta = 120  # From vehicle message
            store.get_stats(order, eta, "delivered", msg.sender)
            # CSV row appended with all order metrics
            ```
        
        Note:
            Statistics are append-only. For new simulation runs, manually delete or
            rename the CSV file to avoid mixing data from different experiments.
        """
        agent : Store = self
        
        order_stats = {
            "order_id": order.orderid,
            "store_jid": str(self.jid).split('@')[0],
            "vehicle_jid" : str(vehicle).split('@')[0],
            "origin_warehouse": order.sender.split('@')[0],
            "product": order.product,
            "quantity": order.quantity,
            "ETA": eta if eta else None,
            "time_to_delivery": self.current_tick - self.order_timings[order.orderid],
            "current_tick": self.current_tick,
            "final_state": state  # pending, delivered, failed
        }
        
        # Build full file path
        full_path = os.path.join(self.stats_path, self.stats_filename)
        
        # Check if file exists to determine if we need to write headers
        file_exists = os.path.isfile(full_path)
        
        # Write to CSV
        try:
            # Create directory if it doesn't exist
            os.makedirs(self.stats_path, exist_ok=True)
            
            if not file_exists: open_mode = 'w'
            else: open_mode = 'a'
            
            with open(full_path, mode=open_mode, newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=order_stats.keys())
                
                # Write header only if file is new
                if not file_exists:
                    writer.writeheader()
                
                writer.writerow(order_stats)
            
            if self.verbose:
                print(f"{self.jid}> Stats saved to {full_path} for order {order.orderid}")
        except Exception as e:
            print(f"{self.jid}> ERROR saving stats: {e}")        
    
    def print_stock(self) -> None:
        """
        Print the current stock inventory to console.
        
        This helper method provides a human-readable display of the store's current
        inventory, showing all products and their quantities. Used after deliveries
        to provide visibility into stock levels.
        
        Output Format:
            If stock is empty:
                "{jid}> Stock is empty"
            
            If stock has items:
                "{jid}> Current stock:"
                "  - product1: quantity1 units"
                "  - product2: quantity2 units"
                ...
        
        Side Effects:
            - Prints to standard output (console)
            - Always visible (not affected by verbose setting)
        
        Example Output:
            ```
            store1@localhost> Current stock:
              - electronics: 250 units
              - food: 100 units
              - clothing: 75 units
            ```
        
        Note:
            This method is called after every successful delivery to provide
            immediate feedback about inventory changes.
        """
        if not self.stock:
            print(f"{self.jid}> Stock is empty")
        else:
            print(f"{self.jid}> Current stock:")
            for product, quantity in self.stock.items():
                print(f"  - {product}: {quantity} units")
    # ------------------------------------------
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False, contact_list = [], verbose = False):
        """
        Initialize the Store agent with configuration and state.
        
        This constructor sets up the store agent with all necessary parameters for
        operation, including network configuration, graph reference, ID encoding,
        and statistics tracking. It prepares the agent for FIPA Contract Net Protocol
        negotiations and supply chain operations.
        
        Args:
            jid (str): Jabber ID for the store agent (e.g., "store1@localhost").
                Must be unique within the XMPP server.
            password (str): Authentication password for XMPP server connection.
            map (Graph): Reference to the world graph for pathfinding and distance
                calculations. Shared across all agents in the simulation.
            node_id (int): Graph node ID representing the store's physical location.
                Used in pathfinding and warehouse scoring.
            port (int, optional): XMPP server port. Defaults to 5222 (standard XMPP).
            verify_security (bool, optional): Whether to verify SSL/TLS certificates.
                Defaults to False for local development. Set True for production.
            contact_list (list[str], optional): List of warehouse JIDs to subscribe to.
                Store will send purchase requests to these warehouses.
                Defaults to empty list.
            verbose (bool, optional): Enable detailed debug logging.
                True: Print all debug information
                False: Print only essential messages
                Defaults to False.
        
        ID Encoding System:
            Generates unique request IDs using hierarchical encoding:
            - Formula: `(agent_type * 100_000_000) + (instance_id * 1_000_000) + counter`
            - Store type code: 1
            - Instance ID: Extracted from JID (e.g., "store1" -> 1, "store42" -> 42)
            - Example: store1's first request = 1_001_000_000
            - Example: store1's second request = 1_001_000_001
            - Ensures global uniqueness across all agents and requests
        
        Configuration Loading:
            Imports from config module:
            - PRODUCTS: List of available products for purchase
            - STORE_BUY_PROBABILITY: Probability (0-1) of purchase attempt per period
            - STORE_MAX_BUY_QUANTITY: Maximum quantity per purchase order
        
        State Initialization:
            - pending_deliveries: Empty dict for tracking orders awaiting delivery
            - order_timings: Empty dict for recording confirmation timestamps
            - current_tick: 0 (synchronized by world agent during runtime)
            - stock: Initialized in setup() as empty dict
            - failed_requests: Initialized in setup() as empty queue
            - request_counter: Initialized in setup() as 0
        
        Statistics Configuration:
            - stats_path: "stats/" directory (created automatically if needed)
            - stats_filename: "store_stats.csv" (append mode)
        
        Example:
            ```python
            from world.graph import Graph
            
            map_graph = Graph()
            # ... add nodes and edges to graph ...
            
            store = Store(
                jid="store1@localhost",
                password="secure_password",
                map=map_graph,
                node_id=5,
                port=5222,
                verify_security=False,
                contact_list=["warehouse1@localhost", "warehouse2@localhost"],
                verbose=True
            )
            
            # store.id_base = 1_001_000_000
            # Ready to start and begin purchasing
            await store.start()
            ```
        
        Note:
            The agent is not fully operational until setup() is called (automatically
            by SPADE when start() is invoked). The setup() method initializes
            behaviours and subscribes to contacts.
        """
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
        self.contact_list = contact_list
        self.verbose = verbose
        
        # Extract instance number from JID for ID encoding (e.g., "store1@localhost" -> 1)
        jid_name = str(jid).split('@')[0]
        instance_id = int(''.join(filter(str.isdigit, jid_name)))
        
        # Calculate ID base: Store type code = 1
        self.id_base = (1 * 100_000_000) + (instance_id * 1_000_000)
        
        self.pending_deliveries : dict[str, Order] = {}  # key: request_id, value: Order object
        self.order_timings : dict[str, int] =  {}  # key: request_id, value: ticks at confirmation
        self.current_tick : int = 0
        self.stats_path = os.path.join(os.getcwd(), "stats")
        self.stats_filename = "store_stats.csv"
        
        # Constants from config
        self.product_list = config.PRODUCTS
        self.buy_prob = config.STORE_BUY_PROBABILITY
        self.max_buy_quantity = config.STORE_MAX_BUY_QUANTITY

        self.high_demand = False
        
    async def setup(self):
        """
        Setup method called automatically by SPADE when agent starts.
        
        This method initializes the agent's operational state and registers all
        behaviours with appropriate message templates. It completes the agent
        initialization process started in __init__, preparing the store for
        active participation in the supply chain simulation.
        
        Initialization Steps:
            1. Configure presence management (auto-approve subscriptions)
            2. Subscribe to all warehouses in contact list
            3. Initialize runtime state variables (stock, counters, queues)
            4. Register BuyProduct behaviour (periodic purchasing)
            5. Register ReceiveTimeDelta behaviour (time synchronization)
            6. Register RetryPreviousBuy behaviour (failed request retry)
            7. Register ReceiveVehicleArrival behaviour (delivery reception)
        
        Presence Configuration:
            - presence.approve_all = True: Auto-accept all subscription requests
            - Subscribes to each warehouse in contact_list
            - Enables bidirectional communication with warehouses
        
        State Initialization:
            - stock: Empty dict (populated by deliveries)
            - current_buy_request: None (set during purchase attempts)
            - failed_requests: Empty FIFO queue (populated by failed negotiations)
            - request_counter: 0 (incremented for each purchase request)
        
        Behaviour Registration:
        
            1. **BuyProduct** (PeriodicBehaviour):
                - No template filter (self-triggered by period)
                - Period: config.STORE_BUY_FREQUENCY seconds
                - Purpose: Initiate FIPA Contract Net Protocol for purchases
            
            2. **ReceiveTimeDelta** (CyclicBehaviour):
                - Template: performative="inform"
                - Purpose: Receive time updates and traffic data from world agent
                - Continuous operation
            
            3. **RetryPreviousBuy** (PeriodicBehaviour):
                - No template filter (self-triggered)
                - Period: 5 seconds
                - Purpose: Retry failed purchase requests
            
            4. **ReceiveVehicleArrival** (CyclicBehaviour):
                - Template: performative="vehicle-delivery"
                - Purpose: Receive delivery notifications and update stock
                - Continuous operation
        
        Template Filtering:
            Templates ensure behaviours only receive relevant messages:
            - ReceiveTimeDelta: Only "inform" messages (from world agent)
            - ReceiveVehicleArrival: Only "vehicle-delivery" messages (from vehicles)
            - BuyProduct/RetryPreviousBuy: No template (time-triggered, not message-triggered)
        
        Side Effects:
            - Sends presence subscription requests to all warehouses
            - Adds four behaviours to agent's behaviour queue
            - Prints subscription confirmations if verbose mode enabled
        
        Returns:
            None. Completes when all behaviours are registered and agent is operational.
        
        Example Flow:
            ```
            Agent Start:
                1. SPADE calls setup()
                2. Subscribe to warehouse1, warehouse2
                3. Initialize stock = {}
                4. Register BuyProduct (will start after 5s)
                5. Register ReceiveTimeDelta (active immediately)
                6. Register RetryPreviousBuy (checks every 5s)
                7. Register ReceiveVehicleArrival (active immediately)
                8. Agent ready for operation
            ```
        
        Note:
            This method is asynchronous and is automatically called by SPADE's
            agent lifecycle management. Do not call this method manually.
        """
        self.presence.approve_all = True
        for contact in self.contact_list:
            self.presence.subscribe(contact)
            if self.verbose:
                print(f"{self.jid}> Sent subscription request to {contact}")
        self.stock = {}
        self.current_buy_request : Message = None
        self.failed_requests : queue.Queue = queue.Queue()
        self.request_counter = 0

        # BuyProduct behaviour initialization
        buy_behav = self.BuyProduct()
        self.add_behaviour(buy_behav)
        
        # HighDemand behaviour initialization
        highd_behav = self.HighDemand()
        self.add_behaviour(highd_behav)

        # Time delta behaviour
        time_behav = self.ReceiveTimeDelta()
        time_template : Template = Template()
        time_template.set_metadata("performative", "inform")
        self.add_behaviour(time_behav, time_template)
        
        # Buy retrying is not bound by ticks
        retry_behav = self.RetryPreviousBuy(period=5)
        self.add_behaviour(retry_behav)
        
        # Vehicle arrival behaviour
        vehicle_behav = self.ReceiveVehicleArrival()
        delivery_temp = Template()
        delivery_temp.set_metadata("performative", "vehicle-delivery")
        self.add_behaviour(vehicle_behav, delivery_temp)

