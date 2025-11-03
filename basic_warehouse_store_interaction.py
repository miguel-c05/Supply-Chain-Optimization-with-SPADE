import spade
import asyncio
from store import Store
from warehouse import Warehouse

async def main():
    store_agent = Store("store1@localhost", "pass")

    w1 = Warehouse("ware1@localhost", "pass")
    w2 = Warehouse("ware2@localhost", "pass")
    w3 = Warehouse("ware3@localhost", "pass")
    w4 = Warehouse("ware4@localhost", "pass")
    w5 = Warehouse("ware5@localhost", "pass")

    await store_agent.start(auto_register=True)
    # store_agent.web.start("localhost", "10000")  # Comentado - causa erro de presença
    
    await w1.start(auto_register=True)
    await w2.start(auto_register=True)
    await w3.start(auto_register=True)
    await w4.start(auto_register=True)
    await w5.start(auto_register=True)
    # w1.web.start("localhost", "10001")  # Comentado - causa erro de presença
    # w2.web.start("localhost", "10002")
    # w3.web.start("localhost", "10003")
    # w4.web.start("localhost", "10004")
    # w5.web.start("localhost", "10005")
    
    # Aguardar um pouco para os agentes estarem prontos
    await asyncio.sleep(2)
    
    store_agent.presence.subscribe("ware1@localhost")
    store_agent.presence.subscribe("ware2@localhost")
    store_agent.presence.subscribe("ware3@localhost")
    store_agent.presence.subscribe("ware4@localhost")
    store_agent.presence.subscribe("ware5@localhost") 
    w1.presence.approve_all = True
    w2.presence.approve_all = True
    w3.presence.approve_all = True
    w4.presence.approve_all = True
    w5.presence.approve_all = True
    
    # Adicionar o behaviour em vez de apenas criar
    behav = store_agent.BuyProduct(3, "A")
    store_agent.add_behaviour(behav)
    
    await spade.wait_until_finished(store_agent)
    
if __name__ == "__main__":
    spade.run(main())