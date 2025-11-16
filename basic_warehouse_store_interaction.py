import spade
import asyncio
from store import Store
from warehouse import Warehouse
from world.world import World

async def main():
    # Create a world with stores and warehouses assigned to nodes
    world = World(width=3, height=3, warehouses=5, stores=1, mode="uniform")
    graph = world.graph
    
    # Iterate over nodes and instance agents based on node purpose
    stores = []
    warehouses = []
    
    for node_id, node in graph.nodes.items():
        if node.store:
            store_agent = Store(f"store{node_id}@localhost", "pass", graph, node_id)
            stores.append(store_agent)
            print(f"✅ Created Store agent at node {node_id}")
        
        elif node.warehouse:
            warehouse_agent = Warehouse(f"warehouse{node_id}@localhost", "pass", graph, node_id)
            warehouses.append(warehouse_agent)
            print(f"✅ Created Warehouse agent at node {node_id}")
    
    # Start all agents
    for store in stores:
        await store.start(auto_register=True)
    
    for warehouse in warehouses:
        await warehouse.start(auto_register=True)
    
    # Setup presence subscriptions
    for store in stores:
        for warehouse in warehouses:
            store.presence.subscribe(warehouse.jid)
            warehouse.presence.approve_all = True
    
    await asyncio.sleep(2)
    
    print("\n" + "="*60)
    print("📊 INITIAL STATE")
    print("="*60)
    print(f"World: {world.width}x{world.height} grid, seed={world.seed}, mode={world.mode}")
    print(f"Stores: {len(stores)}, Warehouses: {len(warehouses)}\n")
    
    for store in stores:
        print(f"Store at node {store.node_id} (pos: {store.pos_x}, {store.pos_y})")
        print(f"  Stock: {store.stock}\n")
    
    for warehouse in warehouses:
        print(f"Warehouse at node {warehouse.node_id} (pos: {warehouse.pos_x}, {warehouse.pos_y})")
        warehouse.print_stock()
        print()
    
    # Test buying with the first store
    if stores:
        store_agent = stores[0]
        
        print("="*60)
        print("🛒 BUYING 10 UNITS OF A")
        print("="*60)
        
        behav = store_agent.BuyProduct(10, "A")
        store_agent.add_behaviour(behav)
        await behav.join()
        
        await asyncio.sleep(3)
        
        print("\n" + "="*60)
        print("🛒 BUYING 10 UNITS OF B")
        print("="*60)
        
        behav = store_agent.BuyProduct(10, "B")
        store_agent.add_behaviour(behav)
        await behav.join()
        
        await asyncio.sleep(3)
        
        print("\n" + "="*60)
        print("📊 FINAL STATE")
        print("="*60)
        print(f"Store stock: {store_agent.stock}\n")
        
        for warehouse in warehouses:
            print(f"Warehouse at node {warehouse.node_id}:")
            warehouse.print_stock()
            print()
    
    await asyncio.sleep(2)
    
    # Stop all agents
    for store in stores:
        await store.stop()
    for warehouse in warehouses:
        await warehouse.stop()
    
    print("✅ Simulation complete!")
    
if __name__ == "__main__":
    spade.run(main())