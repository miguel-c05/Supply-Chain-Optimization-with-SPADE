# Message Protocols Documentation

This document details the message structures and operation sequences for all agent communication protocols in the Supply Chain Optimization system.

## Table of Contents
1. [Store ↔ Warehouse Protocol](#store--warehouse-protocol)
2. [Warehouse ↔ Supplier Protocol](#warehouse--supplier-protocol)

---

## Store ↔ Warehouse Protocol

### Overview
Three-way handshake protocol where stores request products from warehouses.

### Message Flow

```
Store                           Warehouse
  |                                 |
  |  1. store-buy (request)         |
  |-------------------------------->|
  |                                 |
  |                                 | (Lock stock)
  |                                 |
  |  2. warehouse-accept            |
  |<--------------------------------|
  |                                 |
  | (Update stock)                  |
  |                                 |
  |  3. store-confirm               |
  |-------------------------------->|
  |                                 |
  |                                 | (Update locked stock,
  |                                 |  add to pending_orders)
  |                                 |
```

### 1. `store-buy` (Request)

**Direction:** Store → Warehouse

**Metadata:**
```json
{
  "performative": "store-buy",
  "store_id": "store1@localhost",
  "request_id": "0"
}
```

**Body Format:**
```
"{quantity} {product}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "store-buy",
    "store_id": "store1@localhost",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Warehouse Action:**
- Check if product exists and quantity available
- If yes: Lock stock and send acceptance
- If no: Ignore (timeout on store side)

---

### 2. `warehouse-accept` (Acceptance)

**Direction:** Warehouse → Store

**Metadata:**
```json
{
  "performative": "warehouse-accept",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "request_id": "0"
}
```

**Body Format:**
```
"{quantity} {product}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "warehouse-accept",
    "warehouse_id": "warehouse1@localhost",
    "store_id": "store1@localhost",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Store Action:**
- Receive acceptance
- Update own stock (add received quantity)
- Send confirmation

---

### 3. `store-confirm` (Confirmation)

**Direction:** Store → Warehouse

**Metadata:**
```json
{
  "performative": "store-confirm",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "request_id": "0"
}
```

**Body Format:**
```
"{quantity} {product}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "store-confirm",
    "warehouse_id": "warehouse1@localhost",
    "store_id": "store1@localhost",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Warehouse Action:**
- Unlock stock (remove from locked_stock)
- Add to pending_orders for vehicle pickup

---

### Timeout Handling

**Store side (RecieveWarehouseAcceptance):**
- Timeout: 5 seconds
- Action: Add request to `failed_requests` queue

**Warehouse side (ReceiveConfirmation):**
- Timeout: 10 seconds
- Action: Return locked stock to available stock

---

## Warehouse ↔ Supplier Protocol

### Overview
Three-way handshake protocol where warehouses request materials from suppliers (infinite stock).

### Message Flow

```
Warehouse                       Supplier
  |                                 |
  |  1. warehouse-buy (request)     |
  |-------------------------------->|
  |                                 |
  |                                 | (Track supplied quantity)
  |                                 |
  |  2. supplier-accept             |
  |<--------------------------------|
  |                                 |
  | (Update stock)                  |
  |                                 |
  |  3. warehouse-confirm           |
  |-------------------------------->|
  |                                 |
  |                                 | (Add to pending_deliveries)
  |                                 |
```

### 1. `warehouse-buy` (Request)

**Direction:** Warehouse → Supplier

**Metadata:**
```json
{
  "performative": "warehouse-buy",
  "warehouse_id": "warehouse1@localhost",
  "request_id": "1"
}
```

**Body Format:**
```
"{quantity} {product}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "warehouse-buy",
    "warehouse_id": "warehouse1@localhost",
    "request_id": "1"
  },
  "body": "25 A"
}
```

**Supplier Action:**
- Always accept (infinite stock)
- Track total supplied quantity
- Send acceptance

---

### 2. `supplier-accept` (Acceptance)

**Direction:** Supplier → Warehouse

**Metadata:**
```json
{
  "performative": "supplier-accept",
  "supplier_id": "supplier1@localhost",
  "warehouse_id": "warehouse1@localhost",
  "request_id": "1"
}
```

**Body Format:**
```
"{quantity} {product}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "supplier-accept",
    "supplier_id": "supplier1@localhost",
    "warehouse_id": "warehouse1@localhost",
    "request_id": "1"
  },
  "body": "25 A"
}
```

**Warehouse Action:**
- Receive acceptance
- Update own stock (add received quantity)
- Send confirmation

---

### 3. `warehouse-confirm` (Confirmation)

**Direction:** Warehouse → Supplier

**Metadata:**
```json
{
  "performative": "warehouse-confirm",
  "supplier_id": "supplier1@localhost",
  "warehouse_id": "warehouse1@localhost",
  "request_id": "1"
}
```

**Body Format:**
```
"{quantity} {product}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "warehouse-confirm",
    "supplier_id": "supplier1@localhost",
    "warehouse_id": "warehouse1@localhost",
    "request_id": "1"
  },
  "body": "25 A"
}
```

**Supplier Action:**
- Add to pending_deliveries for vehicle pickup

---

### Timeout Handling

**Warehouse side (RecieveSupplierAcceptance):**
- Timeout: 5 seconds
- Action: Add request to `failed_requests` queue

**Supplier side (ReceiveWarehouseConfirmation):**
- Timeout: 10 seconds
- Action: Log order not confirmed (no rollback needed - infinite stock)

---

## Key Design Principles

### 1. **Unique Message Routing**
Each message includes multiple metadata keys to ensure race condition prevention:
- `performative`: Message type
- Agent IDs: Source and destination
- `request_id`: Unique identifier for each request

### 2. **Template Filtering**
Behaviours use multi-key templates to receive only their specific messages:
```python
template = Template()
template.set_metadata("performative", "warehouse-accept")
template.set_metadata("store_id", str(agent.jid))
template.set_metadata("request_id", str(request_id))
```

### 3. **Request Counter Management**
- Counter incremented **BEFORE** sending message
- Ensures template matches sent metadata

### 4. **Body Format Consistency**
All messages use: `"{quantity} {product}"`
- No redundant data (request_id only in metadata)
- Easy parsing with `split(" ")`

### 5. **Timeout Strategies**
- Shorter timeouts for critical operations (5s for acceptances)
- Longer timeouts for confirmations (10s)
- Failed requests queued for retry

---

## Complete Operation Sequences

### Store Purchase (Successful)

1. **Store.BuyProduct(5, "A")**
   - Increment request_counter
   - Send `store-buy` to all warehouse contacts
   - Add RecieveWarehouseAcceptance behaviour with template

2. **Warehouse.ReceiveBuyRequest**
   - Receive `store-buy`
   - Check stock availability
   - Lock 5 units of A (stock -= 5, locked_stock += 5)
   - Add AcceptBuyRequest behaviour

3. **Warehouse.AcceptBuyRequest**
   - Send `warehouse-accept`
   - Add ReceiveConfirmation behaviour with template

4. **Store.RecieveWarehouseAcceptance**
   - Receive `warehouse-accept` within 5s
   - Update stock (stock[A] += 5)
   - Add SendStoreConfirmation behaviour

5. **Store.SendStoreConfirmation**
   - Send `store-confirm`

6. **Warehouse.ReceiveConfirmation**
   - Receive `store-confirm` within 10s
   - Update locked_stock (locked_stock[A] -= 5)
   - Add to pending_orders[store_jid]

### Warehouse Purchase from Supplier (Successful)

1. **Warehouse.BuyMaterial(25, "A")**
   - Increment request_counter
   - Send `warehouse-buy` to all supplier contacts
   - Add RecieveSupplierAcceptance behaviour with template

2. **Supplier.ReceiveBuyRequest**
   - Receive `warehouse-buy`
   - Always accept (infinite stock)
   - Track supplied quantity (total_supplied[A] += 25)
   - Add AcceptBuyRequest behaviour

3. **Supplier.AcceptBuyRequest**
   - Send `supplier-accept`
   - Add ReceiveWarehouseConfirmation behaviour with template

4. **Warehouse.RecieveSupplierAcceptance**
   - Receive `supplier-accept` within 5s
   - Update stock (stock[A] += 25)
   - Add SendWarehouseConfirmation behaviour

5. **Warehouse.SendWarehouseConfirmation**
   - Send `warehouse-confirm`

6. **Supplier.ReceiveWarehouseConfirmation**
   - Receive `warehouse-confirm` within 10s
   - Add to pending_deliveries[warehouse_jid]

---

## Error Handling

### Failed Store Purchase
- **Cause:** Warehouse timeout (no acceptance in 5s)
- **Effect:** Request added to `store.failed_requests` queue
- **Recovery:** Use `Store.RetryPreviousBuy()` behaviour

### Failed Warehouse Purchase
- **Cause:** Supplier timeout (no acceptance in 5s)
- **Effect:** Request added to `warehouse.failed_requests` queue
- **Recovery:** Use `Warehouse.RetryPreviousBuy()` behaviour

### Unconfirmed Store Order
- **Cause:** Store doesn't send confirmation within 10s
- **Effect:** Warehouse unlocks stock, order cancelled
- **Recovery:** Store must retry from beginning

### Unconfirmed Warehouse Order
- **Cause:** Warehouse doesn't send confirmation within 10s
- **Effect:** Supplier logs unconfirmed order (no rollback)
- **Recovery:** Warehouse must retry from beginning

---

## Implementation Notes

### Race Condition Prevention
Multi-key metadata ensures each behaviour receives only its messages:
```python
# Example: Two simultaneous requests
# Request 1: request_id="0"
# Request 2: request_id="1"

# Each RecieveWarehouseAcceptance filters by its own request_id
template.set_metadata("request_id", "0")  # Only receives messages with request_id="0"
```

### Stock Management
**Warehouse:**
- `stock`: Available (unlocked) inventory
- `locked_stock`: Reserved during transactions
- `pending_orders`: Confirmed orders awaiting pickup

**Supplier:**
- No stock tracking (infinite)
- `total_supplied`: Statistics
- `pending_deliveries`: Confirmed deliveries awaiting pickup

---

**Last Updated:** November 8, 2025
