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
from world.graph import Graph
from veiculos.veiculos import Order
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
                    
                    behav = self.agent.AssignVehicle(order.orderid)
                    self.agent.add_behaviour(behav)

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
    
    class AssignVehicle(OneShotBehaviour):
        def __init__(self, request_id):
            super().__init__()
            self.request_id = request_id
        
        def populate_vehicles_from_contacts(self):
            """Populate vehicles list from presence contacts if empty"""
            agent : Supplier = self.agent
            
            # Get all vehicles from presence contacts
            vehicles = [str(jid) for jid in agent.presence.contacts.keys() if "vehicle" in str(jid)]
            
            if vehicles:
                agent.vehicles = vehicles
                print(f"{agent.jid}> 🔍 Discovered {len(vehicles)} vehicle(s) from presence: {vehicles}")
            else:
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
            agent : Warehouse = self.agent
            
            # Populate vehicles from contacts
            has_vehicles = self.populate_vehicles_from_contacts()
            
            if not has_vehicles:
                print(f"{agent.jid}> ❌ ERROR: No vehicles found in contacts!")
                print(f"{agent.jid}> Make sure vehicles are started and have subscribed to this supplier.")
                return
            
            print(f"{agent.jid}> 📤 Requesting vehicle proposals...")
            print(f"{agent.jid}> Vehicles to contact: {agent.vehicles}")
            
            # Enviar mensagens de proposal a todos os veículos
            # Não verificamos presença - deixamos cada veículo decidir se pode aceitar
            n_available_vehicles = 0
            away_vehicles = []
            for vehicle_jid in agent.vehicles:
                
                msg : Message = self.create_presence_info_message(to=vehicle_jid)
                await self.send(msg)
                
                behav = agent.ReceivePresenceInfo()
                temp : Template = Template()
                temp.set_metadata("performative", "presence-response")
                temp.set_metadata("vehicle_id", str(vehicle_jid))
                agent.add_behaviour(behav, temp)
                
                await behav.join()
                print(f"{agent.jid}> Presence info from {vehicle_jid}: {agent.presence_infos}")
                
                if agent.presence_infos[vehicle_jid] == "PresenceShow.CHAT":
                    msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                    await self.send(msg)
                    n_available_vehicles += 1
                    print(f"{agent.jid}> ✉️ Sent order proposal to {vehicle_jid}")
                
                elif agent.presence_infos[vehicle_jid] == "PresenceShow.AWAY" and n_available_vehicles == 0:
                    away_vehicles.append(vehicle_jid)
                    print(f"{agent.jid}> ⚠️ Vehicle {vehicle_jid} is away.")
                    
            if n_available_vehicles == 0:
                print(f"{agent.jid}> ⚠️ No AVAILABLE vehicles found. All vehicles are AWAY.")
                for vehicle_jid in away_vehicles:
                    msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                    await self.send(msg)
                    print(f"{agent.jid}> ✉️ Sent order proposal to {vehicle_jid}")
            
            print(f"{agent.jid}> 📨 Sent proposals to {n_available_vehicles} vehicle(s)")
                    
            behav = agent.ReceiveVehicleProposals(self.request_id)
            temp : Template = Template()
            temp.set_metadata("performative", "vehicle-proposal")
            agent.add_behaviour(behav, temp)
            
            # Waits for all vehicle proposals to be received
            await behav.join()
    
    class ReceivePresenceInfo(OneShotBehaviour):
        async def run(self):
            agent : Warehouse = self.agent
            
            msg : Message = await self.receive(timeout=10)
            
            if msg:
                data = json.loads(msg.body)
                presence_info = data["presence_show"]
                print(f"{agent.jid}> Received presence info response from {msg.sender}:"
                      f"{presence_info}")
                agent.presence_infos[msg.get_metadata("vehicle_id")] = presence_info
            else:
                print(f"{agent.jid}> No presence info response received from vehicle.")
                  
    class ReceiveVehicleProposals(OneShotBehaviour):
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
            agent : Warehouse = self.agent
            print(f"{agent.jid}> 📤 Collecting vehicle proposals...")
            
            proposals = {}  # vehicle_jid : (can_fit, time)
            
            while True:
                msg : Message = await self.receive(timeout=5)
                
                if msg:
                    print(f"{agent.jid}> Received vehicle proposal from {msg.sender}")
                    data = json.loads(msg.body)
                    
                    # A proposta do veículo não é uma Order, são apenas dados da proposta
                    order_id = data["orderid"]
                    sender_jid = str(msg.sender)
                    can_fit = data["can_fit"]
                    time = data["delivery_time"]
                    
                    proposals[sender_jid] = (can_fit, time)
                    print(f"{agent.jid}> Vehicle {sender_jid} proposal: can_fit={can_fit}, time={time}")
  
                else: 
                    print(f"{agent.jid}> ⏱️ Timeout - no more proposals received")
                    break
            
            print(f"{agent.jid}> 📊 Total proposals received: {len(proposals)}")
            best_vehicle = self.get_best_vehicle(proposals)
            
            if best_vehicle:
                
                print(f"{agent.jid}> 🏆 Best vehicle selected: {best_vehicle}")
                
                # Send confirmation to the selected vehicle
                msg : Message = Message(to=best_vehicle)
                msg.set_metadata("performative", "order-confirmation")
                
                order : Order = agent.pending_orders[order_id]
                order_data = {
                    "orderid" : order.orderid,
                    "confirmed" : True
                }
                msg.body = json.dumps(order_data)
                
                await self.send(msg)
                print(f"{agent.jid}> ✉️ Confirmation sent to {best_vehicle} for order {order_id}")
                
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
                    print(f"{agent.jid}> ❌ Rejection sent to {vehicle_jid} for order {order_id}")
            else:
                print(f"{agent.jid}> ⚠️ No vehicles available to assign!")       
    
    # ------------------------------------------
    #         WAREHOUSE <-> SUPPLIER
    # ------------------------------------------      
    class BuyMaterial(OneShotBehaviour):
        def __init__(self, quantity, product):
            super().__init__()
            self.quantity = quantity
            self.product = product
        
        def populate_suppliers_from_contacts(self):
            """Populate suppliers list from presence contacts if empty"""
            agent : Warehouse = self.agent
            if not agent.suppliers:
                agent.suppliers = [jid for jid in agent.presence.contacts.keys() if "supplier" in str(jid)]
                if agent.suppliers:
                    print(f"{agent.jid}> Auto-populated suppliers from contacts: {agent.suppliers}")
        
        async def run(self):
            agent : Warehouse = self.agent
            
            # Populate suppliers from contacts if list is empty
            self.populate_suppliers_from_contacts()
            
            if not agent.suppliers:
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
                    len(agent.suppliers),
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
    
    # ------------------------------------------
    #         COMMON / OTHER BEHAVIORS
    # ------------------------------------------

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
                data = json.loads(msg.body)
                
                type : str = data["type"]
                delta : int = data["time"]
                agent.current_tick += delta
                
                if type.lower() != "arrival":
                    map_updates = data["data"]                   
                
                # TODO -- implement update graph  
                agent.update_graph(map_updates)
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
        path, fuel, time = self.map.djikstra(supplier_node_id, self.node_id)
        
        return time  # Use time as score (could also use fuel)

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
        print("-"*30)
                
        print(f"Current {self.jid} PENDING ORDERS:")
        if self.pending_orders:
            for order_id, order in self.pending_orders.items():
                print(f"Order {order_id}: {order.quantity}x{order.product} "
                      f"from {order.sender} to {order.receiver}")
        else:
            print("No pending orders")
        
        print("="*30)
    
    def update_graph(self, msg : Message):
        pass # TODO - implement if needed
    
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
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False, contact_list = []):
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
        self.contact_list = contact_list
        # Extract instance number from JID for ID encoding (e.g., "warehouse1@localhost" -> 1)
        jid_name = str(jid).split('@')[0]
        instance_id = int(''.join(filter(str.isdigit, jid_name)))

        # Calculate ID base: Warehouse type code = 2
        self.id_base = (2 * 100_000_000) + (instance_id * 1_000_000)
        
        # Initialize critical attributes early to avoid AttributeError
        self.pending_orders : dict[int, Order] = {} # order_id as key and Order object as value
        self.vehicle_proposals : dict[int, dict[str, tuple[bool]]] = {}
        self.vehicles = []
        self.suppliers = []
        self.request_counter : int = 0
    
    async def setup(self):
        self.presence.approve_all = True
        for contact in self.contact_list:
            self.presence.subscribe(contact)
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
        
        # Run ReceiveVehicleArrival behaviour for deliveries
        behav = self.ReceiveVehicleArrival()
        template = Template()
        template.set_metadata("performative", "vehicle-delivery")
        self.add_behaviour(behav, template)
        
        # Run ReceiveTimeDelta
        behav = self.ReceiveTimeDelta()
        template = Template()
        template.set_metadata("performative", "time-delta")
        self.add_behaviour(behav, template)

