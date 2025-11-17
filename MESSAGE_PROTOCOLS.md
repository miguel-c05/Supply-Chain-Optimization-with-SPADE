# Message Protocols Documentation

This document details the message structures and operation sequences for all agent communication protocols in the Supply Chain Optimization system.

## Table of Contents
1. [Store ↔ Warehouse Protocol](#store--warehouse-protocol)
2. [Warehouse ↔ Supplier Protocol](#warehouse--supplier-protocol)

---

## Store ↔ Warehouse Protocol

### Overview
Multi-response selection protocol where stores request products from MULTIPLE warehouses simultaneously, collect all responses, score them, select the best warehouse, and send denials to non-selected warehouses to unlock their stock.

### Message Flow

```
Store                    Warehouse1              Warehouse2              Warehouse3
  |                           |                       |                       |
  |  1. store-buy (broadcast) |                       |                       |
  |-------------------------->|---------------------->|---------------------->|
  |                           |                       |                       |
  |                           | (Lock stock)          | (Lock stock)          | (Check stock - insufficient)
  |                           |                       |                       |
  |  2. warehouse-accept      |                       |                       |
  |<--------------------------|                       |                       |
  |                           |                       |                       |
  |  2. warehouse-accept      |                       |                       |
  |<--------------------------------------------------|                       |
  |                           |                       |                       |
  |  2. warehouse-reject      |                       |                       |
  |<----------------------------------------------------------------------|
  |                           |                       |                       |
  | (Score acceptances,       |                       |                       |
  |  select best)             |                       |                       |
  |                           |                       |                       |
  |  3. store-confirm (winner)|                       |                       |
  |<--------------------------------------------------|                       |
  |                           |                       |                       |
  |  4. store-deny (loser)    |                       |                       |
  |-------------------------->|                       |                       |
  |                           |                       |                       |
  |                           | (Unlock stock)        | (Update stock,        |
  |                           |                       |  add to pending)      |
```

### 1. `store-buy` (Request)

**Direction:** Store → Warehouse

**Metadata:**
```json
{
  "performative": "store-buy",
  "store_id": "store1@localhost",
  "node_id": "5",
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
    "node_id": "5",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Warehouse Action:**
- Check if product exists and quantity available
- If yes: Lock stock and send acceptance
- If no: Send rejection or ignore (timeout on store side)

---

### 2. `warehouse-accept` (Acceptance)

**Direction:** Warehouse → Store

**Metadata:**
```json
{
  "performative": "warehouse-accept",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "node_id": "12",
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
    "node_id": "12",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Store Action:**
- Receive acceptance(s) from one or more warehouses
- Collect ALL responses (acceptances and rejections) within timeout
- Calculate score for each accepting warehouse using node_id for distance
- Select warehouse with LOWEST score (best option)
- Update own stock (add received quantity)
- Send confirmation to SELECTED warehouse
- Send denial to ALL OTHER accepting warehouses to unlock their stock

---

### 3. `store-confirm` (Confirmation)

**Direction:** Store → Warehouse

**Metadata:**
```json
{
  "performative": "store-confirm",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "node_id": "5",
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
    "node_id": "5",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Warehouse Action:**
- Receive confirmation from store
- Unlock stock (remove from locked_stock)
- Add to pending_orders (as Order object) for vehicle pickup

---

### 4. `store-deny` (Denial)

**Direction:** Store → Warehouse

**Metadata:**
```json
{
  "performative": "store-deny",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "node_id": "5",
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
    "performative": "store-deny",
    "warehouse_id": "warehouse1@localhost",
    "store_id": "store1@localhost",
    "node_id": "5",
    "request_id": "0"
  },
  "body": "5 A"
}
```

**Warehouse Action:**
- Receive denial (not selected)
- Unlock stock (locked_stock -= quantity, stock += quantity)
- Do NOT add to pending_orders

---

### 5. `warehouse-reject` (Rejection)

**Direction:** Warehouse → Store

**Metadata:**
```json
{
  "performative": "warehouse-reject",
  "warehouse_id": "warehouse1@localhost",
  "store_id": "store1@localhost",
  "node_id": "12",
  "request_id": "0"
}
```

**Body Format:**
```
"{quantity} {product} {reason}"
```

**Example:**
```json
{
  "metadata": {
    "performative": "warehouse-reject",
    "warehouse_id": "warehouse1@localhost",
    "store_id": "store1@localhost",
    "node_id": "12",
    "request_id": "0"
  },
  "body": "5 A insufficient_stock"
}
```

**Store Action:**
- Receive rejection with reason
- Add request to `failed_requests` queue for retry
- May try other warehouses

---

### Timeout Handling

**Store side (CollectWarehouseResponses + ReceiveAllResponses):**
- Timeout: 5 seconds to collect all responses
- Action: Proceed with responses received before timeout
- If no acceptances received: Add request to `failed_requests` queue

**Warehouse side (ReceiveConfirmationOrDenial):**
- Timeout: 10 seconds to receive either store-confirm or store-deny
- Action: Unlock stock (assume denied), return to available inventory

---

## Warehouse ↔ Supplier Protocol

### Overview
Multi-response selection protocol where warehouses request materials from MULTIPLE suppliers simultaneously, collect all responses, score them, select the best supplier, and send denials to non-selected suppliers.

### Message Flow

```
Warehouse                Supplier1               Supplier2               Supplier3
  |                           |                       |                       |
  |  1. warehouse-buy (broadcast)                     |                       |
  |-------------------------->|---------------------->|---------------------->|
  |                           |                       |                       |
  |                           | (Infinite stock,      | (Infinite stock,      | (Infinite stock,
  |                           |  track supplied)      |  track supplied)      |  track supplied)
  |                           |                       |                       |
  |  2. supplier-accept       |                       |                       |
  |<--------------------------|                       |                       |
  |                           |                       |                       |
  |  2. supplier-accept       |                       |                       |
  |<--------------------------------------------------|                       |
  |                           |                       |                       |
  |  2. supplier-accept       |                       |                       |
  |<----------------------------------------------------------------------|
  |                           |                       |                       |
  | (Score acceptances,       |                       |                       |
  |  select best)             |                       |                       |
  |                           |                       |                       |
  |  3. warehouse-confirm (winner)                    |                       |
  |<--------------------------------------------------|                       |
  |                           |                       |                       |
  |  4. warehouse-deny (loser)|                       |                       |
  |-------------------------->|                       |                       |
  |                           |                       |                       |
  |  4. warehouse-deny (loser)|                       |                       |
  |<----------------------------------------------------------------------|
  |                           |                       |                       |
  |                           | (Log rejection)       | (Add to pending       | (Log rejection)
  |                           |                       |  deliveries)          |
```

### 1. `warehouse-buy` (Request)

**Direction:** Warehouse → Supplier

**Metadata:**
```json
{
  "performative": "warehouse-buy",
  "warehouse_id": "warehouse1@localhost",
  "node_id": "12",
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
    "node_id": "12",
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
  "node_id": "8",
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
    "node_id": "8",
    "request_id": "1"
  },
  "body": "25 A"
}
```

**Warehouse Action:**
- Receive acceptance(s) from one or more suppliers
- Collect ALL responses within timeout
- Calculate score for each accepting supplier using node_id for distance
- Select supplier with LOWEST score (best option)
- Update own stock (add received quantity)
- Send confirmation to SELECTED supplier
- Send denial to ALL OTHER accepting suppliers

---

### 3. `warehouse-confirm` (Confirmation)

**Direction:** Warehouse → Supplier

**Metadata:**
```json
{
  "performative": "warehouse-confirm",
  "supplier_id": "supplier1@localhost",
  "warehouse_id": "warehouse1@localhost",
  "node_id": "12",
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
    "node_id": "12",
    "request_id": "1"
  },
  "body": "25 A"
}
```

**Supplier Action:**
- Receive confirmation from warehouse
- Add to pending_deliveries[warehouse_jid] for vehicle pickup

---

### 4. `warehouse-deny` (Denial)

**Direction:** Warehouse → Supplier

**Metadata:**
```json
{
  "performative": "warehouse-deny",
  "supplier_id": "supplier1@localhost",
  "warehouse_id": "warehouse1@localhost",
  "node_id": "12",
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
    "performative": "warehouse-deny",
    "supplier_id": "supplier1@localhost",
    "warehouse_id": "warehouse1@localhost",
    "node_id": "12",
    "request_id": "1"
  },
  "body": "25 A"
}
```

**Supplier Action:**
- Receive denial (not selected)
- Log rejection (no stock rollback needed - infinite stock)

---

### Timeout Handling

**Warehouse side (CollectSupplierResponses + ReceiveAllSupplierResponses):**
- Timeout: 5 seconds to collect all responses
- Action: Proceed with responses received before timeout
- If no acceptances received: Add request to `failed_requests` queue (if implemented)

**Supplier side (ReceiveConfirmationOrDenial):**
- Timeout: 10 seconds to receive either warehouse-confirm or warehouse-deny
- Action: Log timeout (no rollback needed - infinite stock)

---

## Key Design Principles

### 1. **Unique Message Routing**
Each message includes multiple metadata keys to ensure race condition prevention:
- `performative`: Message type
- Agent IDs: Source and destination
- `node_id`: Geographic location/position identifier of sender
- `request_id`: Unique identifier for each request

### 2. **Template Filtering**
Behaviours use multi-key templates to receive only their specific messages:
```python
template = Template()
template.set_metadata("performative", "warehouse-accept")
template.set_metadata("store_id", str(agent.jid))
template.set_metadata("request_id", str(request_id))
```

### 3. **Node ID for Location Tracking**
- Every message includes sender's `node_id` in metadata
- Enables distance calculation between agents
- Used for warehouse selection scoring
- Essential for vehicle routing optimization

### 4. **Request Counter Management**
- Counter value captured **BEFORE** incrementing
- Same value used for both message metadata and template filtering
- Ensures sender and receiver use identical request_id
- Example:
  ```python
  request_id_for_template = agent.request_counter
  agent.request_counter += 1
  # Use request_id_for_template for both sending and template
  msg.set_metadata("request_id", str(request_id_for_template))
  ```

### 5. **Body Format Consistency**
All messages use: `"{quantity} {product}"` (or `"{quantity} {product} {reason}"` for rejections)
- No redundant data (request_id only in metadata)
- Easy parsing with `split(" ")`

### 6. **Timeout Strategies**
- Shorter timeouts for critical operations (5s for acceptances)
- Longer timeouts for confirmations (10s)
- Failed requests queued for retry

---

## Store Warehouse Selection Protocol

### Overview
When a store sends a `store-buy` request to multiple warehouses, it collects ALL responses (accepts and rejects) before making a decision. After selecting the best warehouse, it sends denials to others to unlock their stock.

### Selection Flow

```
Store                 Warehouse1       Warehouse2       Warehouse3
  |                       |                |                |
  | store-buy (to all)    |                |                |
  |---------------------->|--------------->|--------------->|
  |                       |                |                |
  | Wait for all responses (5s timeout)   |                |
  |                       |                |                |
  | warehouse-accept      |                |                |
  |<----------------------|                |                |
  | (node_id=12)          |                |                |
  |                       |                |                |
  | warehouse-reject      |                |                |
  |<--------------------------------------|                |
  | (insufficient_stock)  |                |                |
  |                       |                |                |
  | warehouse-accept      |                |                |
  |<----------------------------------------------------|
  | (node_id=18)          |                |                |
  |                       |                |                |
  | Calculate scores:     |                |                |
  | - Warehouse1: 42.5    |                |                |
  | - Warehouse3: 28.3    |                |                |
  |                       |                |                |
  | Select best (lowest score) = Warehouse3              |
  |                       |                |                |
  | store-confirm         |                |                |
  |<----------------------------------------------------|
  |                       |                |                |
  | store-deny            |                |                |
  |---------------------->|                |                |
  | (unlock stock)        |                |                |
