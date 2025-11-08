import spade
import asyncio
from warehouse import Warehouse
from supplier import Supplier

async def main():
    # Create supplier and warehouse agents
    supplier1 = Supplier("supplier1@localhost", "pass", 1)
    warehouse1 = Warehouse("warehouse1@localhost", "pass", 1)
    
    # Start agents
    await supplier1.start(auto_register=True)
    await warehouse1.start(auto_register=True)
    
    print("✅ Agents started successfully!\n")
    
    # Setup presence (warehouse subscribes to supplier)
    await asyncio.sleep(1)
    warehouse1.presence.subscribe("supplier1@localhost")
    supplier1.presence.approve_all = True
    
    await asyncio.sleep(1)
    print("✅ Presence configured\n")
    
    # Display initial state
    print("="*60)
    print("📊 INITIAL STATE")
    print("="*60)
    warehouse1.print_stock()
    supplier1.print_stats()
    
    # Simulate warehouse buying from supplier using BuyMaterial behaviour
    await asyncio.sleep(2)
    
    print("\n" + "="*60)
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
    print("� SECOND PURCHASE: 50 units of B")
    print("="*60)
    
    buy_behav2 = warehouse1.BuyMaterial(50, "B")
    warehouse1.add_behaviour(buy_behav2)
    await buy_behav2.join()
    await asyncio.sleep(3)
    
    print("\n" + "="*60)
    print("📊 FINAL STATE AFTER SECOND PURCHASE")
    print("="*60)
    warehouse1.print_stock()
    supplier1.print_stats()
    
    await asyncio.sleep(2)
    
    # Stop agents
    await warehouse1.stop()
    await supplier1.stop()
    
    print("\n✅ Simulation complete!")

if __name__ == "__main__":
    spade.run(main())