"""
=================================
        MAIN FOR TESTING
=================================
"""
async def main():
    from world.world import World
    
    # Create a world with suppliers and warehouses
    world = World(width=2, height=2, warehouses=1, suppliers=1, stores=1, mode="uniform")
    graph = world.graph
    
    # Create warehouse agent
    warehouse_node = None
    store_node = None
    supplier_node = None
    for node_id, node in graph.nodes.items():
        if node.warehouse:
            warehouse_node = node_id
        if node.store:
            store_node = node_id
        if node.supplier:
            supplier_node = node_id
    
    if not warehouse_node:
        print("ERROR: No warehouse node found!")
        return
    
    warehouse = Warehouse(f"warehouse{warehouse_node}@localhost", "pass", graph, warehouse_node)
    await warehouse.start(auto_register=True)
    
    print(f"✅ Warehouse started at node {warehouse_node}")
    print(f"Initial stock:")
    warehouse.print_stock()
    
    # Setup presence
    warehouse.presence.set_available()
    warehouse.presence.approve_all = True
    
    # Subscribe to fake vehicles
    fake_vehicle1_jid = "vehicle1@localhost"
    fake_vehicle2_jid = "vehicle2@localhost"
    warehouse.presence.subscribe(fake_vehicle1_jid)
    warehouse.presence.subscribe(fake_vehicle2_jid)
    warehouse.vehicles = [fake_vehicle1_jid, fake_vehicle2_jid]
    
    await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("TEST 1: CREATE PENDING ORDER (STORE REQUEST + CONFIRMATION)")
    print("="*60)
    
    # Simulate store sending order request
    class SimulateStoreOrder(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(0.5)
            msg = Message(to=f"warehouse{warehouse_node}@localhost")
            msg.sender = f"store{store_node}@localhost"
            msg.set_metadata("performative", "store-buy")
            msg.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg.set_metadata("store_id", f"store{store_node}@localhost")
            msg.set_metadata("node_id", str(store_node))
            msg.set_metadata("request_id", "0")
            msg.body = "10 A"
            
            await self.send(msg)
            print(f"📤 Simulated store order: {msg.body}")
    
    warehouse.add_behaviour(SimulateStoreOrder())
    await asyncio.sleep(2)
    
    # Simulate store confirmation
    class SimulateStoreConfirmation(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(0.5)
            msg = Message(to=f"warehouse{warehouse_node}@localhost")
            msg.sender = f"store{store_node}@localhost"
            msg.set_metadata("performative", "store-confirm")
            msg.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg.set_metadata("store_id", f"store{store_node}@localhost")
            msg.set_metadata("node_id", str(store_node))
            msg.set_metadata("request_id", "0")
            msg.body = "10 A"
            
            await self.send(msg)
            print(f"📤 Simulated store confirmation: {msg.body}")
    
    warehouse.add_behaviour(SimulateStoreConfirmation())
    await asyncio.sleep(2)
    
    # Check pending orders
    print(f"\n📦 Pending orders: {len(warehouse.pending_orders)}")
    for order_id, order in warehouse.pending_orders.items():
        print(f"  Order {order_id}: {order.quantity}x{order.product} "
              f"to {order.sender} (store location: {order.sender_location})")
    
    print("\n" + "="*60)
    print("TEST 2: SIMULATE MULTIPLE VEHICLE PROPOSALS")
    print("="*60)
    
    await asyncio.sleep(1)
    
    # Simulate vehicle proposals (warehouse should have sent order-proposal)
    class SimulateVehicle1Proposal(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            # Vehicle 1: can fit, delivery time = 25
            msg = Message(to=f"warehouse{warehouse_node}@localhost")
            msg.sender = "vehicle1@localhost"
            msg.set_metadata("performative", "vehicle-proposal")
            msg.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg.set_metadata("vehicle_id", "vehicle1@localhost")
            msg.set_metadata("request_id", "0")
            
            # Body is JSON with order data + can_fit + delivery_time
            order = warehouse.pending_orders[0]
            proposal_data = {
                "orderid": order.orderid,
                "product": order.product,
                "quantity": order.quantity,
                "sender": order.sender,
                "receiver": order.receiver,
                "sender_location": order.sender_location,
                "receiver_location": order.receiver_location,
                "can_fit": True,
                "delivery_time": 25
            }
            msg.body = json.dumps(proposal_data)
            
            await self.send(msg)
            print(f"📤 Vehicle1 proposal: can_fit=True, time=25")
    
    warehouse.add_behaviour(SimulateVehicle1Proposal())
    
    class SimulateVehicle2Proposal(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1.5)
            # Vehicle 2: can fit, delivery time = 15 (BEST!)
            msg = Message(to=f"warehouse{warehouse_node}@localhost")
            msg.sender = "vehicle2@localhost"
            msg.set_metadata("performative", "vehicle-proposal")
            msg.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg.set_metadata("vehicle_id", "vehicle2@localhost")
            msg.set_metadata("request_id", "0")
            
            order = warehouse.pending_orders[0]
            proposal_data = {
                "orderid": order.orderid,
                "product": order.product,
                "quantity": order.quantity,
                "sender": order.sender,
                "receiver": order.receiver,
                "sender_location": order.sender_location,
                "receiver_location": order.receiver_location,
                "can_fit": True,
                "delivery_time": 15  # Faster!
            }
            msg.body = json.dumps(proposal_data)
            
            await self.send(msg)
            print(f"📤 Vehicle2 proposal: can_fit=True, time=15 (BEST!)")
    
    warehouse.add_behaviour(SimulateVehicle2Proposal())
    
    await asyncio.sleep(3)
    print("\n✅ Warehouse should have selected vehicle2 (lowest delivery time)")
    
    print("\n" + "="*60)
    print("TEST 3: SIMULATE VEHICLE PICKUP")
    print("="*60)
    
    # Simulate vehicle picking up the order
    class SimulateVehiclePickup(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            if warehouse.pending_orders:
                order_id = list(warehouse.pending_orders.keys())[0]
                order = warehouse.pending_orders[order_id]
                
                msg = Message(to=f"warehouse{warehouse_node}@localhost")
                msg.sender = "vehicle2@localhost"
                msg.set_metadata("performative", "vehicle-pickup")
                msg.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
                msg.set_metadata("vehicle_id", "vehicle2@localhost")
                msg.set_metadata("order_id", str(order_id))
                
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
                print(f"📤 Vehicle2 picking up order {order_id}")
            else:
                print("❌ No pending orders to pickup!")
    
    warehouse.add_behaviour(SimulateVehiclePickup())
    await asyncio.sleep(2)
    
    print(f"\n📦 Pending orders after pickup: {len(warehouse.pending_orders)}")
    if not warehouse.pending_orders:
        print("  ✅ Order successfully picked up!")
    
    print("\n" + "="*60)
    print("TEST 4: SIMULATE VEHICLE DELIVERY (SUPPLIER RESTOCK)")
    print("="*60)
    
    print(f"\nStock BEFORE delivery:")
    warehouse.print_stock()
    
    # Simulate vehicle delivering supplies from supplier
    class SimulateVehicleDelivery(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            delivery_order = {
                "product": "B",
                "quantity": 50,
                "orderid": 999,
                "sender": f"supplier{supplier_node}@localhost",
                "receiver": f"warehouse{warehouse_node}@localhost",
                "sender_location": supplier_node,
                "receiver_location": warehouse_node
            }
            
            msg = Message(to=f"warehouse{warehouse_node}@localhost")
            msg.sender = "vehicle1@localhost"
            msg.set_metadata("performative", "vehicle-delivery")
            msg.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg.set_metadata("vehicle_id", "vehicle1@localhost")
            msg.set_metadata("order_id", "999")
            msg.body = json.dumps(delivery_order)
            
            await self.send(msg)
            print(f"📤 Vehicle1 delivering: 50 units of B from supplier")
    
    warehouse.add_behaviour(SimulateVehicleDelivery())
    await asyncio.sleep(2)
    
    print(f"\nStock AFTER delivery:")
    warehouse.print_stock()
    
    print("\n" + "="*60)
    print("TEST 5: VEHICLE THAT CANNOT FIT")
    print("="*60)
    
    # Create another order
    class CreateAnotherOrder(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(0.5)
            msg1 = Message(to=f"warehouse{warehouse_node}@localhost")
            msg1.sender = f"store{store_node}@localhost"
            msg1.set_metadata("performative", "store-buy")
            msg1.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg1.set_metadata("store_id", f"store{store_node}@localhost")
            msg1.set_metadata("node_id", str(store_node))
            msg1.set_metadata("request_id", "1")
            msg1.body = "5 C"
            await self.send(msg1)
            
            await asyncio.sleep(1)
            
            msg2 = Message(to=f"warehouse{warehouse_node}@localhost")
            msg2.sender = f"store{store_node}@localhost"
            msg2.set_metadata("performative", "store-confirm")
            msg2.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg2.set_metadata("store_id", f"store{store_node}@localhost")
            msg2.set_metadata("node_id", str(store_node))
            msg2.set_metadata("request_id", "1")
            msg2.body = "5 C"
            await self.send(msg2)
            
            print(f"📤 Created order: 5 C")
    
    warehouse.add_behaviour(CreateAnotherOrder())
    await asyncio.sleep(3)
    
    # Simulate proposals where only one can fit
    class SimulateCannotFitProposal(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            
            # Vehicle 1: CANNOT FIT
            order = warehouse.pending_orders[1]
            proposal1 = {
                "orderid": order.orderid,
                "product": order.product,
                "quantity": order.quantity,
                "sender": order.sender,
                "receiver": order.receiver,
                "sender_location": order.sender_location,
                "receiver_location": order.receiver_location,
                "can_fit": False,
                "delivery_time": 10
            }
            
            msg1 = Message(to=f"warehouse{warehouse_node}@localhost")
            msg1.sender = "vehicle1@localhost"
            msg1.set_metadata("performative", "vehicle-proposal")
            msg1.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg1.set_metadata("vehicle_id", "vehicle1@localhost")
            msg1.set_metadata("request_id", "1")
            msg1.body = json.dumps(proposal1)
            await self.send(msg1)
            print(f"📤 Vehicle1 proposal: can_fit=FALSE, time=10")
            
            await asyncio.sleep(0.5)
            
            # Vehicle 2: CAN FIT
            proposal2 = {
                "orderid": order.orderid,
                "product": order.product,
                "quantity": order.quantity,
                "sender": order.sender,
                "receiver": order.receiver,
                "sender_location": order.sender_location,
                "receiver_location": order.receiver_location,
                "can_fit": True,
                "delivery_time": 20
            }
            
            msg2 = Message(to=f"warehouse{warehouse_node}@localhost")
            msg2.sender = "vehicle2@localhost"
            msg2.set_metadata("performative", "vehicle-proposal")
            msg2.set_metadata("warehouse_id", f"warehouse{warehouse_node}@localhost")
            msg2.set_metadata("vehicle_id", "vehicle2@localhost")
            msg2.set_metadata("request_id", "1")
            msg2.body = json.dumps(proposal2)
            await self.send(msg2)
            print(f"📤 Vehicle2 proposal: can_fit=TRUE, time=20")
    
    warehouse.add_behaviour(SimulateCannotFitProposal())
    await asyncio.sleep(3)
    
    print("\n✅ Warehouse should have selected vehicle2 (only one that can fit)")
    
    print("\n" + "="*60)
    print("📊 FINAL STATE")
    print("="*60)
    print(f"Pending orders: {len(warehouse.pending_orders)}")
    for order_id, order in warehouse.pending_orders.items():
        print(f"  Order {order_id}: {order.quantity}x{order.product}")
    
    print(f"\nFinal stock:")
    warehouse.print_stock()
    
    await asyncio.sleep(2)
    await warehouse.stop()
    print("\n✅ All vehicle interaction tests completed!")

if __name__ == "__main__":
    spade.run(main())
