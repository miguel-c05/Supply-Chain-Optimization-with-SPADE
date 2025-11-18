"""
=================================
    BUY MATERIAL INTERACTION TEST
=================================

This test simulates the complete BuyMaterial protocol:
1. Warehouse sends buy request to all suppliers
2. Suppliers respond with accept/reject
3. Warehouse selects best supplier (by distance)
4. Warehouse sends confirmation to selected supplier
5. Warehouse sends denial to other suppliers
6. Supplier receives confirmation and adds to pending_deliveries
7. Supplier assigns vehicle for delivery
8. Vehicle receives proposal and responds
9. Supplier selects best vehicle
10. Vehicle picks up order from supplier
11. Vehicle delivers order to warehouse

All agents must be subscribed to each other:
- Vehicles subscribe to warehouses and suppliers
- Warehouses subscribe to suppliers and vehicles
- Suppliers subscribe to warehouses and vehicles
"""

import asyncio
import spade
from spade.behaviour import OneShotBehaviour
from spade.message import Message
from spade.template import Template
import json

from world.world import World
from warehouse import Warehouse
from supplier import Supplier
from veiculos.veiculos import Veiculo


async def main():
    print("\n" + "="*70)
    print("          TESTING BUY MATERIAL PROTOCOL")
    print("="*70 + "\n")
    
    # Create world
    world = World(width=3, height=3, warehouses=1, suppliers=2, stores=0, mode="uniform")
    graph = world.graph
    
    # Find nodes
    warehouse_node = None
    supplier_nodes = []
    
    for node_id, node in graph.nodes.items():
        if node.warehouse:
            warehouse_node = node_id
        if node.supplier:
            supplier_nodes.append(node_id)
    
    if not warehouse_node or len(supplier_nodes) < 2:
        print("ERROR: Need at least 1 warehouse and 2 suppliers!")
        return
    
    print(f"🏭 Warehouse at node: {warehouse_node}")
    print(f"🏪 Suppliers at nodes: {supplier_nodes}")
    
    # Create agents
    warehouse_jid = f"warehouse{warehouse_node}@localhost"
    supplier1_jid = f"supplier{supplier_nodes[0]}@localhost"
    supplier2_jid = f"supplier{supplier_nodes[1]}@localhost"
    vehicle1_jid = "vehicle1@localhost"
    vehicle2_jid = "vehicle2@localhost"
    
    warehouse = Warehouse(warehouse_jid, "pass", graph, warehouse_node)
    supplier1 = Supplier(supplier1_jid, "pass", graph, supplier_nodes[0])
    supplier2 = Supplier(supplier2_jid, "pass", graph, supplier_nodes[1])
    
    # Create vehicles
    vehicle1 = Veiculo(
        jid=vehicle1_jid,
        password="pass",
        max_fuel=1000,
        capacity=100,
        max_orders=5,
        map=graph,
        weight=1.0,
        current_location=supplier_nodes[0]  # Start at supplier1
    )
    
    vehicle2 = Veiculo(
        jid=vehicle2_jid,
        password="pass",
        max_fuel=1000,
        capacity=50,
        max_orders=5,
        map=graph,
        weight=1.0,
        current_location=supplier_nodes[1]  # Start at supplier2
    )
    
    # Start all agents
    print("\n🚀 Starting agents...")
    await vehicle1.start(auto_register=True)
    await vehicle2.start(auto_register=True)
    await warehouse.start(auto_register=True)
    await supplier1.start(auto_register=True)
    await supplier2.start(auto_register=True)
    
    print("✅ All agents started!")
    
    # Setup presence - IMPORTANT: Set available BEFORE subscribing
    warehouse.presence.set_available()
    warehouse.presence.approve_all = True
    
    supplier1.presence.set_available()
    supplier1.presence.approve_all = True
    
    supplier2.presence.set_available()
    supplier2.presence.approve_all = True
    
    vehicle1.presence.set_available()
    vehicle1.presence.approve_all = True
    
    vehicle2.presence.set_available()
    vehicle2.presence.approve_all = True
    
    await asyncio.sleep(2)
    
    # Subscribe agents to each other
    print("\n🔗 Setting up subscriptions...")
    
    # Warehouse subscribes to suppliers and vehicles
    warehouse.presence.subscribe(supplier1_jid)
    warehouse.presence.subscribe(supplier2_jid)
    warehouse.presence.subscribe(vehicle1_jid)
    warehouse.presence.subscribe(vehicle2_jid)
    warehouse.suppliers = [supplier1_jid, supplier2_jid]
    warehouse.vehicles = [vehicle1_jid, vehicle2_jid]
    
    # Supplier1 subscribes to warehouse and vehicles
    supplier1.presence.subscribe(warehouse_jid)
    supplier1.presence.subscribe(vehicle1_jid)
    supplier1.presence.subscribe(vehicle2_jid)
    supplier1.vehicles = [vehicle1_jid, vehicle2_jid]
    
    # Supplier2 subscribes to warehouse and vehicles
    supplier2.presence.subscribe(warehouse_jid)
    supplier2.presence.subscribe(vehicle1_jid)
    supplier2.presence.subscribe(vehicle2_jid)
    supplier2.vehicles = [vehicle1_jid, vehicle2_jid]
    
    # Vehicles subscribe to warehouse and suppliers
    vehicle1.presence.subscribe(warehouse_jid)
    vehicle1.presence.subscribe(supplier1_jid)
    vehicle1.presence.subscribe(supplier2_jid)
    
    vehicle2.presence.subscribe(warehouse_jid)
    vehicle2.presence.subscribe(supplier1_jid)
    vehicle2.presence.subscribe(supplier2_jid)
    
    # CRITICAL: Wait longer for presence information to propagate
    print("⏳ Waiting for presence information to propagate...")
    await asyncio.sleep(5)
    
    # Verify subscriptions
    print("\n🔍 Verifying subscriptions...")
    print(f"Supplier1 contacts: {list(supplier1.presence.contacts.keys())}")
    print(f"Supplier2 contacts: {list(supplier2.presence.contacts.keys())}")
    print(f"Vehicle1 contacts: {list(vehicle1.presence.contacts.keys())}")
    print(f"Vehicle2 contacts: {list(vehicle2.presence.contacts.keys())}")
    
    print("✅ All subscriptions complete!")
    
    # Print initial states
    print("\n" + "="*70)
    print("INITIAL STATE")
    print("="*70)
    
    print(f"\n📦 Warehouse initial stock:")
    warehouse.print_stock()
    
    print(f"\n🏪 Supplier1 stats:")
    supplier1.print_stats()
    
    print(f"\n🏪 Supplier2 stats:")
    supplier2.print_stats()
    
    # TEST 1: Warehouse buys material from suppliers
    print("\n" + "="*70)
    print("TEST 1: WAREHOUSE REQUESTS MATERIAL FROM SUPPLIERS")
    print("="*70)
    
    # Trigger warehouse to buy 50 units of product A
    buy_behav = warehouse.BuyMaterial(quantity=50, product="A")
    warehouse.add_behaviour(buy_behav)
    print(f"\n📤 {warehouse.jid} requesting 50 units of product A from all suppliers")
    
    # Wait for the buy behavior to complete
    await buy_behav.join()
    await asyncio.sleep(8)  # Wait for all supplier responses and selection
    
    print("\n📊 After supplier selection:")
    print(f"\nWarehouse pending orders: {len(warehouse.pending_orders)}")
    print(f"Supplier1 pending deliveries: {len(supplier1.pending_deliveries)}")
    print(f"Supplier2 pending deliveries: {len(supplier2.pending_deliveries)}")
    
    # Check which supplier was selected
    selected_supplier = None
    if supplier1.pending_deliveries:
        selected_supplier = supplier1
        print(f"\n✅ Supplier1 was selected!")
    elif supplier2.pending_deliveries:
        selected_supplier = supplier2
        print(f"\n✅ Supplier2 was selected!")
    else:
        print("\n❌ No supplier was selected!")
        await warehouse.stop()
        await supplier1.stop()
        await supplier2.stop()
        await vehicle1.stop()
        await vehicle2.stop()
        return
    
    # TEST 2: Selected supplier assigns vehicle
    print("\n" + "="*70)
    print("TEST 2: SUPPLIER ASSIGNS VEHICLE FOR DELIVERY")
    print("="*70)
    
    # Get the order_id from pending_deliveries
    order_id = list(selected_supplier.pending_deliveries.keys())[0]
    print(f"\n📦 Order ID: {order_id}")
    
    # NOTE: AssignVehicle is automatically triggered by ReceiveConfirmationOrDenial
    # No need to manually trigger it here
    print(f"\n📤 {selected_supplier.jid} automatically requesting vehicle proposals...")
    
    # Wait for vehicle proposals and selection
    await asyncio.sleep(5)  # Wait for vehicle proposals and selection
    
    print("\n📊 After vehicle assignment:")
    print(f"Vehicle1 orders: {len(vehicle1.orders)}")
    print(f"Vehicle2 orders: {len(vehicle2.orders)}")
    
    # TEST 3: Simulate vehicle pickup from supplier
    print("\n" + "="*70)
    print("TEST 3: VEHICLE PICKS UP ORDER FROM SUPPLIER")
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
                
                msg = Message(to=str(selected_supplier.jid))
                msg.set_metadata("performative", "vehicle-pickup")
                msg.set_metadata("supplier_id", str(selected_supplier.jid))
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
                print(f"\n📤 {selected_vehicle.jid} picking up order {order.orderid} from supplier")
        
        pickup_behav = SimulateVehiclePickup()
        selected_vehicle.add_behaviour(pickup_behav)
        await pickup_behav.join()
        await asyncio.sleep(2)
        
        print(f"\n📊 Supplier pending deliveries after pickup: {len(selected_supplier.pending_deliveries)}")
        if not selected_supplier.pending_deliveries:
            print("  ✅ Order successfully picked up by vehicle!")
    
    # TEST 4: Simulate vehicle delivery to warehouse
    print("\n" + "="*70)
    print("TEST 4: VEHICLE DELIVERS ORDER TO WAREHOUSE")
    print("="*70)
    
    if selected_vehicle:
        print(f"\n📦 Warehouse stock BEFORE delivery:")
        warehouse.print_stock()
        
        class SimulateVehicleDelivery(OneShotBehaviour):
            async def run(self):
                order = selected_vehicle.orders[0]
                
                msg = Message(to=str(warehouse.jid))
                msg.set_metadata("performative", "vehicle-delivery")
                msg.set_metadata("warehouse_id", str(warehouse.jid))
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
                print(f"\n📤 {selected_vehicle.jid} delivering order {order.orderid} to warehouse")
        
        delivery_behav = SimulateVehicleDelivery()
        selected_vehicle.add_behaviour(delivery_behav)
        await delivery_behav.join()
        await asyncio.sleep(2)
        
        print(f"\n📦 Warehouse stock AFTER delivery:")
        warehouse.print_stock()
    
    # FINAL STATE
    print("\n" + "="*70)
    print("📊 FINAL STATE")
    print("="*70)
    
    print(f"\n📦 Warehouse:")
    warehouse.print_stock()
    
    print(f"\n🏪 Supplier1:")
    supplier1.print_stats()
    
    print(f"\n🏪 Supplier2:")
    supplier2.print_stats()
    
    if selected_vehicle:
        print(f"\n🚚 Selected Vehicle ({selected_vehicle.jid}):")
        print(f"  Orders: {len(selected_vehicle.orders)}")
        print(f"  Current location: {selected_vehicle.current_location}")
        print(f"  Current load: {selected_vehicle.current_load}/{selected_vehicle.capacity}")
    
    # Stop all agents
    print("\n🛑 Stopping all agents...")
    await warehouse.stop()
    await supplier1.stop()
    await supplier2.stop()
    await vehicle1.stop()
    await vehicle2.stop()
    
    print("\n✅ BUY MATERIAL PROTOCOL TEST COMPLETED!")
    print("="*70 + "\n")


if __name__ == "__main__":
    spade.run(main())