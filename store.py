import asyncio
import random
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

class Store(Agent):

    
    class BuyProduct(OneShotBehaviour):
        def __init__(self, quantity : int, product : str):
            super().__init__()
            self.quantity = quantity
            self.product = product
            self.agent : Store
        
        async def run(self):
            agent : Store = self.agent
            agent.active_requests[agent.request_counter] = (self.quantity, self.product)
            contacts = list(agent.presence.contacts.keys())
            
            for contact in contacts:
                msg : Message = Message(to=contact)
                msg.set_metadata("performative", "store-buy")
                msg.body = f"{agent.request_counter} {self.quantity} {self.product}"
                
                print(f"Sent request \"{msg.body}\" to {msg.to}")
                
                await self.send(msg)
            agent.request_counter += 1
                
            behav = agent.RecieveAcceptance()
            template = Template()
            template.set_metadata("performative", "warehouse-accept")
            agent.add_behaviour(behav, template)

    class RecieveAcceptance(OneShotBehaviour):
        async def run(self):
            self.agent : Store
            
            # Para ja guardamos apenas uma das mensagens recebidas (n escolhemos)
            msg : Message = await self.receive(timeout=5)
            
            if msg != None:
                rec = msg.body.split(" ")
                rec_id = rec[0]
                quantity = rec[1]
                product = rec[2]
                
                print(
                    f"Recieved acceptance from {msg.sender}: "
                    f"id={rec_id} "
                    f"quant={quantity} "
                    f"product={product}"
                )
                
                if product in self.agent.stock:
                    self.agent.stock[product] += quantity
                else:
                    self.agent.stock[product] = quantity
                
                self.agent.active_requests.pop(rec_id, None)
                
                behav = self.agent.SendConfirmation(msg)
                self.agent.add_behaviour(behav)
    
    class SendConfirmation(OneShotBehaviour):
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.confirmation = msg.body
        
        async def run(self):
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "store-confirm")
            msg.body = self.confirmation
            
            await self.send(msg)
            
            print(f"Confirmation sent to {self.dest} for request: {msg.body}")
    
    
    async def setup(self):
        self.stock = {}
        self.active_requests = {}
        self.request_counter = 0


async def main():
    store_agent : Store = Store("store@localhost", "pass")
    
    
    await store_agent.start()
    store_agent.web.start("localhost", "10000")
    store_agent.presence.subscribe("store@localhost")
    print("Sent subscription request to store@localhost")
    
    store_agent.presence.approve_all = True
    store_agent.presence.approve_subscription("store@localhost")
    print(f"Accepted subscription request from store@localhost")
    
    
    behav = store_agent.BuyProduct(3, "A")
    store_agent.add_behaviour(behav)
    
    class SendTestAcceptance(OneShotBehaviour):
        async def run(self):  
            # Send test acceptance message
            test_msg = Message(to="store@localhost")
            test_msg.sender = "warehouse@localhost"
            test_msg.set_metadata("performative", "warehouse-accept")
            test_msg.body = "0 3 A"
            
            await self.send(test_msg)
            print(f"Sent acceptance of request {test_msg.body}")

    await asyncio.sleep(2)
    store_agent.add_behaviour(SendTestAcceptance())
    
    await spade.wait_until_finished(store_agent)
    
if __name__ == "__main__":
    spade.run(main())