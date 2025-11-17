import asyncio
import random
import queue
import json
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template
from spade.presence import PresenceShow
from world.graph import Graph, Node, Edge
from veiculos.veiculos import Order

class Supplier(Agent):
    
    """
    Class for the Supplier Agent.
    
    Currently able to:
        - Has INFINITE stock of all products
        - Permanently listen for buy requests from Warehouses (MULTIPLE AT A TIME)
        - Send "supplier-accept" messages
        - Receive "warehouse-confirm" messages
        - Track pending deliveries (in self.pending_deliveries)
        
    Usage instructions:
        - For Vehicles:
            - All vehicles must be subscribed in all suppliers and vice-versa
            - To get all pending orders, iterate over supplier_agent.pending_deliveries.values()
        
    Class variables:
        - self.pending_deliveries (dict[int, Order]): Dictionary with order_id as key and Order object as value.
        Use this to retrieve confirmed orders by their ID (useful for Vehicles).
            - keys: order_id (int)
            - values: Order object
            
        - self.total_supplied (dict()): tracks total quantities supplied per product
            - keys: product
            - values: total quantity supplied
    """
    
    # ------------------------------------------
    #          SUPPLIER <-> WAREHOUSE
    # ------------------------------------------
    
    class ReceiveBuyRequest(CyclicBehaviour):
        async def run(self):
            agent : Supplier = self.agent
        
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
                print(f"{agent.jid}> Got a request from {msg.sender}: id={request_id} quant={quant} product={product}")
                
                # Supplier has infinite stock - always accept
                accept_behav = agent.AcceptBuyRequest(msg)
                print(f"{agent.jid}> Accepting request for {quant} of {product} (infinite stock available)")
                
                # Track total supplied (no need to lock since infinite)
                if product in agent.total_supplied:
                    agent.total_supplied[product] += quant
                else:
                    agent.total_supplied[product] = quant

                print(f"Total {product} supplied: {agent.total_supplied[product]}")
                agent.print_stats()
                
                agent.add_behaviour(accept_behav)
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
            agent : Supplier = self.agent
            
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
            
            print(f"{agent.jid}> Sending supplier-accept message to {self.sender}")
            print(f"{agent.jid}> Message metadata: warehouse_id={self.sender}, request_id={self.request_id}")
            
            await self.send(msg)
            print(f"{agent.jid}> Message sent successfully!")
            
            # Wait for either confirmation or denial
            confirm_deny_behav = agent.ReceiveConfirmationOrDenial(msg, self.sender)
            
            # Template that matches BOTH warehouse-confirm AND warehouse-deny
            template = Template()
            template.set_metadata("supplier_id", str(agent.jid))
            template.set_metadata("warehouse_id", str(self.sender))
            template.set_metadata("request_id", str(self.request_id))
            
            agent.add_behaviour(confirm_deny_behav, template)
            print(f"{agent.jid}> AcceptBuyRequest finished, now waiting for confirmation or denial...")
            
            # Aguardar a confirmação ser recebida antes de terminar
            # await confirm_deny_behav.join()
            
    
    class ReceiveConfirmationOrDenial(OneShotBehaviour):
        def __init__(self, accept_msg : Message, sender_jid):
            super().__init__()
            self.accepted_id = int(accept_msg.get_metadata("request_id"))
            bod = accept_msg.body.split(" ")
            self.accepted_quantity = int(bod[0])
            self.accepted_product = bod[1]
            self.sender_jid = str(sender_jid)
        
        async def run(self):
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
                            
                        
                    print(f"{self.agent.jid}> Confirmation received! Delivery scheduled: {product}x{quantity}")
                    print(f"{self.agent.jid}> ReceiveConfirmationOrDenial finished.")

                    behav = self.agent.AssignVehicle(order.orderid)
                    self.agent.add_behaviour(behav)
                    
                    self.agent.print_stats()
                    
                elif performative == "warehouse-deny":
                    # Warehouse denied (chose another supplier) - just log it
                    print(f"{self.agent.jid}> Denial received! Warehouse chose another supplier.")
                    print(f"{self.agent.jid}> Order not confirmed for {product} x{quantity}")
                    
                    self.agent.print_stats()
                    
            else:
                print(f"{self.agent.jid}> Timeout: No confirmation or denial received in 10 seconds.")
                # Since supplier has infinite stock, no need to rollback
                # Just log that order wasn't confirmed
                print(f"{self.agent.jid}> Order not confirmed for {self.accepted_product} x{self.accepted_quantity}")
                
                self.agent.print_stats()
    
    class ReceiveVehicleArrival(CyclicBehaviour):
        def add_metadata(self, r_msg: Message, order : Order) -> Message:
            msg = r_msg
            msg.set_metadata("performative", "supplier-pickup-confirm")
            msg.set_metadata("supplier_id", str(self.agent.jid))
            msg.set_metadata("warehouse_id", str(order.sender))
            msg.set_metadata("node_id", str(self.agent.node_id))
            msg.set_metadata("request_id", str(order.orderid))
        
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
                    
                    # TODO - send message to vehicle
                    msg : Message = Message(to=msg.sender)
                    msg = self.add_metadata(msg, order)
                    await self.send(msg)
                    
                else:
                    print(f"{agent.jid}> Order {order.orderid} not found in pending orders!")
                
    
    class AssignVehicle(OneShotBehaviour):
        def __init__(self, request_id):
            super().__init__()
            self.request_id = request_id
        
        def populate_vehicles_from_contacts(self):
            """Populate vehicles list from presence contacts if empty"""
            agent : Supplier = self.agent
            if not agent.vehicles:
                agent.vehicles = [jid for jid in agent.presence.contacts.keys() if "vehicle" in str(jid)]
                if agent.vehicles:
                    print(f"{agent.jid}> Auto-populated vehicles from contacts: {agent.vehicles}")
            
        def create_call_for_proposal_message(self, to) -> Message:
            self.agent : Supplier
            
            msg : Message = Message(to=to)
            msg.set_metadata("performative", "order-proposal")
            msg.set_metadata("supplier_id", str(self.agent.jid))
            msg.set_metadata("node_id", str(self.agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            
            order = self.agent.pending_deliveries[self.request_id]
            msg.body = json.dumps(order.__dict__)
            return msg
        
        async def run(self):
            agent : Supplier = self.agent
            
            # Populate vehicles from contacts if list is empty
            self.populate_vehicles_from_contacts()
            
            if not agent.vehicles:
                print(f"{agent.jid}> ERROR: No vehicles found in contacts!")
                return
            
            n_available_vehicles = 0
            away_vehicles = []
            
            for vehicle_jid in agent.vehicles:
                # Check if vehicle has presence information available
                if vehicle_jid in agent.presence.contacts and agent.presence.contacts[vehicle_jid].is_available():
                    state = agent.presence.get_contact_presence(vehicle_jid)
                    
                    if state == PresenceShow.CHAT:
                        n_available_vehicles += 1
                        msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                        await self.send(msg)
                        print(f"{agent.jid}> Sent order proposal to {vehicle_jid} (AVAILABLE)")
                        
                    elif state == PresenceShow.AWAY:
                        away_vehicles.append(vehicle_jid)
                        print(f"{agent.jid}> Vehicle {vehicle_jid} is AWAY (busy)")
                else:
                    # No presence info available, send proposal anyway
                    print(f"{agent.jid}> No presence info for {vehicle_jid}. Sending proposal anyway.")
                    msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                    await self.send(msg)
                    n_available_vehicles += 1
            
            # If there are no available vehicles, try to contact away vehicles
            if n_available_vehicles == 0 and away_vehicles:
                print(f"{agent.jid}> No available vehicles. Trying AWAY vehicles: {away_vehicles}")
                for vehicle_jid in away_vehicles:
                    msg : Message = self.create_call_for_proposal_message(to=vehicle_jid)
                    await self.send(msg)
            
            if n_available_vehicles == 0 and not away_vehicles:
                print(f"{agent.jid}> WARNING: No vehicles available or contacted!")
                    
            behav = self.agent.ReceiveVehicleProposals()
            temp : Template = Template()
            temp.set_metadata("performative", "vehicle-proposal")
            temp.set_metadata("supplier_id", str(agent.jid))
            self.agent.add_behaviour(behav, temp)
            
            # Waits for all vehicle proposals to be received
            await behav.join()
                    
    class ReceiveVehicleProposals(OneShotBehaviour):
        
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
            print(f"{agent.jid}> Collecting vehicle proposals...")
            
            proposals = {}  # vehicle_jid : (can_fit, time)
            
            while True:
                msg : Message = await self.receive(timeout=10)
                
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
  
                else: break
            
            best_vehicle = self.get_best_vehicle(proposals)
            
            if best_vehicle:
                print(f"{agent.jid}> Best vehicle selected: {best_vehicle}")
                
                # Send assignment message to best vehicle
                msg : Message = Message(to=best_vehicle)
                msg.set_metadata("performative", "order-confirmation")
                msg.set_metadata("supplier_id", str(agent.jid))
                msg.set_metadata("node_id", str(agent.node_id))
                
                order = agent.pending_deliveries[order_id]
                msg.body = json.dumps(order.__dict__)
                
                await self.send(msg)
    
    class ReceiveTimeDelta(CyclicBehaviour):
        async def run(self):
            agent : Supplier = self.agent
            
            msg : Message = await self.receive(timeout=20)
            
            if msg != None:
                delta = int(msg.body) # TODO -- assumes body holds ONLY the delta time
                self.current_time += delta
                
                # TODO -- implement update graph  
                agent.update_graph(msg)
    
    # ------------------------------------------
    #           AUXILARY FUNCTIONS
    # ------------------------------------------
    
    def print_stats(self):
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

    def update_graph(self, msg : Message):
        # Parse message body - each line contains: startnode endnode newweight
        lines = msg.body.strip().split('\n')
        for line in lines:
            parts = line.strip().split()
            if len(parts) == 3:
                try:
                    start_node = int(parts[0])
                    end_node = int(parts[1])
                    new_weight = float(parts[2])
                    # Update the edge weight in the graph
                    edge : Edge = self.map.get_edge(start_node, end_node)
                    edge.weight = new_weight
                    print(f"{self.jid}> Updated edge ({start_node}, {end_node}) with weight {new_weight}")
                except (ValueError, AttributeError) as e:
                    print(f"{self.jid}> Error updating graph edge: {e}")
    
    def message_to_order(self, msg : Message) -> Order:
        """
        Convert a store-confirm message to an Order object.
        """
        body = msg.body
        parts = body.split(" ")
        quantity = int(parts[0])
        product = parts[1]
        
        order_id = msg.get_metadata("request_id")
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
            receiver=receiver
        )
        
        # Set locations
        order.sender_location = store_location  # Store location
        order.receiver_location = warehouse_location  # Warehouse location
        
        return order
    
    
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
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False):
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
        node : Node = self.map.get_node(node_id)
        self.pos_x = node.x
        self.pos_y = node.y
        
        # Extract instance number from JID for ID encoding (e.g., "supplier1@localhost" -> 1)
        jid_name = str(jid).split('@')[0]
        instance_id = int(''.join(filter(str.isdigit, jid_name)))
        
        # Calculate ID base: Supplier type code = 3
        self.id_base = (3 * 100_000_000) + (instance_id * 1_000_000)
    
    async def setup(self):
        self.presence.approve_all = True
        
        # Supplier has infinite stock - no need to track stock levels
        # Just track what's been supplied
        self.total_supplied = {}
        self.current_tick = 0
        
        # Track pending deliveries by order_id
        self.pending_deliveries : dict[int, Order] = {}
        
        # Identify vehicles from presence contacts
        self.vehicles = []
        for vehicle in self.presence.contacts.keys():
            if "vehicle" in str(vehicle):
                self.vehicles.append(vehicle)
        
        print(f"{self.jid}> Supplier initialized with INFINITE stock")
        self.print_stats()
        
        behav = self.ReceiveBuyRequest()
        template = Template()
        template.set_metadata("performative", "warehouse-buy")
        self.add_behaviour(behav, template)


