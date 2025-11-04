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
    
    warehouses = [w1,w2,w3,w4,w5]

    await store_agent.start(auto_register=True)
    # store_agent.web.start("localhost", "10000")  # Comentado - causa erro de presença
    
    port = 10000
    for w in warehouses:
        await w.start(auto_register=True)
        #w.web.start("localhost", str(port)) # Comentado - causa erro de presença
        
        store_agent.presence.subscribe(w.jid)
        w.presence.approve_all = True
        port += 1
    
    # Adicionar o behaviour em vez de apenas criar
    behav = store_agent.BuyProduct(3, "A")
    store_agent.add_behaviour(behav)
    await behav.join()
    print("="*60)
    print("END OF BUY A. MOVING TO BUY B")
    print("="*60)
    
    
    behav = store_agent.BuyProduct(3, "B")
    store_agent.add_behaviour(behav)
    
    await spade.wait_until_finished(store_agent)
    
if __name__ == "__main__":
    spade.run(main())