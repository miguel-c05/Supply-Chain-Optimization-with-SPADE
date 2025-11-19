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
    Class for the Store Agent.
    
    Currently able to:
        -
        
    Usage instructions:
        - To buy x units of product Y, call self.BuyProduct(x,Y)
        - Only ONE request must be sent at once, periodically and accoring to a
        predefined probability.
        
    Class variables:
        - self.stock (dict): current inventory
            - keys (str): product
            - values (int): quantity

        - self.request_counter (int): a counter that serves as the requests id
        - self.current_buy_request (Message): holds the current buy request Message
        - self.failed_requests (queue.Queue(Message)): a queue that holds all failed buy request
        Messages. A request is enqueued if ReceiveAcceptance times out.
    """
    
    # ------------------------------------------
    #         WAREHOUSE <-> STORE
    # ------------------------------------------
    
    class BuyProduct(PeriodicBehaviour):

        def __init__(self,
                     quantity : Optional[int] = None,
                     product : Optional[str] = None,
                     period=config.STORE_BUY_FREQUENCY,
                     start_at=datetime.now() + timedelta(seconds=5)):
            
            super().__init__(period=period, start_at=start_at)
            self.quantity = quantity
            self.product = product
        
        async def run(self):
            agent : Store = self.agent
            
            roll = random.randint(1,100)
            # Decide whether to buy this turn based on probability
            if roll > agent.buy_prob * 100:
                if agent.verbose:
                    print(f"{agent.jid}> Decided NOT to buy this turn (roll={roll} > buy_prob={agent.buy_prob})")
                return
            else: pass
            
            if self.quantity is None: 
                self.quantity = random.randint(1, agent.max_buy_quantity)
            if self.product is None:
                self.product = random.choice(agent.product_list)
                
            print(f"{agent.jid}> Preparing to buy {self.quantity} units of {self.product}")
            
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
                msg.body = f"{self.quantity} {self.product}"
                
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
                    self.quantity,
                    self.product
                )
                agent.add_behaviour(behav)
                
                await behav.join()

    class CollectWarehouseResponses(OneShotBehaviour):
        def __init__(self, msg : Message, request_id : int, num_warehouses : int, quantity : int, product : str):
            super().__init__()
            self.request_id = request_id
            self.buy_msg = msg.body
            self.num_warehouses = num_warehouses
            self.quantity = quantity
            self.product = product
            self.acceptances = []  # List of (warehouse_jid, msg)
            self.rejections = []   # List of (warehouse_jid, msg, reason)
            
        async def run(self):
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
        def __init__(self, request_id : int, num_warehouses : int, acceptances : list, rejections : list):
            super().__init__()
            self.request_id = request_id
            self.num_warehouses = num_warehouses
            self.acceptances = acceptances  # Shared list
            self.rejections = rejections    # Shared list
            self.responses_received = 0
            self.timeout = 5  # seconds to wait for all responses
            
        async def run(self):
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
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
            self.msg : Message = msg
            
        
        async def run(self):
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
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
        
        async def run(self):
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
        async def run(self):
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
        async def run(self):
            agent : Store = self.agent
            
            msg : Message = await self.receive(timeout=20)
            
            if msg != None:
                data = json.loads(msg.body)
                
                type : str = data["type"]
                delta : int = data["time"]
                agent.current_tick += delta
                
                if type.lower() != "arrival":
                    map_updates = data["data"]                 
                    # TODO -- implement update graph  
                    agent.update_graph(map_updates)         
    
    class ReceiveVehicleArrival(CyclicBehaviour):
        """
        Behaviour to receive arrival notifications from vehicles.
        Accepts ONLY: vehicle-pickup, vehicle-delivery
        """
        async def run(self):
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
                agent.get_stats(order, eta,"delivered")
                
                print(f"{agent.jid}> Vehicle {msg.sender} delivered {quantity} units of {product}")
                agent.print_stock()    

    # ------------------------------------------
    #           AUXILARY FUNCTIONS
    # ------------------------------------------
    
    def calculate_warehouse_score(self, accept_msg : Message) -> float:
        """
        Calculate the score for a warehouse based its distance to the store.
        Lower score is better.
        """
        
        warehouse_id = int(accept_msg.get_metadata("node_id"))
        path, fuel, time = self.map.djikstra(warehouse_id, self.node_id)
        
        return time
    
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
    
    def message_to_order(self, msg : Message) -> Order:
        """
        Convert a store-confirm message to an Order object.
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
        msg.set_metadata("performative", "store-buy")
        msg.set_metadata("store_id", str(self.jid))
        # NOTE: request_id should be set separately by the caller
    
    def update_graph(self, traffic_data) -> None:
        for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge : Edge = self.agent.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight
    
    def get_stats(self, order : Order, eta, state) -> None:
        """
        Save stats for the given order to CSV file.
        """
        agent : Store = self
        
        order_stats = {
            "order_id": order.orderid,
            "store_jid": str(self.jid),
            "product": order.product,
            "quantity": order.quantity,
            "time_to_delivery": self.current_tick - self.order_timings[order.orderid],
            "final_state": state,  # pending, delivered, failed
            "origin_warehouse": order.sender,
            "ETA": eta if eta else None,
            "current_tick": self.current_tick
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
        """Print the current stock inventory."""
        if not self.stock:
            print(f"{self.jid}> Stock is empty")
        else:
            print(f"{self.jid}> Current stock:")
            for product, quantity in self.stock.items():
                print(f"  - {product}: {quantity} units")
    # ------------------------------------------
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False, contact_list = [], verbose = False):
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
        
    async def setup(self):
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

