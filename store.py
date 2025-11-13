import asyncio
import random
import queue
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, PeriodicBehaviour
from spade.message import Message
from spade.template import Template
from world.graph import Graph, Node

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
    
    # ------------------------------------------
    #         WAREHOUSE <-> STORE
    # ------------------------------------------
    
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
                msg.set_metadata("node_id", str(agent.node_id))
                msg.set_metadata("request_id", str(request_id_for_template))
                msg.body = f"{self.quantity} {self.product}"
                
                print(f"{agent.jid}> Sent request (id={msg.get_metadata('request_id')}):"
                      f"\"{msg.body}\" to {msg.to}")
                
                await self.send(msg)
            
            # Store the last message (or could store all if needed)
            if msg:
                agent.current_buy_request = msg
        
                # Collect responses from all warehouses
                behav = agent.CollectWarehouseResponses(
                    msg, 
                    request_id_for_template, 
                    len(contacts),
                    self.quantity,
                    self.product
                )
                agent.add_behaviour(behav)
                
                await behav.join()

    class CollectWarehouseResponses(OneShotBehaviour):
        def __init__(self, msg : Message, request_id : int, num_warehouses : int, quantity : int, product : str):
            super().__init__()
            self.request_id = request_id
            self.buy_msg = msg.body
            self.num_warehouses = num_warehouses
            self.quantity = quantity
            self.product = product
            self.acceptances = []  # List of (warehouse_jid, msg)
            self.rejections = []   # List of (warehouse_jid, msg, reason)
            
        async def run(self):
            agent : Store = self.agent
            
            # Setup template that accepts BOTH warehouse-accept AND warehouse-reject
            template = Template()
            template.set_metadata("store_id", str(agent.jid))
            template.set_metadata("request_id", str(self.request_id))
            # Don't filter by performative - we want both accept and reject
            
            # Create a combined behaviour to listen for both
            combined_behav = agent.ReceiveAllResponses(
                self.request_id,
                self.num_warehouses,
                self.acceptances,
                self.rejections
            )
            
            # Add with template that matches both performatives
            agent.add_behaviour(combined_behav, template)
            
            # Wait for collection to complete
            await combined_behav.join()
            
            # Now evaluate and choose best warehouse
            if self.acceptances:
                print(f"{agent.jid}> Received {len(self.acceptances)} acceptance(s) and {len(self.rejections)} rejection(s)")
                
                # Calculate scores for each warehouse that accepted
                best_warehouse = None
                best_score = float('inf')
                
                
                for warehouse_jid, msg in self.acceptances:
                    score = agent.calculate_warehouse_score(msg)
                    print(f"{agent.jid}> Warehouse {warehouse_jid} score: {score}")
                    
                    if score < best_score:
                        best_score = score
                        best_warehouse = (warehouse_jid, msg)
                
                if best_warehouse:
                    warehouse_jid, accept_msg = best_warehouse
                    print(f"{agent.jid}> Selected warehouse {warehouse_jid} with score {best_score}")
                    
                    # Send confirmation to the chosen warehouse
                    confirm_behav = agent.SendStoreConfirmation(accept_msg)
                    agent.add_behaviour(confirm_behav)
                    await confirm_behav.join()
                    
                    # Send denial to other warehouses that accepted but weren't chosen
                    for other_warehouse_jid, other_msg in self.acceptances:
                        if other_warehouse_jid != warehouse_jid:
                            deny_behav = agent.SendStoreDenial(other_msg)
                            agent.add_behaviour(deny_behav)
                            print(f"{agent.jid}> Sent denial to {other_warehouse_jid}")
                    
            else:
                print(f"{agent.jid}> No acceptances received. All warehouses rejected or timed out.")
                print(f"{agent.jid}> Request saved in self.failed_requests")
                
                # Add to failed requests
                failed_msg = Message(to=agent.current_buy_request.to)
                agent.set_buy_metadata(failed_msg)
                failed_msg.set_metadata("request_id", str(self.request_id))
                failed_msg.body = self.buy_msg
                agent.failed_requests.put(failed_msg)

    class ReceiveAllResponses(OneShotBehaviour):
        def __init__(self, request_id : int, num_warehouses : int, acceptances : list, rejections : list):
            super().__init__()
            self.request_id = request_id
            self.num_warehouses = num_warehouses
            self.acceptances = acceptances  # Shared list
            self.rejections = rejections    # Shared list
            self.responses_received = 0
            self.timeout = 5  # seconds to wait for all responses
            
        async def run(self):
            agent : Store = self.agent
            
            import time
            start_time = time.time()
            
            while self.responses_received < self.num_warehouses:
                elapsed = time.time() - start_time
                remaining_timeout = self.timeout - elapsed
                
                if remaining_timeout <= 0:
                    print(f"{agent.jid}> Timeout: Only received {self.responses_received}/{self.num_warehouses} responses")
                    break
                
                msg : Message = await self.receive(timeout=remaining_timeout)
                
                if msg:
                    performative = msg.get_metadata("performative")
                    warehouse_jid = str(msg.sender)
                    
                    if performative == "warehouse-accept":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        
                        print(f"{agent.jid}> Received acceptance from {warehouse_jid}: {quantity} {product}")
                        self.acceptances.append((warehouse_jid, msg))
                        
                    elif performative == "warehouse-reject":
                        parts = msg.body.split(" ")
                        quantity = int(parts[0])
                        product = parts[1]
                        reason = parts[2] if len(parts) > 2 else "unknown"
                        
                        print(f"{agent.jid}> Received rejection from {warehouse_jid}: {quantity} {product} (reason: {reason})")
                        self.rejections.append((warehouse_jid, msg, reason))
                    
                    self.responses_received += 1
                else:
                    # No more messages, timeout
                    break
            
            print(f"{agent.jid}> Finished collecting responses: {len(self.acceptances)} accepts, {len(self.rejections)} rejects")

    class SendStoreConfirmation(OneShotBehaviour):
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
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            
            print(f"{agent.jid}> Confirmation sent to {self.dest} for request: {msg.body}")

    class SendStoreDenial(OneShotBehaviour):
        def __init__(self, msg : Message):
            super().__init__()
            self.dest = msg.sender
            self.request_id = msg.get_metadata("request_id")
            parts = msg.body.split(" ")
            self.quantity = int(parts[0])
            self.product = parts[1]
        
        async def run(self):
            agent : Store = self.agent
            
            msg = Message(to=self.dest)
            msg.set_metadata("performative", "store-deny")
            msg.set_metadata("warehouse_id", str(self.dest))
            msg.set_metadata("store_id", str(agent.jid))
            msg.set_metadata("node_id", str(agent.node_id))
            msg.set_metadata("request_id", str(self.request_id))
            msg.body = f"{self.quantity} {self.product}"
            
            await self.send(msg)
            
            print(f"{agent.jid}> Denial sent to {self.dest} for request: {msg.body}")

    class ReceiveOrderCompletion(OneShotBehaviour):
        pass # TODO - implement if needed
    
    class RetryPreviousBuy(PeriodicBehaviour):
        async def run(self):
            agent : Store = self.agent
            
            if not agent.failed_requests.empty():
                request : Message = agent.failed_requests.get()
                request_id = request.get_metadata("request_id")
                parts = request.body.split(" ")
                quantity = int(parts[0])
                product = parts[1]
                
                contacts = list(agent.presence.contacts.keys())
                num_warehouses = len(contacts)
                
                for contact in contacts:
                    msg : Message = Message(to=contact)
                    agent.set_buy_metadata(msg)
                    msg.set_metadata("node_id", str(agent.node_id))
                    msg.set_metadata("request_id", str(request_id))
                    msg.body = request.body

                    print(f"{self.agent.jid}> Retrying request (id={request_id}):"
                          f"\"{msg.body}\" to {msg.to}")

                    await self.send(msg)

                # Use CollectWarehouseResponses instead
                behav = agent.CollectWarehouseResponses(msg, request_id, quantity, product, num_warehouses)
                agent.add_behaviour(behav)
                await behav.join()
    
    class ActionCycle(PeriodicBehaviour):
        def __init__(self, product_list, buy_prob, max_buy_quantity, period=10):
            super().__init__(period=period)
            self.product_list = product_list
            self.buy_prob = buy_prob
            self.max_buy_quantity = max_buy_quantity

        async def run(self):
            agent : Store = self.agent
            
            roll : float = random.randint(1,100) / 100.0
            if roll < self.buy_prob:
                product = random.choice(self.product_list)
                quantity = random.randint(1, self.max_buy_quantity)

                behav = agent.BuyProduct(quantity, product)
                agent.add_behaviour(behav)
            
    
    # ------------------------------------------
    #           AUXILARY FUNCTIONS
    # ------------------------------------------
    
    def calculate_warehouse_score(self, accept_msg : Message) -> float:
        """
        Calculate the score for a warehouse based its distance to the store.
        Lower score is better.
        """
        
        warehouse_id = int(accept_msg.get_metadata("node_id"))
        path, score = self.map.djikstra(warehouse_id, self.node_id)
        
        return score
      
    def set_buy_metadata(self, msg : Message):
        msg.set_metadata("performative", "store-buy")
        msg.set_metadata("store_id", str(self.jid))
        # Note: request_id should be set separately by the caller
    
    # ------------------------------------------
    
    def __init__(self, jid, password, map : Graph, node_id : int, port = 5222, verify_security = False):
        super().__init__(jid, password, port, verify_security)
        self.node_id = node_id
        self.map : Graph = map
    
    async def setup(self):
        self.stock = {}
        self.current_buy_request : Message = None
        self.failed_requests : queue.Queue = queue.Queue()
        self.request_counter = 0
        
        # Parameters for ActionCycle behaviour
        self.product_list = ["A", "B", "C", "D"]
        self.buy_prob = 0.5
        self.max_buy_quantity = 10

        behav = self.ActionCycle(self.product_list, self.buy_prob,
                                 self.max_buy_quantity, period=10)
        self.add_behaviour(behav)
        
        retry_behav = self.RetryPreviousBuy(period=5)
        self.add_behaviour(retry_behav)


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