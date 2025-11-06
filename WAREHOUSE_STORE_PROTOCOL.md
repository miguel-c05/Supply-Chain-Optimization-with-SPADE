# Warehouse-Store Communication Protocol

## Overview

This document describes the message-based communication protocol between **Store** and **Warehouse** agents in the SPADE multi-agent system for supply chain optimization.

---

## Message Flow

The protocol follows a 3-step handshake pattern:

```
Store → Warehouse: store-buy (request)
Store ← Warehouse: warehouse-accept (acceptance)
Store → Warehouse: store-confirm (confirmation)
```

---

## Message Types

### 1. `store-buy` (Store → Warehouse)

**Purpose:** Store requests to buy products from a warehouse.

**Metadata Template:**
```json
{
  "performative": "store-buy",
  "store_id": "store1@localhost",
  "request_id": "42"
}
```

**Body Format:** `"{quantity} {product}"`

**Example:**
```json
{
  "to": "warehouse1@localhost",
  "metadata": {
    "performative": "store-buy",
    "store_id": "store1@localhost",
    "request_id": "42"
  },
  "body": "10 A"
}
```

**Semantics:**
- `request_id`: Unique identifier for this request (in metadata, scoped to the store)
- `quantity`: Number of units requested
- `product`: Product type (e.g., "A", "B", "C")

---

### 2. `warehouse-accept` (Warehouse → Store)

**Purpose:** Warehouse confirms it can fulfill the request and locks the stock.

**Metadata Template:**
```json
{
  "performative": "warehouse-accept",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "request_id": "42"
}
```

**Body Format:** `"{quantity} {product}"` (echoes the original request)

**Example:**
```json
{
  "to": "store1@localhost",
  "metadata": {
    "performative": "warehouse-accept",
    "warehouse_id": "warehouse1@localhost",
    "store_id": "store1@localhost",
    "request_id": "42"
  },
  "body": "10 A"
}
```

**Semantics:**
- Warehouse locks the requested quantity in `locked_stock`
- Stock is reserved but not yet removed from inventory
- Awaits final confirmation from store

---

### 3. `store-confirm` (Store → Warehouse)

**Purpose:** Store confirms the purchase and finalizes the transaction.

**Metadata Template:**
```json
{
  "performative": "store-confirm",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "request_id": "42"
}
```

**Body Format:** `"{quantity} {product}"` (echoes the acceptance)

**Example:**
```json
{
  "to": "warehouse1@localhost",
  "metadata": {
    "performative": "store-confirm",
    "warehouse_id": "warehouse1@localhost",
    "store_id": "store1@localhost",
    "request_id": "42"
  },
  "body": "10 A"
}
```

**Semantics:**
- Warehouse moves items from `locked_stock` to `pending_orders[store_id]`
- Store adds items to its `stock`
- Transaction is complete; items await vehicle pickup

---

## Metadata Key Explanation

| Key | Description | Scope |
|-----|-------------|-------|
| `performative` | Message type identifier | All messages |
| `store_id` | JID of the store agent | All messages |
| `warehouse_id` | JID of the warehouse agent | `warehouse-accept`, `store-confirm` |
| `request_id` | Unique request identifier | All messages |

**Important:** The combination of `(store_id, request_id)` is **globally unique** across the system, preventing ID collisions when multiple stores send requests simultaneously.

---

## Template Filtering

Behaviours use SPADE templates to filter incoming messages by multiple metadata keys:

```python
# Example: Warehouse waiting for confirmation of request #42 from store1
template = Template()
template.set_metadata("performative", "store-confirm")
template.set_metadata("warehouse_id", "warehouse1@localhost")
template.set_metadata("store_id", "store1@localhost")
template.set_metadata("request_id", "42")
```

This ensures:
- ✅ **No race conditions** between concurrent requests
- ✅ **Exact message routing** to the correct behaviour
- ✅ **Clean separation** of different transactions

---

## Error Handling

### Timeout (No Acceptance)

If warehouse cannot fulfill the request:
- No `warehouse-accept` is sent
- Store's `RecieveAcceptance` times out (default: 5s)
- Request remains in `active_requests` for retry

### Timeout (No Confirmation)

If store does not confirm:
- Warehouse's `ReceiveConfirmation` times out (default: 10s)
- Locked stock is **released** back to available stock
- Transaction is rolled back

---

## State Transitions

### Warehouse Stock States

1. **Unlocked** (`stock[product]`): Available for new requests
2. **Locked** (`locked_stock[product]`): Reserved, awaiting confirmation
3. **Pending** (`pending_orders[store_id][product]`): Confirmed, awaiting vehicle pickup

### Store Stock States

1. **Requested** (`active_requests[request_id]`): Request sent, awaiting acceptance
2. **In Stock** (`stock[product]`): Confirmed and available for use

---

## Concurrency Notes

- Multiple stores can send requests to the same warehouse concurrently
- Each request is processed sequentially by `ReceiveBuyRequest` (CyclicBehaviour)
- Template filtering ensures confirmations match the correct request
- Stock locking prevents double-allocation of inventory

---

## Example Full Transaction

```
T0: Store1 sends store-buy (metadata: id=10, body: "5 A")
T1: Warehouse1 locks 5 units of A
T2: Warehouse1 sends warehouse-accept (metadata: id=10, body: "5 A")
T3: Store1 receives acceptance
T4: Store1 adds 5 units of A to stock
T5: Store1 sends store-confirm (metadata: id=10, body: "5 A")
T6: Warehouse1 receives confirmation
T7: Warehouse1 moves 5 units of A to pending_orders[Store1]
T8: Warehouse1 unlocks 5 units (locked_stock[A] -= 5)
T9: Transaction complete
```

---

## Future Extensions

Possible additions to the protocol:
- `warehouse-reject`: Explicit rejection when stock is insufficient
- `store-cancel`: Cancel a pending request before confirmation
- `priority` metadata: Priority levels for urgent orders
- `timestamp` metadata: Request time for aging/expiry logic
- `partial-accept`: Warehouse offers partial quantity when full amount unavailable