"""
=================================
        MAIN FOR TESTING
=================================
"""
async def main():
    supplier_agent = Supplier("supplier@localhost", "password")
    
    try:
        await supplier_agent.start(auto_register=True)
        print("Supplier agent started successfully!")
    except Exception as e:
        print(f"Failed to start supplier agent: {e}")
        return
    
    # Simulate buy requests from warehouses
    class SendFirstBuyRequest(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1)
            msg = Message(to="supplier@localhost")
            msg.set_metadata("performative", "warehouse-buy")
            msg.set_metadata("warehouse_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "1")
            msg.body = "50 A"
            await self.send(msg)
            print("First buy request sent: 50 units of A")
    
    supplier_agent.add_behaviour(SendFirstBuyRequest())
    
    class SendSecondBuyRequest(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(1.5)
            msg = Message(to="supplier@localhost")
            msg.set_metadata("performative", "warehouse-buy")
            msg.set_metadata("warehouse_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "2")
            msg.body = "100 B"
            await self.send(msg)
            print("Second buy request sent: 100 units of B")
    
    supplier_agent.add_behaviour(SendSecondBuyRequest())
    
    # Simulate confirmations from warehouses
    class SendFirstConfirmation(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(3)
            msg = Message(to="supplier@localhost")
            msg.set_metadata("performative", "warehouse-confirm")
            msg.set_metadata("supplier_id", "supplier@localhost")
            msg.set_metadata("warehouse_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "1")
            msg.body = "50 A"
            await self.send(msg)
            print("First confirmation sent!")
    
    supplier_agent.add_behaviour(SendFirstConfirmation())
    
    class SendSecondConfirmation(OneShotBehaviour):
        async def run(self):
            await asyncio.sleep(3.5)
            msg = Message(to="supplier@localhost")
            msg.set_metadata("performative", "warehouse-confirm")
            msg.set_metadata("supplier_id", "supplier@localhost")
            msg.set_metadata("warehouse_id", "warehouse@localhost")  # self-send for test
            msg.set_metadata("request_id", "2")
            msg.body = "100 B"
            await self.send(msg)
            print("Second confirmation sent!")
    
    supplier_agent.add_behaviour(SendSecondConfirmation())
    
    await asyncio.sleep(5)
    
    # Print final stats
    print("\n=== FINAL SUPPLIER STATS ===")
    supplier_agent.print_stats()
    
    await spade.wait_until_finished(supplier_agent)
    
    
if __name__ == "__main__":
    spade.run(main())
