# Request ID Encoding System

## Overview

This document describes the integer-based request ID encoding system used across all agents in the supply chain simulation. The system ensures that every request ID is globally unique across all agent types and instances.

## ID Format

```
ID = [Agent_Type][Instance_ID][Counter]
     (1 digit)    (2 digits)   (6 digits)
```

**Total:** 9-digit integer

### Components

1. **Agent Type Code** (1 digit)
   - Identifies the type of agent that created the request
   - First digit of the ID

2. **Instance ID** (2 digits)
   - Identifies which specific agent instance within that type
   - Middle 2 digits
   - Supports 01-99 instances per agent type

3. **Counter** (6 digits)
   - Sequential counter maintained by each agent
   - Last 6 digits
   - Supports up to 999,999 requests per agent instance

## Agent Type Codes

| Agent Type | Code | Description |
|------------|------|-------------|
| Store      | 1    | Consumer agents that request products |
| Warehouse  | 2    | Storage agents that supply stores and buy from suppliers |
| Supplier   | 3    | Production agents with infinite stock |
| Vehicle    | 4    | Transport agents that deliver orders |

## Examples

### Store Examples
- **Store #1, Request #5**: `1` + `01` + `000005` = **100100005**
- **Store #3, Request #142**: `1` + `03` + `000142` = **100300142**
- **Store #12, Request #50000**: `1` + `12` + `050000` = **112050000**

### Warehouse Examples
- **Warehouse #1, Request #1**: `2` + `01` + `000001` = **200100001**
- **Warehouse #5, Request #278**: `2` + `05` + `000278` = **205000278**
- **Warehouse #10, Request #99999**: `2` + `10` + `099999` = **210099999**

### Supplier Examples
- **Supplier #1, Request #100**: `3` + `01` + `000100` = **300100100**
- **Supplier #3, Request #42**: `3` + `03` + `000042` = **303000042**
- **Supplier #7, Request #5000**: `3` + `07` + `005000` = **307005000**

### Vehicle Examples
- **Vehicle #1, Request #10**: `4` + `01` + `000010` = **400100010**
- **Vehicle #15, Request #500**: `4` + `15` + `000500` = **415000500**

## Implementation

### Initialization

Each agent must extract its instance number from its JID and calculate its ID base:

```python
# Extract instance number from JID (e.g., "store1@localhost" → 1)
jid_name = str(jid).split('@')[0]
instance_id = int(''.join(filter(str.isdigit, jid_name)))

# Calculate ID base using agent type code
# Store=1, Warehouse=2, Supplier=3, Vehicle=4
agent_type_code = 1  # Example for Store
self.id_base = (agent_type_code * 100_000_000) + (instance_id * 1_000_000)

# Initialize counter
self.request_counter = 0
```

### Generating Request IDs

```python
def generate_request_id(self):
    request_id = self.id_base + self.request_counter
    self.request_counter += 1
    return request_id
```

### Example for Store Agent

```python
# Store #1
self.id_base = (1 * 100_000_000) + (1 * 1_000_000) = 101_000_000

# First request:  101_000_000 + 0 = 101000000
# Second request: 101_000_000 + 1 = 101000001
# Third request:  101_000_000 + 2 = 101000002
```

### Example for Warehouse Agent

```python
# Warehouse #3
self.id_base = (2 * 100_000_000) + (3 * 1_000_000) = 203_000_000

# First request:  203_000_000 + 0 = 203000000
# Second request: 203_000_000 + 1 = 203000001
# Third request:  203_000_000 + 2 = 203000002
```

## Decoding Request IDs

To extract information from a request ID:

```python
def decode_request_id(request_id):
    agent_type_code = request_id // 100_000_000
    instance_id = (request_id % 100_000_000) // 1_000_000
    counter = request_id % 1_000_000
    
    agent_types = {1: "Store", 2: "Warehouse", 3: "Supplier", 4: "Vehicle"}
    agent_type = agent_types.get(agent_type_code, "Unknown")
    
    return {
        "agent_type": agent_type,
        "instance_id": instance_id,
        "counter": counter
    }
```

### Example Decoding

```python
# ID: 203000042
decode_request_id(203000042)
# Returns:
# {
#     "agent_type": "Warehouse",
#     "instance_id": 3,
#     "counter": 42
# }
```

## Limitations

- **Maximum instances per type:** 99 (limited by 2-digit instance ID)
- **Maximum requests per agent:** 999,999 (limited by 6-digit counter)
- **Agent naming requirement:** Agents must have numeric identifiers in their JIDs (e.g., `store1`, `warehouse5`)

## Benefits

1. **Global Uniqueness:** No collisions possible between any agents
2. **Debuggable:** ID reveals which agent created the request
3. **Deterministic:** Same logic applies everywhere
4. **Integer Type:** Compatible with existing Order.orderid expectations
5. **No Coordination:** Each agent generates IDs independently
6. **Human Readable:** Easy to identify patterns during debugging

## Migration Notes

When implementing this system:

1. Update `__init__` methods in Store, Warehouse, Supplier, and Vehicle agents
2. Replace simple `self.request_counter` with `self.id_base + self.request_counter`
3. Keep `request_counter` incrementing from 0
4. No changes needed to message templates (already use request_id as metadata)
5. Order.orderid already expects int type, so no changes needed there
