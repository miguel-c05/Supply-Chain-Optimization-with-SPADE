import asyncio
import getpass
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour
from spade.message import Message
from spade.template import Template

class SenderAgent(Agent):
    
    class InformBehav(OneShotBehaviour):
        async def on_start(self):
            await asyncio.sleep(5)
            self.counter = 1
        
        async def run(self):
            print("InformBehav running.")
            msg : Message = Message(to="reciever@localhost")
            msg.set_metadata("performative", "inform")
            msg.body = f"Sent message number {self.counter}."
            
            await self.send(msg)
            print("Message sent!")
            
            await self.agent.stop()
    
    async def setup(self):
        print(f"{self.__class__.__name__} activated.")
        behav = self.InformBehav()
        self.add_behaviour(behav)
        
class RecieverAgent(Agent):
    
    class RecieveBehav(OneShotBehaviour):
        async def run(self):
            print("RecieveBehav running.")
            msg = await self.receive(timeout=10)
            
            if msg: print(f"Recieved message number {msg.body[-2]}")
            else: print("No message recieved in 10 seconds")
            
            await self.agent.stop()
            
    async def setup(self):
        print(f"{self.__class__.__name__} started.")
        behav = self.RecieveBehav()
        temp : Template = Template()
        temp.set_metadata("performative", "inform")
        self.add_behaviour(behav, temp)
        
async def main():
    rec_agent = RecieverAgent("reciever@localhost", "recpass")
    send_agent = SenderAgent("sender@localhost", "sendpass")
    
    await rec_agent.start()
    await send_agent.start()
    rec_agent.web.start("localhost", "10000")
    send_agent.web.start("localhost", "10001")
    
    await spade.wait_until_finished(rec_agent)
    print("Communication over.")
    
if __name__ == "__main__":
    spade.run(main())