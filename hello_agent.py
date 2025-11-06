import spade
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour, CyclicBehaviour
import asyncio


class MyAgent(Agent):
    """
    A simple SPADE agent that runs a OneShotBehaviour to print "Hello World".
    """
    class CounterBehav(CyclicBehaviour):
        async def on_start(self):
            print(f"Starting {super().__class__.__name__} behaviour...")
            self.counter = 0
            
        async def run(self):
            line = f"Counting: {self.counter} second"
            # pluralize when the counter is not exactly 1
            if self.counter != 1: line += "s"
            line += " passed"
            print(line)
            self.counter += 1
            
            #if (self.counter >= 5): self.kill(); return
            
            await asyncio.sleep(1)
            
        async def on_end(self):
            line = f"In total the behaviour ran for {self.counter} second"
            if self.counter != 1: line += "s"
            print(line)
            await self.agent.stop()
            
    
    class FirstBehav(OneShotBehaviour):
        async def run(self):
            line = f"Counting: {self.counter} second{'s' if self.counter != 1 else ''}"
            print(line)
            self.counter += 1
            await asyncio.sleep(1)
            """
            The main logic of the behavior: prints a message and stops the agent.
            """
            print("Hello World from Agent!")
            
            # Crucial: Stop the agent after the behavior is executed once
            await self.agent.stop()

    async def setup(self):
        """
        Called when the agent is initialized. Adds the behavior.
        """
        print(f"Agent {self.jid} starting up.")
        self.add_behaviour(self.CounterBehav())


async def main():
    """
    Initializes and starts the agent instance.
    """
    # NOTE: Ensure you have an XMPP server (like ejabberd or the built-in test server) 
    # running on 'localhost' for this agent to connect.
    agent = MyAgent("agent@localhost", "password")
    
    # Start the agent and wait for it to be ready
    await agent.start()
    agent.web.start(hostname="127.0.0.1", port="10000")
    await spade.wait_until_finished(agent)
    # The main coroutine can now wait or return. 
    # Since MyBehav stops the agent, the spade runtime will exit shortly.
    

if __name__ == "__main__":
    print("--- Starting SPADE Runtime ---")
    # spade.run() handles initializing the asyncio event loop and running main()
    spade.run(main())
    print("--- SPADE Runtime Finished ---")
