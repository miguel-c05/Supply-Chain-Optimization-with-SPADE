import asyncio
import random
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

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
        - Lock stock in order to make process several requests at a time
        - Buy materials from a Supplier Agent (placeholder setup) 
        - Setup intelligent buying method
        - Communicate with other Warehouses
        - Communicate with Vehicles
    """
    
    
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
                    print(f"{agent.jid}> Could not satisfy request.")
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
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quant} {self.product}"
            
            await self.send(msg)
            
            confirm_behav = agent.ReceiveConfirmation(msg, self.sender)
            template = Template()
            template.set_metadata("performative", "store-confirm")
            template.set_metadata("warehouse_id", str(agent.jid))
            template.set_metadata("store_id", str(self.sender))
            template.set_metadata("request_id", str(self.request_id))
            
            agent.add_behaviour(confirm_behav, template)
            print(f"{agent.jid}> AcceptBuyRequest finished, now waiting for confirmation...")
            
            # Aguardar a confirmação ser recebida antes de terminar
            # await confirm_behav.join()
            
            
    class ReceiveConfirmation(OneShotBehaviour):
        def __init__(self, accept_msg : Message, sender_jid):
            super().__init__()
            self.accepted_id = int(accept_msg.get_metadata("request_id"))
            bod = accept_msg.body.split(" ")
            self.accepted_quantity = int(bod[0])
            self.accepted_product = bod[1]
            self.sender_jid = str(sender_jid)
            self.sender_jid = str(sender_jid)
        
        async def run(self):
            print(f"{self.agent.jid}> Waiting for store confirmation...")
            msg : Message = await self.receive(timeout=10)
            
            if msg != None:
                self.agent : Warehouse
                
                # Message with body format "quantity product"
                request = msg.body.split(" ")
                quantity = int(request[0])
                product = request[1]
                
                # Update warehouse locked stock
                self.agent.locked_stock[product] -= quantity
                
                # Put bought items aside (in self.pending_orders)
                pending_orders = self.agent.pending_orders
                jid = msg.sender
                if jid not in pending_orders:
                    pending_orders[jid] = {}
                    pending_orders[jid][product] = quantity
                elif product not in pending_orders[jid]:
                    pending_orders[jid][product] = quantity
                else:
                    pending_orders[jid][product] += quantity
                        
                    
                print(f"{self.agent.jid}> Confirmation received! Stock updated: {product} -= {quantity}")
                print(f"{self.agent.jid}> ReceiveConfirmation finished, stock updated.")

                self.agent.print_stock()
            else:
                print(f"{self.agent.jid}> Timeout: No confirmation received in 10 seconds. Unlocking stock...")
                self.agent.locked_stock[self.accepted_product] -= self.accepted_quantity
                self.agent.stock[self.accepted_product] += self.accepted_quantity
                
                self.agent.print_stock()
            
            
                
            
            
    class AssignVehicle(OneShotBehaviour):
        async def run(self):
            pass
    
    class BuyMaterial(OneShotBehaviour):
        def __init__(self, quantity, product):
            super().__init__()
            self.quantity = quantity
            self.product = product
        
        async def run(self):
            pass # TODO - implement Suppliers and complete func
        
    class CommunicationPhase(OneShotBehaviour):
        async def run(self):
            pass
    
    class ActionPhase(OneShotBehaviour):
        async def run(self):
            pass
    
    def print_stock(self):
        print("="*30)
        
        print(f"Current {self.jid} UNLOCKED stock:")
        for product, amount in self.stock.items():
            print(f"{product}: {amount}")
            
        print("-"*30)
        
        print(f"Current {self.jid} LOCKED stock:")
        for product, amount in self.locked_stock.items():
            print(f"{product}: {amount}")
        
        print("="*30)

    
    async def setup(self):
        self.stock = {"A" : random.randint(0,20),
                      "B" : random.randint(0,20),
                      "C" : random.randint(0,20),}
        
        # Dict with products as keys and the sum of requested items as values
        self.locked_stock = {}
        
        self.print_stock()
        
        """
        self.pending_orders has the following structure:
        
        dict(   jid :   dict(   product: quantity,
                                product: quantity,
                                ...),
                jid :   dict(   product: quantity,
                                product: quantity,
                                ...),
                ...
            )
        """
        self.pending_orders = {}
        
        behav = self.ReceiveBuyRequest()
        template = Template()
        template.set_metadata("performative", "store-buy")
        self.add_behaviour(behav, template)
        


"""
=================================
        MAIN FOR TESTING
=================================
"""
async def main():
    # Tente com diferentes credenciais
    ware_agent = Warehouse("warehouse@localhost", "password")
    
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