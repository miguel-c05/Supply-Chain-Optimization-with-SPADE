"""
=================================
    BUY PRODUCT INTERACTION TEST
=================================

This test simulates the complete BuyProduct protocol:
1. Store sends buy request to all warehouses
2. Warehouses respond with accept/reject
3. Store selects best warehouse (by distance)
4. Store sends confirmation to selected warehouse
5. Store sends denial to other warehouses
6. Warehouse receives confirmation and adds to pending_orders
7. Warehouse assigns vehicle for delivery
8. Vehicle receives proposal and responds
9. Warehouse selects best vehicle
10. Vehicle picks up order from warehouse
11. Vehicle delivers order to store

All agents must be subscribed to each other:
- Vehicles subscribe to warehouses and stores
- Warehouses subscribe to stores and vehicles
- Stores subscribe to warehouses
"""

import asyncio
import spade
from spade.behaviour import OneShotBehaviour
from spade.message import Message
from spade.template import Template
import json
import config
from world.world import World
from warehouse import Warehouse
from store import Store
from veiculos.veiculos import Veiculo


async def main():
    print("\n" + "="*70)
    print("          TESTING BUY PRODUCT PROTOCOL")
    print("="*70 + "\n")
    
    # Create world
    w = World(width=8,
        height=8,
        mode="different", 
        max_cost=4, 
        gas_stations=2, 
        warehouses=2,
        suppliers=1, 
        stores=2, 
        highway=False,
        traffic_probability=0.3,
        traffic_spread_probability=0.7,
        traffic_interval=3,
        untraffic_probability=0.4
        )
    graph = w.graph
    w.plot_graph()
    
    # Find nodes
    warehouse_nodes = []
    store_node = None
    
    for node_id, node in graph.nodes.items():
        if node.warehouse:
            warehouse_nodes.append(node_id)
        if node.store and store_node is None:
            store_node = node_id
    
    if len(warehouse_nodes) < 2 or not store_node:
        print("ERROR: Need at least 2 warehouses and 1 store!")
        return
    
    print(f"🏭 Warehouses at nodes: {warehouse_nodes}")
    print(f"🏪 Store at node: {store_node}")
    
    # Create agents
    warehouse1_jid = f"warehouse{warehouse_nodes[0]}@localhost"
    warehouse2_jid = f"warehouse{warehouse_nodes[1]}@localhost"
    store_jid = f"store{store_node}@localhost"
    vehicle1_jid = "vehicle1@localhost"
    vehicle2_jid = "vehicle2@localhost"
    
    warehouse1 = Warehouse(warehouse1_jid, "pass", graph, warehouse_nodes[0])
    warehouse2 = Warehouse(warehouse2_jid, "pass", graph, warehouse_nodes[1])
    store = Store(store_jid, "pass", graph, store_node)
    
    # Create vehicles
    vehicle1 = Veiculo(
        jid=vehicle1_jid,
        password="pass",
        max_fuel=1000,
        capacity=config.VEHICLE_CAPACITY,
        max_orders=5,
        map=graph,
        weight=1500,
        current_location=1,  # Start at node 1
        event_agent_jid=None  # No event agent in this test
    )
    
    vehicle2 = Veiculo(
        jid=vehicle2_jid,
        password="pass",
        max_fuel=1000,
        capacity=config.VEHICLE_CAPACITY,
        max_orders=5,
        map=graph,
        weight=1500,
        current_location=1,  # Start at node 1
        event_agent_jid=None  # No event agent in this test
    )
    
    # Start all agents
    print("\n🚀 Starting agents...")
    await vehicle1.start(auto_register=True)
    await vehicle2.start(auto_register=True)
    await warehouse1.start(auto_register=True)
    await warehouse2.start(auto_register=True)
    await store.start(auto_register=True)
    
    print("✅ All agents started!")
    
    # Setup presence - IMPORTANT: Set available BEFORE subscribing
    warehouse1.presence.set_available()
    warehouse1.presence.approve_all = True
    
    warehouse2.presence.set_available()
    warehouse2.presence.approve_all = True
    
    store.presence.set_available()
    store.presence.approve_all = True
    
    vehicle1.presence.set_available()
    vehicle1.presence.approve_all = True
    
    vehicle2.presence.set_available()
    vehicle2.presence.approve_all = True
    
    await asyncio.sleep(2)
    
    # Subscribe agents to each other
    print("\n🔗 Setting up subscriptions...")
    
    # Store subscribes to warehouses
    store.presence.subscribe(warehouse1_jid)
    store.presence.subscribe(warehouse2_jid)
    
    # Warehouse1 subscribes to store and vehicles
    warehouse1.presence.subscribe(store_jid)
    warehouse1.presence.subscribe(vehicle1_jid)
    warehouse1.presence.subscribe(vehicle2_jid)
    warehouse1.vehicles = [vehicle1_jid, vehicle2_jid]
    
    # Warehouse2 subscribes to store and vehicles
    warehouse2.presence.subscribe(store_jid)
    warehouse2.presence.subscribe(vehicle1_jid)
    warehouse2.presence.subscribe(vehicle2_jid)
    warehouse2.vehicles = [vehicle1_jid, vehicle2_jid]
    
    # Vehicles subscribe to warehouses and store
    vehicle1.presence.subscribe(warehouse1_jid)
    vehicle1.presence.subscribe(warehouse2_jid)
    vehicle1.presence.subscribe(store_jid)
    
    vehicle2.presence.subscribe(warehouse1_jid)
    vehicle2.presence.subscribe(warehouse2_jid)
    vehicle2.presence.subscribe(store_jid)
    
    # CRITICAL: Wait longer for presence information to propagate
    print("⏳ Waiting for presence information to propagate...")
    await asyncio.sleep(5)
    
    # Verify subscriptions
    print("\n🔍 Verifying subscriptions...")
    print(f"Store contacts: {list(store.presence.contacts.keys())}")
    print(f"Warehouse1 contacts: {list(warehouse1.presence.contacts.keys())}")
    print(f"Warehouse2 contacts: {list(warehouse2.presence.contacts.keys())}")
    print(f"Vehicle1 contacts: {list(vehicle1.presence.contacts.keys())}")
    print(f"Vehicle2 contacts: {list(vehicle2.presence.contacts.keys())}")
    
    print("✅ All subscriptions complete!")
    
    # Print initial states
    print("\n" + "="*70)
    print("INITIAL STATE")
    print("="*70)
    
    print(f"\n🏪 Store initial stock:")
    print(f"  Stock: {store.stock}")
    
    print(f"\n📦 Warehouse1 initial stock:")
    warehouse1.print_stock()
    
    print(f"\n📦 Warehouse2 initial stock:")
    warehouse2.print_stock()
    
    # TEST 1: Store buys product from warehouses
    print("\n" + "="*70)
    print("TEST 1: STORE REQUESTS PRODUCT FROM WAREHOUSES")
    print("="*70)
    
    # Trigger store to buy 10 units of product A
    buy_behav = store.BuyProduct(quantity=10, product="A")
    store.add_behaviour(buy_behav)
    print(f"\n📤 {store.jid} requesting 10 units of product A from all warehouses")
    
    # Wait for the buy behavior to complete
    await buy_behav.join()
    await asyncio.sleep(8)  # Wait for all warehouse responses and selection
    
    print("\n📊 After warehouse selection:")
    print(f"\nStore stock: {store.stock}")
    print(f"Warehouse1 pending orders: {len(warehouse1.pending_orders)}")
    print(f"Warehouse2 pending orders: {len(warehouse2.pending_orders)}")
    
    # Check which warehouse was selected
    selected_warehouse = None
    if warehouse1.pending_orders:
        selected_warehouse = warehouse1
        print(f"\n✅ Warehouse1 was selected!")
    elif warehouse2.pending_orders:
        selected_warehouse = warehouse2
        print(f"\n✅ Warehouse2 was selected!")
    else:
        print("\n❌ No warehouse was selected!")
        await warehouse1.stop()
        await warehouse2.stop()
        await store.stop()
        await vehicle1.stop()
        await vehicle2.stop()
        return
    
    #====================================================================
    # TEST 2: Selected warehouse assigns vehicle
    #====================================================================
    
    print("\n" + "="*70)
    print("TEST 2: WAREHOUSE ASSIGNS VEHICLE FOR DELIVERY")
    print("="*70)
    
    # Get the order_id from pending_orders
    order_id = list(selected_warehouse.pending_orders.keys())[0]
    print(f"\n📦 Order ID: {order_id}")
    
    # NOTE: AssignVehicle is automatically triggered by ReceiveConfirmationOrDenial
    # No need to manually trigger it here
    print(f"\n📤 {selected_warehouse.jid} automatically requesting vehicle proposals...")
    
    # Wait for vehicle proposals and selection
    await asyncio.sleep(5)  # Wait for vehicle proposals and selection
    
    print("\n📊 After vehicle assignment:")
    print(f"Vehicle1 orders: {len(vehicle1.orders)}")
    print(f"Vehicle2 orders: {len(vehicle2.orders)}")
    
    # TEST 3: Simulate vehicle pickup from warehouse
    print("\n" + "="*70)
    print("TEST 3: VEHICLE PICKS UP ORDER FROM WAREHOUSE")
    print("="*70)
    
    # Determine which vehicle was selected
    selected_vehicle = None
    if vehicle1.orders:
        selected_vehicle = vehicle1
        print(f"\n✅ Vehicle1 was selected!")
    elif vehicle2.orders:
        selected_vehicle = vehicle2
        print(f"\n✅ Vehicle2 was selected!")
    else:
        print("\n⚠️ No vehicle was assigned yet")
    
    if selected_vehicle:
        class SimulateVehiclePickup(OneShotBehaviour):
            async def run(self):
                order = selected_vehicle.orders[0]
                
                msg = Message(to=str(selected_warehouse.jid))
                msg.set_metadata("performative", "vehicle-pickup")
                msg.set_metadata("warehouse_id", str(selected_warehouse.jid))
                msg.set_metadata("vehicle_id", str(selected_vehicle.jid))
                msg.set_metadata("order_id", str(order.orderid))
                
                order_dict = {
                    "product": order.product,
                    "quantity": order.quantity,
                    "orderid": order.orderid,
                    "sender": order.sender,
                    "receiver": order.receiver,
                    "sender_location": order.sender_location,
                    "receiver_location": order.receiver_location
                }
                
                msg.body = json.dumps(order_dict)
                await self.send(msg)
                print(f"\n📤 Vehicle sent pickup confirmation to warehouse")
        
        pickup_behav = SimulateVehiclePickup()
        selected_vehicle.add_behaviour(pickup_behav)
        await pickup_behav.join()
        await asyncio.sleep(2)
        
        print(f"\n📊 Warehouse pending orders after pickup: {len(selected_warehouse.pending_orders)}")
        if not selected_warehouse.pending_orders:
            print("  ✅ Order successfully picked up by vehicle!")
        
        print(f"\n📊 Warehouse stock after pickup:")
        selected_warehouse.print_stock()
    
    # TEST 4: Simulate vehicle delivery to store
    print("\n" + "="*70)
    print("TEST 4: VEHICLE DELIVERS ORDER TO STORE")
    print("="*70)
    
    if selected_vehicle:
        print(f"\n📦 Store stock BEFORE delivery:")
        print(f"  Stock: {store.stock}")
        
        class SimulateVehicleDelivery(OneShotBehaviour):
            async def run(self):
                order = selected_vehicle.orders[0]
                
                msg = Message(to=str(store.jid))
                msg.set_metadata("performative", "vehicle-delivery")
                msg.set_metadata("store_id", str(store.jid))
                msg.set_metadata("vehicle_id", str(selected_vehicle.jid))
                msg.set_metadata("order_id", str(order.orderid))
                
                order_dict = {
                    "product": order.product,
                    "quantity": order.quantity,
                    "orderid": order.orderid,
                    "sender": order.sender,
                    "receiver": order.receiver,
                    "sender_location": order.sender_location,
                    "receiver_location": order.receiver_location
                }
                
                msg.body = json.dumps(order_dict)
                await self.send(msg)
                print(f"\n📤 Vehicle sent delivery confirmation to store")
        
        delivery_behav = SimulateVehicleDelivery()
        selected_vehicle.add_behaviour(delivery_behav)
        await delivery_behav.join()
        await asyncio.sleep(2)
        
        print(f"\n📦 Store stock AFTER delivery:")
        print(f"  Stock: {store.stock}")
    
    # FINAL STATE
    print("\n" + "="*70)
    print("📊 FINAL STATE")
    print("="*70)
    
    print(f"\n🏪 Store:")
    print(f"  Stock: {store.stock}")
    
    print(f"\n📦 Warehouse1:")
    warehouse1.print_stock()
    
    print(f"\n📦 Warehouse2:")
    warehouse2.print_stock()
    
    if selected_vehicle:
        print(f"\n🚚 Selected Vehicle ({selected_vehicle.jid}):")
        print(f"  Orders: {len(selected_vehicle.orders)}")
        print(f"  Current location: {selected_vehicle.current_location}")
        print(f"  Current load: {selected_vehicle.current_load}/{selected_vehicle.capacity}")
    
    # Stop all agents
    print("\n🛑 Stopping all agents...")
    await warehouse1.stop()
    await warehouse2.stop()
    await store.stop()
    await vehicle1.stop()
    await vehicle2.stop()
    
    print("\n✅ BUY PRODUCT PROTOCOL TEST COMPLETED!")
    print("="*70 + "\n")


if __name__ == "__main__":
    spade.run(main())
