import asyncio
import random
import json
import queue
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.template import Template
from world.graph import Graph
from veiculos.algoritmo_tarefas import Order
import config

class Warehouse(Agent):
    
    """
    Class for the Warehouse Agent.
    
    Currently able to:
        - Generate random starting stock (1 to 20 over products A, B and C)
        - Permanently listen for buy requests (NOW MULTIPLE AT A TIME)
        - Send "warehouse-accept" messages
        - Receive "store-confirm" messages
        - Update stock
        - Put bought items aside (in self.pending_orders) while they are not transported
        
    Usage instructions:
        - For Vehicles:
            - All vehicles must be subscribed in all warehouses and vice-versa
            - To get all all orders from a store_agent, get
            warehouse_agent.pending_orders[store_agent.jid]
    
    What is missing (TODO):
        - Communicate with Vehicles
        
    Class variables:
        - self.stock (dict()): current AVAILABLE stock
            - keys: products
            - values: quantity
        
        - self.locked_stock (dict()): stock that is being used for some request process
            - keys: products
            - values: quantity

        - self.pending_orders (dict()): Dictionary with order_id as key and Order object as value.
        Use this to retrieve confirmed orders by their ID (useful for Vehicles).
            - keys: order_id (int)
            - values: Order object
    """
    
    # ------------------------------------------
    #           WAREHOUSE <-> STORE
    # ------------------------------------------
    
    class ReceiveBuyRequest(CyclicBehaviour):
        async def run(self):
            agent : Warehouse = self.agent
        
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
                print(f"{agent.jid}> Got a request from {msg.sender}: id={request_id} quant={quant} product={product}")
                
                if (product in agent.stock.keys()) and agent.stock[product] >= quant:
                    accept_behav = agent.AcceptBuyRequest(msg)
                    print(f"{self.agent.jid}> Locking {quant} of {product}...")
                    agent.stock[product] -= quant
                    
                    if product in agent.locked_stock:
                        agent.locked_stock[product] += quant
                    else: agent.locked_stock[product] = quant

                    print(f"Items locked at {agent.jid}.")
                    agent.print_stock()
                    
                    agent.add_behaviour(accept_behav)
                else:
                    # Reject the request - insufficient stock
                    reject_behav = agent.RejectBuyRequest(msg, reason="insufficient_stock")
                    agent.add_behaviour(reject_behav)
                    print(f"{agent.jid}> Could not satisfy request. Rejection sent.")
            else:
                print(f"{agent.jid}> Did not get any buy requests in 20 seconds.")

    class AcceptBuyRequest(OneShotBehaviour):
        def __init__(self, msg : Message):
            super().__init__()
            self.request_id = int(msg.get_metadata("request_id"))
            request = msg.body.split(" ")
            self.quant = int(request[0])
            self.product = request[1]
            self.sender = msg.sender
        
        async def run(self):
            agent : Warehouse = self.agent
            
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
            
            # Wait for either confirmation or denial
            confirm_deny_behav = agent.ReceiveConfirmationOrDenial(msg, self.sender)
            
            # Template that matches BOTH store-confirm AND store-deny
            template = Template()
            template.set_metadata("warehouse_id", str(agent.jid))
            template.set_metadata("store_id", str(self.sender))
            template.set_metadata("request_id", str(self.request_id))
            
            agent.add_behaviour(confirm_deny_behav, template)
            print(f"{agent.jid}> AcceptBuyRequest finished, now waiting for confirmation or denial...")
            
            # Aguardar a confirmação ser recebida antes de terminar
            # await confirm_deny_behav.join()
    
    class RejectBuyRequest(OneShotBehaviour):
        def __init__(self, msg : Message, reason : str = "insufficient_stock"):
            super().__init__()
            self.request_id = int(msg.get_metadata("request_id"))
            request = msg.body.split(" ")
            self.quant = int(request[0])
            self.product = request[1]
            self.sender = msg.sender
            self.reason = reason
        
        async def run(self):
            agent : Warehouse = self.agent
            
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
            print(f"{agent.jid}> RejectBuyRequest sent to {self.sender}")
            
    
    class ReceiveConfirmationOrDenial(OneShotBehaviour):
        def __init__(self, accept_msg : Message, sender_jid):
            super().__init__()
            self.accepted_id = int(accept_msg.get_metadata("request_id"))
            bod = accept_msg.body.split(" ")
            self.accepted_quantity = int(bod[0])
            self.accepted_product = bod[1]
            self.sender_jid = str(sender_jid)
        
        async def run(self):
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
                    
                    # Add to pending_orders dict with order_id as key
                    self.agent.pending_orders[order.orderid] = order
                            
                        
                    print(f"{self.agent.jid}> Confirmation received! Stock updated: {product} -= {quantity}")
                    print(f"{self.agent.jid}> Order {order.orderid} added to pending orders")
                    print(f"{self.agent.jid}> ReceiveConfirmationOrDenial finished, stock updated.")

                    self.agent.print_stock()
                    
                elif performative == "store-deny":
                    # Store denied (chose another warehouse) - unlock the stock
                    print(f"{self.agent.jid}> Denial received! Store chose another warehouse.")
                    print(f"{self.agent.jid}> Unlocking stock: {product} += {quantity}")
                    
                    self.agent.locked_stock[product] -= quantity
                    self.agent.stock[product] += quantity
                    
                    self.agent.print_stock()
                    
            else:
                print(f"{self.agent.jid}> Timeout: No confirmation or denial received in 10 seconds. Unlocking stock...")
                self.agent.locked_stock[self.accepted_product] -= self.accepted_quantity
                self.agent.stock[self.accepted_product] += self.accepted_quantity
                
                self.agent.print_stock()            
    
    # ------------------------------------------
    #         WAREHOUSE <-> SUPPLIER
    # ------------------------------------------      
    class BuyMaterial(OneShotBehaviour):
        def __init__(self, quantity, product):
            super().__init__()
            self.quantity = quantity
            self.product = product
        
        async def run(self):
            agent : Warehouse = self.agent
            contacts = list(agent.presence.contacts.keys())
            
            # Get request_id before sending
            request_id_for_template = agent.request_counter
            agent.request_counter += 1
            
            msg = None  # Will store the last sent message for current_buy_request
            for contact in contacts:
                msg = Message(to=contact)
                msg.set_metadata("performative", "warehouse-buy")
                msg.set_metadata("warehouse_id", str(agent.jid))
                msg.set_metadata("request_id", str(request_id_for_template))
                msg.set_metadata("node_id", str(agent.node_id))
                msg.body = f"{self.quantity} {self.product}"
                
                print(f"{agent.jid}> Sent request (id={msg.get_metadata('request_id')}):"
                      f"\"{msg.body}\" to {msg.to}")
                
                await self.send(msg)
            
            # Store the last message (or could store all if needed)
            if msg:
                agent.current_buy_request = msg
        
                # Collect responses from all suppliers
                behav = agent.CollectSupplierResponses(
                    msg, 
                    request_id_for_template, 
                    len(contacts),
                    self.quantity,
                    self.product
                )
                agent.add_behaviour(behav)
                
                await behav.join()
    
    class CollectSupplierResponses(OneShotBehaviour):
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
                print(f"{agent.jid}> Received {len(self.acceptances)} acceptance(s) and {len(self.rejections)} rejection(s)")
                
                # Calculate scores for each supplier that accepted
                best_supplier = None
                best_score = float('inf')
                
                for supplier_jid, msg in self.acceptances:
                    score = agent.calculate_supplier_score(msg)
                    print(f"{agent.jid}> Supplier {supplier_jid} score: {score}")
                    
                    if score < best_score:
                        best_score = score
                        best_supplier = (supplier_jid, msg)
                
                if best_supplier:
                    supplier_jid, accept_msg = best_supplier
                    print(f"{agent.jid}> Selected supplier {supplier_jid} with score {best_score}")
                    
                    # Send confirmation to the chosen supplier
                    confirm_behav = agent.SendWarehouseConfirmation(accept_msg)
                    agent.add_behaviour(confirm_behav)
                    await confirm_behav.join()
                    
                    # Send denial to other suppliers that accepted but weren't chosen
                    for other_supplier_jid, other_msg in self.acceptances:
                        if other_supplier_jid != supplier_jid:
                            deny_behav = agent.SendWarehouseDenial(other_msg)
                            agent.add_behaviour(deny_behav)
                            print(f"{agent.jid}> Sent denial to {other_supplier_jid}")
                    
            else:
                print(f"{agent.jid}> No acceptances received. All suppliers rejected or timed out.")
                print(f"{agent.jid}> Request saved in self.failed_requests")
                
                # Add to failed requests
                if hasattr(agent, 'current_buy_request') and agent.current_buy_request:
                    agent.failed_requests.put(agent.current_buy_request)

    class ReceiveAllSupplierResponses(OneShotBehaviour):
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
            
            print(f"{agent.jid}> ReceiveAllSupplierResponses starting - waiting for {self.num_suppliers} responses (request_id={self.request_id})")
            
            import time
            start_time = time.time()
            
            while self.responses_received < self.num_suppliers:
                elapsed = time.time() - start_time
                remaining_timeout = self.timeout - elapsed
                
                if remaining_timeout <= 0:
                    print(f"{agent.jid}> Timeout: Only received {self.responses_received}/{self.num_suppliers} responses")
                    break
                
                print(f"{agent.jid}> Waiting for supplier response... (timeout={remaining_timeout:.1f}s)")
                msg : Message = await self.receive(timeout=remaining_timeout)
                
                if msg:
                    performative = msg.get_metadata("performative")
                    supplier_jid = str(msg.sender)
                    
                    print(f"{agent.jid}> Received message from {supplier_jid} with performative={performative}")
                    
                    if performative == "supplier-accept":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        
                        print(f"{agent.jid}> Received acceptance from {supplier_jid}: {quantity} {product}")
                        self.acceptances.append((supplier_jid, msg))
                        
                    elif performative == "supplier-reject":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        reason = parts[2] if len(parts) > 2 else "unknown"
                        
                        print(f"{agent.jid}> Received rejection from {supplier_jid}: {quantity} {product} (reason: {reason})")
                        self.rejections.append((supplier_jid, msg, reason))
                    else:
                        print(f"{agent.jid}> WARNING: Received unknown performative: {performative}")
                    
                    self.responses_received += 1
                else:
                    # No more messages, timeout
                    print(f"{agent.jid}> No message received in timeout window")
                    break
            
            print(f"{agent.jid}> Finished collecting responses: {len(self.acceptances)} accepts, {len(self.rejections)} rejects")               
    
    class SendWarehouseConfirmation(OneShotBehaviour):
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
            
            print(f"{agent.jid}> Confirmation sent to {self.dest} for request: {msg.body}")
    
    class SendWarehouseDenial(OneShotBehaviour):
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
            
            print(f"{agent.jid}> Denial sent to {self.dest} for request: {msg.body}")
    
    class RetryPreviousBuy(OneShotBehaviour):
        async def run(self):
            agent : Warehouse = self.agent
            
            if not agent.failed_requests.empty():
                request : Message = agent.failed_requests.get()
                request_id = request.get_metadata("request_id")
                contacts = list(agent.presence.contacts.keys())
                
                for contact in contacts:
                    msg : Message = Message(to=contact)
                    agent.set_buy_metadata(msg)
                    msg.set_metadata("request_id", str(request_id))
                    msg.body = request.body

                    print(f"{agent.jid}> Retrying request (id={request_id}):"
                          f"\"{msg.body}\" to {msg.to}")

                    await self.send(msg)

                behav = agent.RecieveSupplierAcceptance(msg)
                template = Template()
                template.set_metadata("performative", "supplier-accept")
                template.set_metadata("warehouse_id", str(agent.jid))
                template.set_metadata("request_id", str(request_id))
                agent.add_behaviour(behav, template)

                await behav.join()
    
    class HandleResupply(PeriodicBehaviour):
        async def run(self):
            agent : Warehouse = self.agent
            
            # Check stock levels
            for product, amount in agent.stock.items():
                if amount < config.WAREHOUSE_RESUPPLY_THRESHOLD:
                    # Need to restock this product
                    restock_amount = config.WAREHOUSE_MAX_PRODUCT_CAPACITY - amount
                    print(f"{agent.jid}> Stock of {product} is low ({amount}). Initiating restock of {restock_amount}.")
                    
                    buy_behav = agent.BuyMaterial(restock_amount, product)
                    agent.add_behaviour(buy_behav)
                    
                    await buy_behav.join()
            
    class AssignVehicle(OneShotBehaviour):
        async def run(self):
            pass # TODO - implement if needed
    
    class ReceiveVehicleArrival(CyclicBehaviour):
        """
        Behaviour to receive arrival notifications from vehicles.
        Accepts ONLY: vehicle-pickup, vehicle-delivery
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
                    order = agent.dict_to_order(data)
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"{agent.jid}> ERROR: Failed to parse vehicle message: {e}")
                    return
                
                # Handle based on performative
                if performative == "vehicle-pickup":
                    # Vehicle is picking up an order to deliver to store
                    if order.orderid in agent.pending_orders:
                        del agent.pending_orders[order.orderid]
                        print(f"{agent.jid}> Vehicle {msg.sender} picked up order {order.orderid} "
                            f"({order.quantity}x{order.product} for {order.sender})")
                    else:
                        print(f"{agent.jid}> Order {order.orderid} not found in pending orders!")
                
                elif performative == "vehicle-delivery":
                    # Vehicle is delivering supplies from supplier
                    product = order.product
                    quantity = order.quantity
                    
                    if product in agent.stock:
                        agent.stock[product] += quantity
                    else:
                        agent.stock[product] = quantity
                    
                    print(f"{agent.jid}> Vehicle {msg.sender} delivered {quantity} units of {product}")
                    agent.print_stock()               
                
                
    
    class ReceiveTimeDelta(CyclicBehaviour):
        async def run(self):
            agent : Warehouse = self.agent
            
            msg : Message = await self.receive(timeout=20)
            
            if msg != None:
                delta = int(msg.body) # TODO -- assumes body holds ONLY the delta time
                self.current_time += delta
                
                # TODO -- implement update graph  
                agent.update_graph(msg)
    
    # ------------------------------------------
    #           AUXILARY FUNCTIONS
    # ------------------------------------------
    
    def calculate_supplier_score(self, accept_msg : Message) -> float:
        """
        Calculate the score for a supplier based on its distance to the warehouse.
        Lower score is better.
        """
        
        supplier_node_id = int(accept_msg.get_metadata("node_id"))
        path, score = self.map.djikstra(supplier_node_id, self.node_id)
        
        return score

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
        tick = self.current_tick
        
        order = Order(
            product=product,
            quantity=quantity,
            orderid=order_id,
            sender=sender,
            receiver=receiver,
            tick_received=tick
        )
        
        # Set locations
        order.sender_location = store_location  # Store location
        order.receiver_location = warehouse_location  # Warehouse location
        
        return order
        
    def set_buy_metadata(self, msg : Message):
        msg.set_metadata("performative", "warehouse-buy")
        msg.set_metadata("warehouse_id", str(self.jid))
        msg.set_metadata("request_id", str(self.request_counter))
    
    def print_stock(self):
        print("="*30)
        
        print(f"Current {self.jid} UNLOCKED stock:")
        for product, amount in self.stock.items():
            print(f"{product}: {amount}/{config.WAREHOUSE_MAX_PRODUCT_CAPACITY}")
        print("-"*30)
        
        print(f"Current {self.jid} LOCKED stock:")
        for product, amount in self.locked_stock.items():
            print(f"{product}: {amount}/{self.stock[product] + amount}")
        
        print("="*30)
    
    def update_graph(self, msg : Message):
        pass # TODO - implement if needed
    
    def dict_to_order(self, data : dict) -> Order:
        order =  Order(
            product=data["product"],
            quantity=data["quantity"],
            orderid=data["orderid"],
            sender=data["sender"],
            receiver=data["receiver"],
            sender_location=data["sender_location"],
            receiver_location=data["receiver_location"],
            tick_received=data.get("tick_received", 0)
        )
        return order
    # ------------------------------------------
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False):
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
    
    async def setup(self):
        # Initialize stock and time
        self.stock = {}
        self.current_tick = 0
        
        # Set the starting stock randomly
        product_max = config.WAREHOUSE_MAX_PRODUCT_CAPACITY
        for prod in config.PRODUCTS:
            self.stock[prod] = random.randint(0, product_max)
        
        self.current_capacity = {prod: product_max - quant for prod, quant in self.stock.items()}
        
        # Dict with products as keys and the sum of requested items as values
        self.locked_stock = {}
        self.print_stock()
        
        # Dict with order_id as key and Order object as value
        self.pending_orders : dict[int, Order] = {}
        self.request_counter : int = 0
        self.current_buy_request : Message = None
        self.failed_requests : queue.Queue = queue.Queue()
        
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
        # TODO - set template metadata if needed
        template.set_metadata("performative", "vehicle-pickup")
        self.add_behaviour(behav, template)
        
        # Run ReceiveVehicleArrival behaviour for deliveries
        behav = self.ReceiveVehicleArrival()
        template = Template()
        # TODO - set template metadata if needed
        template.set_metadata("performative", "vehicle-delivery")
        self.add_behaviour(behav, template)


"""
=================================
        MAIN FOR TESTING
