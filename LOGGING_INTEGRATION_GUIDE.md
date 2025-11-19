# Logging Integration Guide

This guide explains where and how to integrate the logging system into all agent files.

## Quick Start

The logging system has been initialized in `simulate.py`. All loggers are singletons and can be accessed via:

```python
from logger_utils import MessageLogger, RouteCalculationLogger, VehicleMetricsLogger, InventoryLogger, OrderLifecycleLogger

# Get logger instances
msg_logger = MessageLogger.get_instance()
route_logger = RouteCalculationLogger.get_instance()
vehicle_logger = VehicleMetricsLogger.get_instance()
inventory_logger = InventoryLogger.get_instance()
order_logger = OrderLifecycleLogger.get_instance()
```

## Integration Points by File

### 1. `veiculos/veiculos.py` (Vehicle Agent)

#### A. Import statements (after line 64)

```python
from logger_utils import MessageLogger, RouteCalculationLogger, VehicleMetricsLogger, OrderLifecycleLogger
import time
```

#### B. Message logging - Add after EVERY `await self.send(msg)`:

```python
# Example from ReceiveOrdersBehaviour (around line 543)
await self.send(proposal_msg)

# ADD THIS:
msg_logger = MessageLogger.get_instance()
msg_logger.log_message(
    sender=str(self.agent.jid),
    receiver=str(msg.sender),
    message_type="vehicle-proposal",
    performative="vehicle-proposal",
    body=proposal_msg.body
)
```

#### C. Route calculation logging - Add BEFORE AND AFTER each `A_star_task_algorithm` call:

```python
# Example from can_fit_in_current_route (around line 761)
# BEFORE A*:
start_time = time.time()

route, total_time, _ = A_star_task_algorithm(
    self.agent.map,
    final_location,
    future_orders,
    self.agent.capacity,
    self.agent.max_fuel
)

# AFTER A*:
computation_time = (time.time() - start_time) * 1000  # Convert to ms
route_logger = RouteCalculationLogger.get_instance()
route_logger.log_calculation(
    vehicle_jid=str(self.agent.jid),
    algorithm="astar",
    num_orders=len(future_orders),
    computation_time_ms=computation_time,
    route_length=len(route) if route else 0,
    total_distance=total_time,
    route_nodes=str([node_id for node_id, _ in route]) if route else "[]"
)
```

#### D. Vehicle state logging - Add after significant state changes:

```python
# Example: After accepting an order (around line 820)
vehicle_logger = VehicleMetricsLogger.get_instance()
vehicle_logger.log_vehicle_state(
    vehicle_jid=str(self.agent.jid),
    current_fuel=self.agent.current_fuel,
    current_load=self.agent.current_load,
    current_location=self.agent.current_location,
    next_node=self.agent.next_node,
    num_active_orders=len(self.agent.orders),
    num_pending_orders=len(self.agent.pending_orders),
    status="order_accepted"
)
```

**Locations to add A\* logging in `veiculos.py`:**

- Line ~218: `Order.time_to_deliver()` - algorithm="astar" (initial order time calculation)
- Line ~637: `ReceiveOrdersBehaviour.can_fit_in_current_route()` - algorithm="astar"
- Line ~761: `ReceiveOrdersBehaviour.calculate_future_delivery_time()` - algorithm="astar"
- Line ~904: `WaitConfirmationBehaviour` - algorithm="astar" (route recalculation)
- Line ~1110: `MovementBehaviour` - algorithm="astar" (traffic recalculation)

### 2. `store.py` (Store Agent)

#### A. Import statements (after line 40)

```python
from logger_utils import MessageLogger, InventoryLogger, OrderLifecycleLogger
```

#### B. Message logging - Add after each message send:

```python
# Example from BuyProduct (around line 260)
await self.send(buy_msg)

# ADD THIS:
msg_logger = MessageLogger.get_instance()
msg_logger.log_message(
    sender=str(self.agent.jid),
    receiver=str(contact),
    message_type="store-buy",
    timestamp_sim=self.agent.current_tick,
    performative=buy_msg.get_metadata("performative"),
    body=buy_msg.body
)
```

#### C. Order lifecycle logging:

```python
# When creating order (around line 240)
order_logger = OrderLifecycleLogger.get_instance()
order_logger.log_order_event(
    order_id=request_id,
    sender=str(self.agent.jid),
    receiver="broadcast",
    product=product,
    quantity=quantity,
    event_type="created",
    timestamp_sim=self.agent.current_tick
)
```

#### D. Inventory logging - Add when stock changes:

```python
# Example from ReceiveVehicleArrival (around line 1600)
# BEFORE stock update:
stock_before = self.agent.stock.get(product, 0)

# Update stock
self.agent.stock[product] = self.agent.stock.get(product, 0) + quantity

# AFTER stock update:
inventory_logger = InventoryLogger.get_instance()
inventory_logger.log_inventory_change(
    agent_jid=str(self.agent.jid),
    agent_type="store",
    product=product,
    change_type="delivery",
    quantity=quantity,
    stock_before=stock_before,
    stock_after=self.agent.stock[product],
    timestamp_sim=self.agent.current_tick
)
```