```

### Warehouse Scoring

**Function:** `Store.calculate_warehouse_score(accept_msg) -> float`

**Criteria (examples):**
1. **Distance** (using node_id):
   ```python
   warehouse_node_id = int(accept_msg.get_metadata("node_id"))
   warehouse_node = agent.map.get_node(warehouse_node_id)
   distance = math.sqrt((agent.pos_x - warehouse_node.x)**2 + 
                       (agent.pos_y - warehouse_node.y)**2)
   ```

2. **Historical Reliability**: Track success rate of past orders
3. **Delivery Time**: Expected time to delivery (could be in metadata)
4. **Cost**: Price per unit (could be in metadata)
5. **Warehouse Load**: Current capacity utilization

**Lower score = Better warehouse**

### Response Collection

**Behaviour:** `CollectWarehouseResponses` and `ReceiveAllResponses`

**Process:**
1. Send `store-buy` to N warehouses
2. Wait for responses (5s timeout)
3. Collect acceptances in list: `[(warehouse_jid, msg), ...]`
4. Collect rejections in list: `[(warehouse_jid, msg, reason), ...]`
5. Calculate score for each acceptance
6. Select warehouse with lowest score
7. Send `store-confirm` to selected warehouse
8. (Optional) Send cancellation to other accepting warehouses

**Handling:**
- If no acceptances: Add to `failed_requests` queue
- If timeout before all responses: Proceed with received responses
- If all reject: Add to `failed_requests` queue

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

**Last Updated:** November 13, 2025
