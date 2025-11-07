import asyncio
import random
import queue
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

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
            - To get all orders from a warehouse_agent, get
            supplier_agent.pending_deliveries[warehouse_agent.jid]
    
    What is missing (TODO):
        - Communicate with Vehicles for delivery
        - Implement delivery tracking/completion
        - Add pricing/billing logic
        
    Class variables:
        - self.pending_deliveries (dict(list())): each key is a warehouse JID and the value
        is a list of confirmed buy Message objects for that warehouse. Use this to
        retrieve all confirmed orders for a warehouse (useful for Vehicles or
        transport assignment).
            - keys: warehouse.jid
            - values: list() of spade.message.Message (confirmed "warehouse-confirm" messages)
            
        - self.total_supplied (dict()): tracks total quantities supplied per product
            - keys: product
            - values: total quantity supplied
    """
    
    
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
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quant} {self.product}"
            
            await self.send(msg)
            
            confirm_behav = agent.ReceiveWarehouseConfirmation(msg, self.sender)
            template = Template()
            template.set_metadata("performative", "warehouse-confirm")
            template.set_metadata("supplier_id", str(agent.jid))
            template.set_metadata("warehouse_id", str(self.sender))
            template.set_metadata("request_id", str(self.request_id))
            
            agent.add_behaviour(confirm_behav, template)
            print(f"{agent.jid}> AcceptBuyRequest finished, now waiting for confirmation...")
            
            # Aguardar a confirmação ser recebida antes de terminar
            # await confirm_behav.join()
            
            
    class ReceiveWarehouseConfirmation(OneShotBehaviour):
        def __init__(self, accept_msg : Message, sender_jid):
            super().__init__()
            self.accepted_id = int(accept_msg.get_metadata("request_id"))
            bod = accept_msg.body.split(" ")
            self.accepted_quantity = int(bod[0])
            self.accepted_product = bod[1]
            self.sender_jid = str(sender_jid)
        
        async def run(self):
            print(f"{self.agent.jid}> Waiting for warehouse confirmation...")
            msg : Message = await self.receive(timeout=10)
            
            if msg != None:
                self.agent : Supplier
                
                # Message with body format "quantity product"
                request = msg.body.split(" ")
                quantity = int(request[0])
                product = request[1]
                
                # Put confirmed orders in pending_deliveries
                # Store the confirmation message object so other agents (e.g.
                # Vehicles) can inspect the full message when assigning/collecting
                # orders. pending_deliveries[jid] is a list of Message objects.
                pending_deliveries : dict = self.agent.pending_deliveries
                jid = str(msg.sender)
                if jid not in pending_deliveries:
                    pending_deliveries[jid] = []
                pending_deliveries[jid].append(msg)
                        
                    
                print(f"{self.agent.jid}> Confirmation received! Delivery scheduled: {product} x{quantity}")
                print(f"{self.agent.jid}> ReceiveWarehouseConfirmation finished.")

                self.agent.print_stats()
            else:
                print(f"{self.agent.jid}> Timeout: No confirmation received in 10 seconds.")
                # Since supplier has infinite stock, no need to rollback
                # Just log that order wasn't confirmed
                print(f"{self.agent.jid}> Order not confirmed for {self.accepted_product} x{self.accepted_quantity}")
                
                self.agent.print_stats()
            
            
    class CommunicationPhase(OneShotBehaviour):
        async def run(self):
            pass
    
    class ActionPhase(OneShotBehaviour):
        async def run(self):
            pass
    
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
            
        print(f"\nPending Deliveries by Warehouse:")
        if self.pending_deliveries:
            for warehouse_jid, messages in self.pending_deliveries.items():
                print(f"  {warehouse_jid}: {len(messages)} order(s)")
        else:
            print("  None")
        
        print("="*40)

    def __init__(self, jid, password, node_id : int, port = 5222, verify_security = False):
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
    
    async def setup(self):
        # Supplier has infinite stock - no need to track stock levels
        # Just track what's been supplied
        self.total_supplied = {}
        
        # Track pending deliveries per warehouse
        self.pending_deliveries = {}
        
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
