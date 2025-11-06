from hello_agent import MyAgent
import spade
from spade.agent import Agent

async def main():
    print("trying to exec MyAgent now...")
    agent = MyAgent("callee@localhost", "idk")
    await agent.start()

if __name__ == "__main__":
    spade.run(main())