**Key locations in `store.py`:**

- Line ~260: BuyProduct sends store-buy
- Line ~480: SendStoreConfirmation sends store-confirm
- Line ~560: SendStoreDenial sends store-deny
- Line ~1600: ReceiveVehicleArrival updates stock

### 3. `warehouse.py` (Warehouse Agent)

#### A. Import statements (after line 42)

```python
from logger_utils import MessageLogger, InventoryLogger, OrderLifecycleLogger
```

#### B. Message logging locations:

- Line ~350: AcceptBuyRequest sends warehouse-accept
- Line ~520: RejectBuyRequest sends warehouse-reject
- Line ~1200: BuyMaterial sends warehouse-buy (to supplier)
- Line ~1515: SendWarehouseConfirmation (to supplier)
- Line ~1550: SendWarehouseDenial (to supplier)

#### C. Inventory logging locations:

- Line ~640: ReceiveConfirmationOrDenial locks stock
- Line ~1680: ReceiveVehicleArrival updates stock (delivery from supplier)
- Line ~1685: ReceiveVehicleArrival reduces stock (pickup by vehicle)

**Example for warehouse-accept:**

```python
# Line ~370
await self.send(accept_msg)

msg_logger = MessageLogger.get_instance()
msg_logger.log_message(
    sender=str(self.agent.jid),
    receiver=str(msg.sender),
    message_type="warehouse-accept",
    timestamp_sim=self.agent.current_tick,
    performative="warehouse-accept",
    body=accept_msg.body
)
```

### 4. `supplier.py` (Supplier Agent)

#### A. Import statements (after line 48)

```python
from logger_utils import MessageLogger, OrderLifecycleLogger
```

#### B. Message logging locations:

- Line ~340: AcceptBuyRequest sends supplier-accept
- Line ~1080: ChooseBestVehicle sends order-confirmation (to vehicle)

**Example:**

```python
# Line ~340
await self.send(accept_msg)

msg_logger = MessageLogger.get_instance()
msg_logger.log_message(
    sender=str(self.agent.jid),
    receiver=str(msg.sender),
    message_type="supplier-accept",
    timestamp_sim=self.agent.current_tick,
    performative="supplier-accept",
    body=accept_msg.body
)
```

### 5. `Eventos/event_agent.py` (Event Agent)

#### A. Import statements (after line 65)

```python
from logger_utils import MessageLogger
```

#### B. Message logging locations:

- Line ~550: ProcessEventsBehaviour sends arrival events
- Line ~620: ProcessEventsBehaviour sends transit events
- Line ~720: SimulateTrafficBehaviour sends time updates

### 6. `world_agent.py` (World Agent)

#### A. Import statements (after line 10)

```python
from logger_utils import MessageLogger
```

#### B. Message logging locations:

- Line ~120: TimeDeltaBehaviour sends traffic events
- Line ~170: TimeDeltaBehaviour sends time-delta responses
- Line ~320: \_handle_world_state_query sends world state
- Line ~380: \_handle_node_query sends node info
- Line ~470: \_handle_edge_query sends edge info
- Line ~540: \_handle_facilities_query sends facilities info

## Complete Integration Template

Here's a complete template for adding to any message send:

```python
# 1. Send the message
await self.send(message)

# 2. Log the message
try:
    msg_logger = MessageLogger.get_instance()
    msg_logger.log_message(
        sender=str(self.agent.jid),  # or self.jid for non-behaviour methods
        receiver=str(message.to),
        message_type=message.get_metadata("performative") or "unknown",
        timestamp_sim=getattr(self.agent, 'current_tick', None),
        performative=message.get_metadata("performative") or "",
        body=message.body[:100],  # First 100 chars
        metadata=str(message.metadata) if hasattr(message, 'metadata') else ""
    )
except Exception as e:
    # Don't let logging errors crash the agent
    print(f"[LOGGING ERROR] {e}")
```

## Testing

After integration, check that log files are created in `logs/<timestamp>/`:

- `messages.csv` - All inter-agent messages
- `route_calculations.csv` - All A\* algorithm calls
- `vehicle_metrics.csv` - Vehicle state snapshots
- `inventory_changes.csv` - Stock level changes
- `order_lifecycle.csv` - Order tracking from creation to delivery

## Analysis Scripts

After collecting logs, you can analyze them with:

```python
import pandas as pd

# Load logs
messages = pd.read_csv('logs/<timestamp>/messages.csv')
routes = pd.read_csv('logs/<timestamp>/route_calculations.csv')

# Count messages by type
print(messages['message_type'].value_counts())

# Count route calculations by algorithm
print(routes['algorithm'].value_counts())

# Average computation time
print(f"Avg A* time: {routes['computation_time_ms'].mean():.2f}ms")
```

## Notes

- All loggers are thread-safe singletons
- Logging failures won't crash agents (use try-except)
- New log directory created for each simulation run
- CSV files can be opened in Excel or processed with pandas
