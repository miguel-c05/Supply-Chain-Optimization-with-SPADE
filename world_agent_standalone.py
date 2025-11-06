"""
WorldAgent Standalone Version
This version runs WITHOUT XMPP server and without Docker.
All agents run in the same process with in-memory communication.

USAGE:
    python world_agent_standalone.py

This is the EASIEST way to get started immediately!
"""

import asyncio
import json
from typing import Dict, List, Callable
from world.world import World


class SimpleMessageBroker:
    """Simple in-memory message broker for agents."""
    
    def __init__(self):
        self.agents: Dict[str, Callable] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
    
    async def register_agent(self, agent_id: str, handler: Callable):
        """Register an agent with a message handler."""
        self.agents[agent_id] = handler
        print(f"[BROKER] Agent registered: {agent_id}")
    
    async def send_message(self, from_agent: str, to_agent: str, body: dict):
        """Send a message between agents."""
        if to_agent not in self.agents:
            print(f"[BROKER] ERROR: Agent {to_agent} not found")
            return
        
        # Call the handler directly
        await self.agents[to_agent](from_agent, body)


class StandaloneWorldAgent:
    """Standalone WorldAgent that works without XMPP."""
    
    def __init__(self, broker: SimpleMessageBroker):
        self.broker = broker
        self.world = None
        self.subscribers: List[str] = []
        self.tick_interval = 2
        self.running = True
    
    async def initialize(self):
        """Initialize the world."""
        print("[WorldAgent] Initializing World...")
        
        self.world = World(
            width=5,
            height=5,
            mode="uniform",
            max_cost=5,
            seed=None,
            gas_stations=1,
            warehouses=2,
            suppliers=3,
            stores=2,
            highway=True,
            traffic_probability=0.4,
            traffic_spread_probability=0.75,
            traffic_interval=3,
            untraffic_probability=0.4
        )
        
        print("[WorldAgent] World initialized successfully!")
        print(f"[WorldAgent] Seed: {self.world.seed}")
        await self.broker.register_agent("world", self.handle_message)
    
    async def handle_message(self, from_agent: str, message: dict):
        """Handle incoming messages from other agents."""
        msg_type = message.get("type")
        
        if msg_type == "subscribe":
            if from_agent not in self.subscribers:
                self.subscribers.append(from_agent)
                print(f"[WorldAgent] {from_agent} subscribed to updates")
        
        elif msg_type == "query_world_state":
            response = {
                "type": "world_state",
                "data": {
                    "tick": self.world.tick_counter,
                    "width": self.world.width,
                    "height": self.world.height,
                    "seed": self.world.seed,
                    "mode": self.world.mode,
                    "num_nodes": len(self.world.graph.nodes),
                    "num_edges": len(self.world.graph.edges),
                    "infected_edges": len(self.world.graph.infected_edges),
                    "gas_stations": self.world.gas_stations,
                    "warehouses": self.world.warehouses,
                    "suppliers": self.world.suppliers,
                    "stores": self.world.stores
                }
            }
            await self.broker.send_message("world", from_agent, response)
        
        elif msg_type == "query_facilities":
            facilities = {
                "warehouses": [],
                "suppliers": [],
                "stores": [],
                "gas_stations": []
            }
            
            for node_id, node in self.world.graph.nodes.items():
                if node.warehouse:
                    facilities["warehouses"].append(node_id)
                if node.supplier:
                    facilities["suppliers"].append(node_id)
                if node.store:
                    facilities["stores"].append(node_id)
                if node.gas_station:
                    facilities["gas_stations"].append(node_id)
            
            response = {
                "type": "facilities_info",
                "data": facilities
            }
            await self.broker.send_message("world", from_agent, response)
    
    async def run_simulation(self):
        """Run the simulation loop."""
        print("[WorldAgent] Starting simulation loop...")
        
        while self.running:
            try:
                # Execute world tick
                self.world.tick()
                current_tick = self.world.tick_counter
                
                print(f"\n[WorldAgent] ===== Tick {current_tick} =====")
                print(f"[WorldAgent] Infected edges: {len(self.world.graph.infected_edges)}")
                
                # Plot the world graph
                print(f"[WorldAgent] Generating graph visualization...")
                self.world.plot_graph()
                
                # Broadcast to subscribers
                update = {
                    "type": "world_tick_update",
                    "tick": current_tick,
                    "infected_edges": len(self.world.graph.infected_edges)
                }
                
                for subscriber in self.subscribers:
                    await self.broker.send_message("world", subscriber, update)
                
                # Wait for tick interval
                await asyncio.sleep(self.tick_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[WorldAgent] Error: {e}")


class StandaloneTransportAgent:
    """Standalone Transport Agent."""
    
    def __init__(self, broker: SimpleMessageBroker):
        self.broker = broker
        self.agent_id = "transport"
    
    async def initialize(self):
        """Initialize the agent."""
        await self.broker.register_agent(self.agent_id, self.handle_message)
        print(f"[{self.agent_id}] Initialized")
    
    async def handle_message(self, from_agent: str, message: dict):
        """Handle incoming messages."""
        msg_type = message.get("type")
        
        if msg_type == "world_state":
            data = message.get("data", {})
            print(f"\n[{self.agent_id}] ===== World State =====")
            print(f"  Tick: {data.get('tick')}")
            print(f"  Grid: {data.get('width')}x{data.get('height')}")
            print(f"  Nodes: {data.get('num_nodes')}")
            print(f"  Edges: {data.get('num_edges')}")
            print(f"  Infected Edges: {data.get('infected_edges')}")
        
        elif msg_type == "world_tick_update":
            tick = message.get("tick")
            infected = message.get("infected_edges")
            print(f"[{self.agent_id}] World Update - Tick: {tick}, Infected Edges: {infected}")
    
    async def run(self):
        """Run the agent."""
        # Subscribe to world updates
        await self.broker.send_message(self.agent_id, "world", {"type": "subscribe"})
        
        # Query world state every 5 seconds
        for _ in range(100):
            await asyncio.sleep(5)
            await self.broker.send_message(self.agent_id, "world", {"type": "query_world_state"})


class StandaloneLogisticsAgent:
    """Standalone Logistics Agent."""
    
    def __init__(self, broker: SimpleMessageBroker):
        self.broker = broker
        self.agent_id = "logistics"
    
    async def initialize(self):
        """Initialize the agent."""
        await self.broker.register_agent(self.agent_id, self.handle_message)
        print(f"[{self.agent_id}] Initialized")
    
    async def handle_message(self, from_agent: str, message: dict):
        """Handle incoming messages."""
        msg_type = message.get("type")
        
        if msg_type == "facilities_info":
            data = message.get("data", {})
            print(f"\n[{self.agent_id}] ===== Facilities Info =====")
            print(f"  Warehouses: {data.get('warehouses')}")
            print(f"  Suppliers: {data.get('suppliers')}")
            print(f"  Stores: {data.get('stores')}")
            print(f"  Gas Stations: {data.get('gas_stations')}")
    
    async def run(self):
        """Run the agent."""
        # Query facilities every 10 seconds
        for _ in range(100):
            await asyncio.sleep(10)
            await self.broker.send_message(self.agent_id, "world", {"type": "query_facilities"})


async def main():
    """Main entry point."""
    print("""
╔═════════════════════════════════════════════════════════════════════╗
║        WorldAgent Standalone (No Docker, No XMPP Server)           ║
║                                                                     ║
║        All agents run in a single process with in-memory           ║
║        communication. Perfect for testing and development.         ║
║                                                                     ║
║        Press Ctrl+C to stop                                        ║
╚═════════════════════════════════════════════════════════════════════╝
    """)
    
    # Create message broker
    broker = SimpleMessageBroker()
    
    # Create agents
    world_agent = StandaloneWorldAgent(broker)
    transport_agent = StandaloneTransportAgent(broker)
    logistics_agent = StandaloneLogisticsAgent(broker)
    
    # Initialize agents
    await world_agent.initialize()
    await transport_agent.initialize()
    await logistics_agent.initialize()
    
    # Run all agents concurrently
    try:
        await asyncio.gather(
            world_agent.run_simulation(),
            transport_agent.run(),
            logistics_agent.run()
        )
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
        world_agent.running = False
        print("[INFO] Done!")


if __name__ == "__main__":
    print("[INFO] Starting WorldAgent Standalone...")
    print("[INFO] Python AsyncIO Event Loop")
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Goodbye!")
