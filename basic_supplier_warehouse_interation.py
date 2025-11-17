import spade
import asyncio
from warehouse import Warehouse
from supplier import Supplier
from world.world import World

async def main():
    # Create a world with suppliers and warehouses assigned to nodes
    world = World(width=2, height=2, warehouses=1, suppliers=1, mode="uniform")
    graph = world.graph
    
    # Iterate over nodes and instance agents based on node purpose
    suppliers : list[Supplier] = []
    warehouses : list[Warehouse] = []
    
    for node_id, node in graph.nodes.items():
        if node.supplier:
            supplier_agent = Supplier(f"supplier{node_id}@localhost", "pass", graph, node_id)
            suppliers.append(supplier_agent)
            print(f"✅ Created Supplier agent at node {node_id}")
        
        elif node.warehouse:
            warehouse_agent = Warehouse(f"warehouse{node_id}@localhost", "pass", graph, node_id)
            warehouses.append(warehouse_agent)
            print(f"✅ Created Warehouse agent at node {node_id}")
    
    # Start all agents
    for supplier in suppliers:
        await supplier.start(auto_register=True)
    
    for warehouse in warehouses:
        await warehouse.start(auto_register=True)
    
    print("\n✅ Agents started successfully!\n")
    
    # Setup presence subscriptions (warehouses subscribe to suppliers)
    await asyncio.sleep(1)
    for warehouse in warehouses:
        for supplier in suppliers:
            warehouse.presence.subscribe(supplier.jid)
            supplier.presence.approve_all = True
    
    await asyncio.sleep(1)
    print("✅ Presence configured\n")
    
    # Display initial state
    print("="*60)
    print("📊 INITIAL STATE")
    print("="*60)
    print(f"World: {world.width}x{world.height} grid, seed={world.seed}, mode={world.mode}")
    print(f"Suppliers: {len(suppliers)}, Warehouses: {len(warehouses)}\n")
    
    for supplier in suppliers:
        print(f"Supplier at node {supplier.node_id} (pos: {supplier.pos_x}, {supplier.pos_y})")
        supplier.print_stats()
        print()
    
    for warehouse in warehouses:
        print(f"Warehouse at node {warehouse.node_id} (pos: {warehouse.pos_x}, {warehouse.pos_y})")
        warehouse.print_stock()
        print()
    
    # Test buying with the first warehouse (if available)
    if warehouses and suppliers:
        warehouse1 = warehouses[0]
        supplier1 = suppliers[0]
        
        # Simulate warehouse buying from supplier using BuyMaterial behaviour
        await asyncio.sleep(2)
        
        print("="*60)
        print("📦 WAREHOUSE BUYING FROM SUPPLIER")
        print("="*60)
        
        # Use the warehouse's BuyMaterial behaviour
        buy_behav = warehouse1.BuyMaterial(25, "A")
        warehouse1.add_behaviour(buy_behav)
        print("🛒 Warehouse initiating purchase of 25 units of A...\n")
        
        # Wait for the full interaction cycle to complete
        await buy_behav.join()
        
        # Give time for confirmation to be processed
        await asyncio.sleep(3)
        
        # Display final state
        print("\n" + "="*60)
        print("📊 FINAL STATE")
        print("="*60)
        warehouse1.print_stock()
        supplier1.print_stats()
        
        # Optional: Try another purchase
        print("\n" + "="*60)
        print("🔄 SECOND PURCHASE: 50 units of B")
        print("="*60)
        
        buy_behav2 = warehouse1.BuyMaterial(50, "B")
        warehouse1.add_behaviour(buy_behav2)
        await buy_behav2.join()
        await asyncio.sleep(3)
        
        print("\n" + "="*60)
        print("📊 FINAL STATE AFTER SECOND PURCHASE")
        print("="*60)
        for warehouse in warehouses:
            warehouse.print_stock()
            print()
        
        for supplier in suppliers:
            supplier.print_stats()
            print()
    
    await asyncio.sleep(2)
    
    # Stop all agents
    for warehouse in warehouses:
        await warehouse.stop()
    for supplier in suppliers:
        await supplier.stop()
    
    print("✅ Simulation complete!")

if __name__ == "__main__":
    spade.run(main())