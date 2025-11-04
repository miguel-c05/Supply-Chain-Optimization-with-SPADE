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
        - Permanently listen for buy requests (only one request may be taken at a time)
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
        - Buy materials from a Supplier Agent (placeholder setup) 
        - Setup intelligent buying method
        - Communicate with other Warehouses
        - Communicate with Vehicles
    """
    
    
    class ReceiveBuyRequest(CyclicBehaviour):
        async def run(self):
            agent : Warehouse = self.agent
        
            print("Awaiting buy request...")
            msg = await self.receive(timeout=60)
            if msg != None:
                """
                Messages with metadata ("performative", "store", "buy") have body
                with the following format:
                
                "request_id product_quantity product_type"
                """
                request = msg.body.split(" ")
                request_id = int(request[0])
                quant = int(request[1])
                product = request[2]
                print(f"{self.agent.jid}> Got a request from {msg.sender}: id={request_id} quant={quant} product={product}")
                
                if (product in agent.stock.keys()) and agent.stock[product] >= quant:
                    accept_behav = agent.AcceptBuyRequest(msg)
                    agent.add_behaviour(accept_behav)
                    
                    # Aguardar o comportamento terminar
                    await accept_behav.join()
                    print(f"{self.agent.jid}> AcceptBuyRequest finished, now waiting for confirmation...")
                    
                    print("="*30)
                    print("Current stock:")
                    for product, amount in self.agent.stock.items():
                        print(f"{product}: {amount}")
                    print("="*30)
                else:
                    print(f"{self.agent.jid}> Could not satisfy request.")
            else:
                print(f"{self.agent.jid}> Did not get any buy requests in 60 seconds.")

    class AcceptBuyRequest(OneShotBehaviour):
        def __init__(self, msg : Message):
            super().__init__()
            request = msg.body.split(" ")
            self.request_id = int(request[0])
            self.quant = int(request[1])
            self.product = request[2]
            self.sender = msg.sender
            self.body = msg.body
        
        async def run(self):
            print(
                f"{self.agent.jid}> Accepted a request from {self.sender}: "
                f"id={self.request_id} "
                f"quant={self.quant} "
                f"product={self.product}"
            )
            
            
            msg = Message(to=self.sender)
            msg.set_metadata("performative", "warehouse-accept")
            msg.body = self.body
            
            await self.send(msg)
            
            agent : Warehouse = self.agent
            confirm_behav = agent.ReceiveConfirmation()
            template = Template()
            template.set_metadata("performative", "store-confirm")
            
            agent.add_behaviour(confirm_behav, template)
            
            # Aguardar a confirmação ser recebida antes de terminar
            await confirm_behav.join()
            print(f"{self.agent.jid}> ReceiveConfirmation finished, stock updated.")
            
    class ReceiveConfirmation(OneShotBehaviour):
        async def run(self):
            print(f"{self.agent.jid}> Waiting for store confirmation...")
            msg : Message = await self.receive(timeout=10)
            
            if msg != None:
                self.agent : Warehouse
                
                # Message with body format "id quantity type"
                request = msg.body.split(" ")
                quantity = int(request[1])
                product = request[2]
                
                # Update warehouse stock
                self.agent.stock[product] -= quantity
                
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
            else:
                print(f"{self.agent.jid}> Timeout: No confirmation received in 10 seconds")
                
            
            
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
    

    async def setup(self):
        self.stock = {"A" : random.randint(0,20),
                      "B" : random.randint(0,20),
                      "C" : random.randint(0,20),}
        print("="*30)
        print(f"Startup {self.jid} stock:")
        for product, amount in self.stock.items():
            print(f"{product}: {amount}")
        print("="*30)
        
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
MAIN FOR TESTING

Working so far:
    - Permanently listening for requests
    - Recieves messages with metadata ("performative", "store-buy")
    - If request is satisfiable, sends confirmation message and updates stock
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
    
    # Criar comportamento para enviar mensagem de teste
    class SendTestMessage(OneShotBehaviour):
        async def run(self):
            msg = Message(to="warehouse@localhost")
            msg.set_metadata("performative", "store-buy")
            msg.body = "1 10 A"
            await self.send(msg)
            print("Test message sent!")
    
    ware_agent.add_behaviour(SendTestMessage())
    
    # Criar comportamento para enviar mensagem de confirmação de teste
    class SendTestConfirmation(OneShotBehaviour):
        async def run(self):
            msg = Message(to="warehouse@localhost")
            msg.set_metadata("performative", "store-confirm")
            msg.body = "1 3 A"
            await self.send(msg)
            print("Test confirmation message sent!")

    await asyncio.sleep(2)
    ware_agent.add_behaviour(SendTestConfirmation())
    
    await spade.wait_until_finished(ware_agent)
    
    
if __name__ == "__main__":
    spade.run(main())