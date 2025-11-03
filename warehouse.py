import asyncio
import getpass
import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
from spade.message import Message
from spade.template import Template

class Warehouse(Agent):
    
    class RecieveBuyRequest(CyclicBehaviour):
        async def run(self):
            print("Awaiting buy request...")
            
    
    
    
    
    async def setup(self):
        pass