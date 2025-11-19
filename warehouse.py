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

class Warehouse(Agent):
    
    """
    Class for the Warehouse Agent.
    
    Currently able to:
        - Generate random starting stock (1 to 20 over products A, B and C)
        - Permanently listen for buy requests (NOW MULTIPLE AT A TIME)
        - Send "warehouse-accept" messages
        - Receive "store-confirm" messages
        - Update stock
        - Put bought items aside (in self.pending_deliveries) while they are not transported
        
    Usage instructions:
        - For Vehicles:
            - All vehicles must be subscribed in all warehouses and vice-versa
            - To get all all orders from a store_agent, get
            warehouse_agent.pending_deliveries[store_agent.jid]
    
    What is missing (TODO):
        - Communicate with Vehicles
        
    Class variables:
        - self.stock (dict()): current AVAILABLE stock
            - keys: products
            - values: quantity
        
        - self.locked_stock (dict()): stock that is being used for some request process
            - keys: products
            - values: quantity

        - self.pending_deliveries (dict()): Dictionary with order_id as key and Order object as value.
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
                    agent.stock[product] -= quant
                    
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
        def __init__(self, msg : Message):
            super().__init__()
            self.request_id = int(msg.get_metadata("request_id"))
            request = msg.body.split(" ")
            self.quant = int(request[0])
            self.product = request[1]
            self.sender = msg.sender
        
        async def run(self):
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
            if agent.verbose:
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
                    self.agent.stock[product] += quantity
                    
                    if self.agent.verbose:
                        self.agent.print_stock()
                    
            else:
                if self.agent.verbose:
                    print(f"{self.agent.jid}> Timeout: No confirmation or denial received in 10 seconds. Unlocking stock...")
                self.agent.locked_stock[self.accepted_product] -= self.accepted_quantity
                self.agent.stock[self.accepted_product] += self.accepted_quantity
                
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
                    
                    n_sent_messages += 1
                    print(f"{agent.jid}> ✉️ Sent order proposal to {vehicle_jid}")
            
            if agent.verbose:
                print(f"{agent.jid}> 📨 Sent proposals to {n_sent_messages} vehicle(s)")
                    
            behav = self.agent.ChooseBestVehicle(self.request_id, n_sent_messages)
            self.agent.add_behaviour(behav, temp)
            
            # Waits for all vehicle proposals to be received
            await behav.join()
    
    class ReceivePresenceInfo(OneShotBehaviour):
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
            
            if agent.verbose:
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
            
            if agent.verbose:
                print(f"{agent.jid}> Denial sent to {self.dest} for request: {msg.body}")
    
    class RetryPreviousBuy(OneShotBehaviour):
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
                agent.update_graph(map_updates)
    
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
    
    def update_graph(self, traffic_data) -> None:
        for edge_info in traffic_data.get("edges", []):
                node1_id = edge_info.get("node1")
                node2_id = edge_info.get("node2")
                new_weight = edge_info.get("weight")
                
                edge : Edge = self.map.get_edge(node1_id, node2_id)
                if edge:
                    edge.weight = new_weight

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
