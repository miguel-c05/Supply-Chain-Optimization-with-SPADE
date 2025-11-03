import asyncio
import random
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

class Warehouse(Agent):
    
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
                print(f"Got a request from {msg.sender}: id={request_id} quant={quant} product={product}")
                
                if (product in agent.stock.keys()) and agent.stock[product] >= quant:
                    accept_behav = agent.AcceptBuyRequest(msg)
                    agent.add_behaviour(accept_behav)
                    
                    # Aguardar o comportamento terminar
                    print("AcceptBuyRequest finished, now waiting for confirmation...")
                    await accept_behav.join()
                    
                    print("="*30)
                    print("Current stock:")
                    for product, amount in self.agent.stock.items():
                        print(f"{product}: {amount}")
                    print("="*30)
                else:
                    print("Could not satisfy request.")
            else:
                print("Did not get any buy requests in 60 seconds.")

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
                f"Accepted a request from {self.sender}: "
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
            print("ReceiveConfirmation finished, stock updated.")
            
    class ReceiveConfirmation(OneShotBehaviour):
        async def run(self):
            print("Waiting for store confirmation...")
            msg : Message = await self.receive(timeout=10)
            
            if msg != None:
                # Message with body format "id quantity type"
                request = msg.body.split(" ")
                quantity = int(request[1])
                product = request[2]
                
                self.agent.stock[product] -= quantity
                print(f"Confirmation received! Stock updated: {product} -= {quantity}")
            else:
                print("Timeout: No confirmation received in 10 seconds")
                
            
            
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
        print("Startup stock:")
        for product, amount in self.stock.items():
            print(f"{product}: {amount}")
        print("="*30)
        
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