# Supply Chain Optimization with SPADE

## Overview

This project implements a **supply chain simulation** using **SPADE (Smart Python Agent Development Environment)** agents. The system models a dynamic world with transportation networks, facilities (warehouses, suppliers, stores, gas stations), and traffic simulation.

## Components

### 1. **World** (`world/world.py`)
The core simulation environment that manages:
- **Grid-based graph**: A 2D grid where nodes represent locations and edges represent transportation routes
- **Facilities**: Distribution of warehouses, suppliers, stores, and gas stations
- **Traffic dynamics**: Stochastic traffic events that increase edge costs (travel time)
- **Traffic propagation**: Dynamic traffic spread to adjacent edges
- **Recovery system**: Gradual restoration of traffic-congested edges

#### Key Parameters:
- `width`, `height`: Grid dimensions
- `mode`: "uniform" or "different" cost distribution
- `seed`: Reproducibility of world generation
- `traffic_probability`: Chance of traffic event per tick
- `traffic_spread_probability`: Chance of traffic spreading to adjacent edges
- `traffic_interval`: Ticks between traffic events
- `untraffic_probability`: Chance of congestion clearing

### 2. **WorldAgent** (`world_agent.py`)
A SPADE agent that manages the world simulation and provides an interface for other agents.

#### Responsibilities:
- **World Management**: Initialize and maintain the world state
- **Simulation Loop**: Execute world ticks at regular intervals
- **Message Handling**: Respond to queries from other agents
- **Broadcasting**: Notify subscribed agents of world state changes

#### Behaviors:

##### `WorldInitBehaviour` (OneShotBehaviour)
Initializes the world with configured parameters when the agent starts.

##### `WorldTickBehaviour` (CyclicBehaviour)
Executes world ticks at regular intervals and broadcasts updates to subscribed agents.

##### `MessageHandlerBehaviour` (CyclicBehaviour)
Handles incoming messages from other agents with support for:
- `query_world_state`: Get complete world state
- `query_node_info`: Get information about a specific node
- `query_edge_info`: Get information about a specific edge
- `query_facilities`: Get locations of all facilities
- `subscribe`: Subscribe to world state updates

### 3. **Graph** (`world/graph.py`)
A graph data structure representing the transportation network with:
- Nodes representing locations
- Edges representing routes with costs and distances
- Support for fuel consumption calculation

## Installation & Setup

### Prerequisites
- Python 3.12+
- XMPP Server (e.g., ejabberd) for agent communication
- Required packages listed in `environment.yml`

### Install Dependencies
```bash
conda env create -f environment.yml
conda activate SPADE
```

Or with pip:
```bash
pip install spade aiohttp networkx numpy matplotlib
```

### Configure XMPP Server
For local testing, you can use the built-in XMPP test server or install ejabberd.

## Usage

### Run the WorldAgent
```bash
python world_agent.py
```

This will:
1. Start the WorldAgent on `world@localhost`
2. Initialize the world with default parameters
3. Begin executing world ticks every 2 seconds
4. Listen for messages from other agents

### Example: Creating Other Agents to Interact with WorldAgent

```python
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import json

class TransportAgent(Agent):
    """An agent that queries world state from WorldAgent"""
    
    class QueryBehaviour(CyclicBehaviour):
        async def run(self):
            # Subscribe to world updates
            msg = Message(to="world@localhost")
            msg.body = json.dumps({"type": "subscribe"})
            await self.send(msg)
            
            # Query world state
            msg = Message(to="world@localhost")
            msg.body = json.dumps({"type": "query_world_state"})
            await self.send(msg)
            
            # Receive and process response
            response = await self.receive(timeout=5)
            if response:
                data = json.loads(response.body)
                print(f"World State: {data}")
    
    async def setup(self):
        self.add_behaviour(self.QueryBehaviour())
```

### Query Examples

#### Query World State
```json
{
  "type": "query_world_state"
}
```

Response:
```json
{
  "type": "world_state",
  "data": {
    "tick": 15,
    "width": 5,
    "height": 5,
    "seed": 42,
    "num_nodes": 25,
    "num_edges": 40,
    "infected_edges": 3,
    "warehouses": 2,
    "suppliers": 3,
    "stores": 2
  }
}
```

#### Query Node Information
```json
{
  "type": "query_node_info",
  "node_id": 5
}
```

Response:
```json
{
  "type": "node_info",
  "data": {
    "id": 5,
    "x": 0,
    "y": 4,
    "warehouse": true,
    "supplier": false,
    "store": false,
    "gas_station": false
  }
}
```

#### Query Edge Information
```json
{
  "type": "query_edge_info",
  "node_u": 5,
  "node_v": 10
}
```

Response:
```json
{
  "type": "edge_info",
  "data": {
    "node_u": 5,
    "node_v": 10,
    "weight": 3,
    "initial_weight": 1,
    "distance": 1500,
    "fuel_consumption": 230.77,
    "is_infected": true
  }
}
```

#### Query Facilities
```json
{
  "type": "query_facilities"
}
```

Response:
```json
{
  "type": "facilities_info",
  "data": {
    "warehouses": [5, 12],
    "suppliers": [1, 8, 15],
    "stores": [3, 20],
    "gas_stations": [18]
  }
}
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│              WorldAgent (SPADE)                  │
├─────────────────────────────────────────────────┤
│  • WorldInitBehaviour                           │
│  • WorldTickBehaviour (Simulation Loop)         │
│  • MessageHandlerBehaviour (Query Interface)    │
├─────────────────────────────────────────────────┤
│            World Simulation                      │
├─────────────────────────────────────────────────┤
│  • Graph (Network)                              │
│  • Traffic Management                           │
│  • Facility Management                          │
│  • State Broadcasting                           │
└─────────────────────────────────────────────────┘
         ▲
         │ (XMPP Messages)
         │
┌────────┴──────────────────────────────────────┐
│  Other SPADE Agents (Transport, Logistics)   │
└─────────────────────────────────────────────────┘
```

## Configuration

### World Parameters (in `world_agent.py`)
```python
self.agent.world = World(
    width=5,                        # Grid width
    height=5,                       # Grid height
    mode="uniform",                 # Cost distribution mode
    max_cost=5,                     # Maximum edge weight
    seed=None,                      # Seed for reproducibility
    gas_stations=1,                 # Number of gas stations
    warehouses=2,                   # Number of warehouses
    suppliers=3,                    # Number of suppliers
    stores=2,                       # Number of stores
    highway=True,                   # Enable highway edge
    traffic_probability=0.4,        # Traffic event probability
    traffic_spread_probability=0.75,# Traffic spread probability
    traffic_interval=3,             # Ticks between traffic events
    untraffic_probability=0.4       # Recovery probability
)
```

## Running the Simulation

### Simple Simulation (No Agents)
```bash
python main.py
```

This runs the world without SPADE, useful for testing the world logic.

### Agent-Based Simulation
1. Start the XMPP server (if using external server)
2. Run the WorldAgent:
   ```bash
   python world_agent.py
   ```
3. In another terminal, run other agents that query the WorldAgent

## Future Enhancements

- [ ] TransportAgent for route optimization
- [ ] LogisticsAgent for inventory management
- [ ] VehicleAgent for individual vehicle simulation
- [ ] Web dashboard for visualization
- [ ] Machine learning for traffic prediction
- [ ] Advanced routing algorithms (A*, Dijkstra)

## License

See LICENSE file

## Contributing

Submit issues and pull requests to the GitHub repository.