=================================
"""
async def main():
    # Tente com diferentes credenciais
    ware_agent = Warehouse("warehouse@localhost", "password",1)
    
    try:
        await ware_agent.start(auto_register=True)
        print("Agent started successfully!")
    except Exception as e:
        print(f"Failed to start agent: {e}")
        return
    
    # Simulate both buy requests back-to-back
    class SendFirstBuyRequest(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            msg = Message(to="warehouse@localhost")
            msg.set_metadata("performative", "store-buy")
            msg.set_metadata("store_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "1")
            msg.body = "5 A"
            await self.send(msg)
            print("First buy request sent: 5 units of A")
    
    ware_agent.add_behaviour(SendFirstBuyRequest())
    
    class SendSecondBuyRequest(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1.5)
            msg = Message(to="warehouse@localhost")
            msg.set_metadata("performative", "store-buy")
            msg.set_metadata("store_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "2")
            msg.body = "3 B"
            await self.send(msg)
            print("Second buy request sent: 3 units of B")
    
    ware_agent.add_behaviour(SendSecondBuyRequest())
    
    # Simulate both confirmations after requests
    class SendFirstConfirmation(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(3)
            msg = Message(to="warehouse@localhost")
            msg.set_metadata("performative", "store-confirm")
            msg.set_metadata("warehouse_id", "warehouse@localhost")
            msg.set_metadata("store_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "1")
            msg.body = "5 A"
            await self.send(msg)
            print("First confirmation sent!")
    
    ware_agent.add_behaviour(SendFirstConfirmation())
    
    class SendSecondConfirmation(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(3.5)
            msg = Message(to="warehouse@localhost")
            msg.set_metadata("performative", "store-confirm")
            msg.set_metadata("warehouse_id", "warehouse@localhost")
            msg.set_metadata("store_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "2")
            msg.body = "3 B"
            await self.send(msg)
            print("Second confirmation sent!")
    
    ware_agent.add_behaviour(SendSecondConfirmation())
    
    await spade.wait_until_finished(ware_agent)
    
    
if __name__ == "__main__":
    spade.run(main())