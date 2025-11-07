import asyncio
import random
import queue
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

class Store(Agent):
    
    """
    Class for the Store Agent.
    
    Currently able to:
        -
        
    Usage instructions:
        - To buy x units of product Y, call self.BuyProduct(x,Y)
        - Only ONE request must be sent at once. To make multiple requests await the
        previous BuyProduct request
    
    What is missing (TODO):
        - Implement repetition for missed requests (already stored in self.failed_requests)
        
    Class variables:
        - self.stock (dict): current inventory
            - keys (str): product
            - values (int): quantity

        - self.request_counter (int): a counter that serves as the requests id
        - self.current_buy_request (Message): holds the current buy request Message
        - self.failed_requests (queue.Queue(Message)): a queue that holds all failed buy request
        Messages. A request is enqueued if ReceiveAcceptance times out.
    """
    
    class BuyProduct(OneShotBehaviour):
        def __init__(self, quantity : int, product : str):
            super().__init__()
            self.quantity = quantity
            self.product = product
            self.agent : Store
        
        async def run(self):
            agent : Store = self.agent
            contacts = list(agent.presence.contacts.keys())
            
            # Get request_id before sending
            request_id_for_template = agent.request_counter
            agent.request_counter += 1
            
            msg = None  # Will store the last sent message for current_buy_request
            for contact in contacts:
                msg = Message(to=contact)
                msg.set_metadata("performative", "store-buy")
                msg.set_metadata("store_id", str(agent.jid))
                msg.set_metadata("request_id", str(request_id_for_template))
                msg.body = f"{self.quantity} {self.product}"
                
                print(f"{agent.jid}> Sent request (id={msg.get_metadata('request_id')}):"
                      f"\"{msg.body}\" to {msg.to}")
                
                await self.send(msg)
            
            # Store the last message (or could store all if needed)
            if msg:
                agent.current_buy_request = msg
        
                behav = agent.RecieveAcceptance(msg)
                template = Template()
                template.set_metadata("performative", "warehouse-accept")
                template.set_metadata("store_id", str(agent.jid))
                template.set_metadata("request_id", str(request_id_for_template))
                agent.add_behaviour(behav, template)
                
                await behav.join()

    class RecieveAcceptance(OneShotBehaviour):
        def __init__(self, msg : Message):
            super().__init__()
            self.request_id = msg.get_metadata("request_id")
            self.buy_msg = msg.body
            
        async def run(self):
            self.agent : Store
            
            # Para ja guardamos apenas uma das mensagens recebidas (n escolhemos)
            msg : Message = await self.receive(timeout=5)
            
            if msg != None:
                rec_id = msg.get_metadata("request_id")
                rec = msg.body.split(" ")
                quantity = int(rec[0])
                product = rec[1]
                
                print(
                    f"{self.agent.jid}> Recieved acceptance from {msg.sender}: "
                    f"id={rec_id} "
                    f"quant={quantity} "
                    f"product={product}"
                )
                
                behav = self.agent.SendConfirmation(msg)
                self.agent.add_behaviour(behav)
                
                await behav.join()
            
            else:
                print(f"{self.agent.jid}> No acceptance gotten. Request \"{self.buy_msg}\" "
                      f"saved in self.failed_requests")
                
                # Actually add the failed request to the queue
                agent : Store = self.agent
                failed_msg = Message(to=agent.current_buy_request.to)
                agent.set_buy_metadata(failed_msg)
                failed_msg.set_metadata("request_id", str(self.request_id))
                failed_msg.body = self.buy_msg
                agent.failed_requests.put(failed_msg)
    
    class SendConfirmation(OneShotBehaviour):
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
            
        
        async def run(self):
            agent : Store = self.agent
            
            if self.product in self.agent.stock:
                agent.stock[self.product] += self.quantity
            else:
                agent.stock[self.product] = self.quantity           
            
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "store-confirm")
            msg.set_metadata("warehouse_id", str(self.dest))
            msg.set_metadata("store_id", str(agent.jid))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            
            print(f"{agent.jid}> Confirmation sent to {self.dest} for request: {msg.body}")

    class RetryPreviousBuy(OneShotBehaviour):
        async def run(self):
            agent : Store = self.agent
            
            if not agent.failed_requests.empty():
                request : Message = agent.failed_requests.get()
                request_id = request.get_metadata("request_id")
                contacts = list(agent.presence.contacts.keys())
                
                for contact in contacts:
                    msg : Message = Message(to=contact)
                    agent.set_buy_metadata(msg)
                    msg.set_metadata("request_id", str(request_id))
                    msg.body = request.body

                    print(f"{self.agent.jid}> Retrying request (id={request_id}):"
                          f"\"{msg.body}\" to {msg.to}")

                    await self.send(msg)

                behav = agent.RecieveAcceptance(msg)
                template = Template()
                template.set_metadata("performative", "warehouse-accept")
                template.set_metadata("store_id", str(agent.jid))
                template.set_metadata("request_id", str(request_id))
                agent.add_behaviour(behav, template)

                await behav.join()
                
            
    class CommunicationPhase(OneShotBehaviour):
        async def run(self):
            agent : Store = self.agent
            
        
        
            
            template = Template()
            # TODO - introduzir metadata de msg de "end action"
            behav = agent.ActionPhase()
            agent.add_behaviour(behav, template)
        
    class ActionPhase(OneShotBehaviour):
        async def run(self):
            agent : Store = self.agent
            
            
            
            end_msg = await self.receive(timeout=40)
            
            template = Template()
            # TODO - introduzir metadata de "end communication"
            behav = agent.CommunicationPhase()
        
    def set_buy_metadata(self, msg : Message):
        msg.set_metadata("performative", "store-buy")
        msg.set_metadata("store_id", str(self.jid))
        # Note: request_id should be set separately by the caller
    
    async def setup(self):
        self.stock = {}
        self.current_buy_request : Message = None
        self.failed_requests : queue.Queue = queue.Queue()
        self.request_counter = 0
        
        self.communication_queue : queue.Queue = queue.Queue()
        self.action_queue : queue.Queue = queue.Queue()


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
            test_msg.set_metadata("warehouse_id", "warehouse@localhost")
            test_msg.set_metadata("store_id", "store@localhost")
            test_msg.set_metadata("request_id", "0")
            test_msg.body = "3 A"
            
            await self.send(test_msg)
            print(f"Sent acceptance of request {test_msg.body} with id={test_msg.get_metadata('request_id')}")

    behav = SendTestAcceptance()
    store_agent.add_behaviour(SendTestAcceptance())
    await asyncio.sleep(2)
    
    print("\n=== Testing Retry Method ===")
    await asyncio.sleep(3)
    
    # Manually add a failed request to the queue for testing
    failed_msg = Message(to="warehouse@localhost")
    store_agent.set_buy_metadata(failed_msg)
    failed_msg.body = "5 B"
    store_agent.failed_requests.put(failed_msg)
    print(f"Added failed request to queue: {failed_msg.body}")
    
    # Trigger retry behaviour
    retry_behav = store_agent.RetryPreviousBuy()
    store_agent.add_behaviour(retry_behav)
    
    await asyncio.sleep(2)
    
    await spade.wait_until_finished(store_agent)
    
if __name__ == "__main__":
    spade.run(main())