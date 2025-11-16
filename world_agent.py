import spade
import asyncio
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
from world.world import World
import json
import time


class WorldAgent(Agent):
    """
    A SPADE agent that manages and simulates the supply chain world.
    
    Responsibilities:
    - Manage the world state and simulation
    - Execute world ticks at regular intervals
    - Handle traffic dynamics
    - Respond to queries from other agents about world state
    - Broadcast world state updates to subscribed agents
    """

    class WorldInitBehaviour(OneShotBehaviour):
        """Initializes the world when the agent starts up."""
        
        async def run(self):
            """Initialize the world with configured parameters."""
            print(f"[{self.agent.name}] Initializing World...")
            
            # Create world instance with specified parameters
            self.agent.world = World(
                width=7,
                height=7,
                mode="different", 
                max_cost=4, 
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

            
            print(f"[{self.agent.name}] World initialized successfully!")
            print(f"[{self.agent.name}] World Grid: {self.agent.world.width}x{self.agent.world.height}")
            print(f"[{self.agent.name}] World Seed: {self.agent.world.seed}")
            print(f"[{self.agent.name}] Starting main simulation loop...")

    class TimeDeltaBehaviour(CyclicBehaviour):
        """Handles time-delta simulation requests."""
        
        async def run(self):
            """Process time-delta messages and simulate world."""
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    content = json.loads(msg.body)
                    delta_time = content.get("delta_time", 1)
                    sender = str(msg.sender)
                    
                    print(f"\n[{self.agent.name}] Received time-delta request: {delta_time} ticks from {sender}")
                    
                    # Store initial edge states
                    initial_states = {}
                    for edge in self.agent.world.graph.edges:
                        initial_states[(edge.node1.id, edge.node2.id)] = edge.weight
                    
                    # Simulate delta_time ticks and track changes
                    results = []
                    for i in range(delta_time):
                        self.agent.world.get_events(1)  # Simulate one tick at a time
                        current_tick = self.agent.world.tick_counter
                        
                        print(f"[{self.agent.name}] Simulated tick {i+1}/{delta_time} (current tick: {current_tick})")
                        
                        # Check which edges changed in this tick
                        for edge in self.agent.world.graph.edges:
                            edge_key = (edge.node1.id, edge.node2.id)
                            if edge.weight != initial_states[edge_key]:
                                # Edge changed - record the instant (tick index)
                                edge.calculate_fuel_consumption()
                                edge_info = {
                                    "node1_id": edge.node1.id,
                                    "node2_id": edge.node2.id,
                                    "new_time": edge.weight,
                                    "new_fuel_consumption": round(edge.fuel_consumption, 3),
                                    "instant": i  # The tick index when it changed
                                }
                                results.append(edge_info)
                                # Update the initial state to current state
                                initial_states[edge_key] = edge.weight
                    
                    # Send response with all edge states
                    response = Message(to=sender)
                    response.set_metadata("performative", "inform")
                    response.body = json.dumps({
                        "type": "time_delta_response",
                        "delta_time": delta_time,
                        "final_tick": self.agent.world.tick_counter,
                        "edges": results
                    })
                    await self.send(response)
                    
                    print(f"[{self.agent.name}] Sent time-delta response with {len(results)} edge updates")
                    
                except json.JSONDecodeError as e:
                    print(f"[{self.agent.name}] Error decoding time-delta message: {e}")
                except Exception as e:
                    print(f"[{self.agent.name}] Error in TimeDeltaBehaviour: {e}")

    class MessageHandlerBehaviour(CyclicBehaviour):
        """Handles incoming messages from other agents."""
        
        async def run(self):
            """Process incoming messages."""
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    content = json.loads(msg.body)
                    msg_type = content.get("type")
                    
                    if msg_type == "query_world_state":
                        await self._handle_world_state_query(msg)
                    
                    elif msg_type == "query_node_info":
                        await self._handle_node_query(msg)
                    
                    elif msg_type == "query_edge_info":
                        await self._handle_edge_query(msg)
                    
                    elif msg_type == "query_facilities":
                        await self._handle_facilities_query(msg)
                    
                    elif msg_type == "subscribe":
                        await self._handle_subscribe(msg)
                    
                    else:
                        print(f"[{self.agent.name}] Unknown message type: {msg_type}")
                        
                except json.JSONDecodeError as e:
                    print(f"[{self.agent.name}] Error decoding message: {e}")
                except Exception as e:
                    print(f"[{self.agent.name}] Error handling message: {e}")

        async def _handle_world_state_query(self, msg):
            """Handle query for complete world state."""
            sender = str(msg.sender)
            world_data = {
                "tick": self.agent.world.tick_counter,
                "width": self.agent.world.width,
                "height": self.agent.world.height,
                "seed": self.agent.world.seed,
                "mode": self.agent.world.mode,
                "num_nodes": len(self.agent.world.graph.nodes),
                "num_edges": len(self.agent.world.graph.edges),
                "infected_edges": len(self.agent.world.graph.infected_edges),
                "gas_stations": self.agent.world.gas_stations,
                "warehouses": self.agent.world.warehouses,
                "suppliers": self.agent.world.suppliers,
                "stores": self.agent.world.stores
            }
            
            response = Message(to=sender)
            response.set_metadata("performative", "inform")
            response.body = json.dumps({
                "type": "world_state",
                "data": world_data
            })
            await self.send(response)
            print(f"[{self.agent.name}] Sent world state to {sender}")

        async def _handle_node_query(self, msg):
            """Handle query for information about a specific node."""
            sender = str(msg.sender)
            try:
                content = json.loads(msg.body)
                node_id = content.get("node_id")
                
                if node_id not in self.agent.world.graph.nodes:
                    response = Message(to=sender)
                    response.body = json.dumps({
                        "type": "error",
                        "message": f"Node {node_id} not found"
                    })
                else:
                    node = self.agent.world.graph.nodes[node_id]
                    node_data = {
                        "id": node_id,
                        "x": node.x,
                        "y": node.y,
                        "warehouse": node.warehouse,
                        "supplier": node.supplier,
                        "store": node.store,
                        "gas_station": node.gas_station
                    }
                    
                    response = Message(to=sender)
                    response.set_metadata("performative", "inform")
                    response.body = json.dumps({
                        "type": "node_info",
                        "data": node_data
                    })
                
                await self.send(response)
                print(f"[{self.agent.name}] Sent node {node_id} info to {sender}")
                
            except Exception as e:
                response = Message(to=sender)
                response.body = json.dumps({
                    "type": "error",
                    "message": str(e)
                })
                await self.send(response)

        async def _handle_edge_query(self, msg):
            """Handle query for information about edges."""
            sender = str(msg.sender)
            try:
                content = json.loads(msg.body)
                node_u = content.get("node_u")
                node_v = content.get("node_v")
                
                edge = self.agent.world.graph.get_edge(node_u, node_v)
                
                if edge is None:
                    response = Message(to=sender)
                    response.body = json.dumps({
                        "type": "error",
                        "message": f"Edge ({node_u}, {node_v}) not found"
                    })
                else:
                    edge_data = {
                        "node_u": node_u,
                        "node_v": node_v,
                        "weight": edge.weight,
                        "initial_weight": edge.initial_weight,
                        "distance": edge.distance,
                        "fuel_consumption": edge.get_fuel_consumption(),
                        "is_infected": (node_u, node_v) in self.agent.world.graph.infected_edges
                    }
                    
                    response = Message(to=sender)
                    response.set_metadata("performative", "inform")
                    response.body = json.dumps({
                        "type": "edge_info",
                        "data": edge_data
                    })
                
                await self.send(response)
                print(f"[{self.agent.name}] Sent edge ({node_u}, {node_v}) info to {sender}")
                
            except Exception as e:
                response = Message(to=sender)
                response.body = json.dumps({
                    "type": "error",
                    "message": str(e)
                })
                await self.send(response)

        async def _handle_facilities_query(self, msg):
            """Handle query for facility locations."""
            sender = str(msg.sender)
            
            facilities = {
                "warehouses": [],
                "suppliers": [],
                "stores": [],
                "gas_stations": []
            }
            
            for node_id, node in self.agent.world.graph.nodes.items():
                if node.warehouse:
                    facilities["warehouses"].append(node_id)
                if node.supplier:
                    facilities["suppliers"].append(node_id)
                if node.store:
                    facilities["stores"].append(node_id)
                if node.gas_station:
                    facilities["gas_stations"].append(node_id)
            
            response = Message(to=sender)
            response.set_metadata("performative", "inform")
            response.body = json.dumps({
                "type": "facilities_info",
                "data": facilities
            })
            await self.send(response)
            print(f"[{self.agent.name}] Sent facilities info to {sender}")

        async def _handle_subscribe(self, msg):
            """Handle subscription requests for world state updates."""
            sender = str(msg.sender)
            if sender not in self.agent.subscribers:
                self.agent.subscribers.append(sender)
                print(f"[{self.agent.name}] Agent {sender} subscribed to world updates")
            
            # Send confirmation
            response = Message(to=sender)
            response.set_metadata("performative", "confirm")
            response.body = json.dumps({
                "type": "subscription_confirmed"
            })
            await self.send(response)

    async def _broadcast_world_state(self):
        """Broadcast world state to all subscribed agents."""
        world_update = {
            "type": "world_tick_update",
            "tick": self.world.tick_counter,
            "infected_edges": len(self.world.graph.infected_edges),
            "timestamp": asyncio.get_event_loop().time()
        }
        
        for subscriber in self.subscribers:
            msg = Message(to=subscriber)
            msg.set_metadata("performative", "inform")
            msg.body = json.dumps(world_update)
            await self.send(msg)

    async def setup(self):
        """Set up the WorldAgent with its behaviors."""
        print(f"[{self.name}] Setting up WorldAgent...")
        
        # Initialize agent attributes
        self.world = None
        self.subscribers = []
        self.tick_interval = 2  # Seconds between world ticks
        
        # Add behaviors
        self.add_behaviour(self.WorldInitBehaviour())
        
        # Add time-delta behaviour with template
        template = Template()
        template.set_metadata("performative", "request")
        template.metadata = {"performative": "request"}
        self.add_behaviour(self.TimeDeltaBehaviour(), template)
        
        self.add_behaviour(self.MessageHandlerBehaviour())
        
        print(f"[{self.name}] WorldAgent setup complete!")


async def main():
    """
    Main entry point for the WorldAgent.
    Requires an XMPP server (like ejabberd) running on localhost.
    """
    print("--- Starting SPADE WorldAgent ---")
    
    # Create and start the WorldAgent
    # NOTE: Change credentials and server as needed
    world_agent = WorldAgent("world@localhost", "password")
    
    try:
        await world_agent.start()
        print("WorldAgent started successfully!")
        
        # Keep the agent running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n--- Stopping WorldAgent ---")
        await world_agent.stop()
    except Exception as e:
        print(f"Error: {e}")
        await world_agent.stop()


if __name__ == "__main__":
    # Run the WorldAgent
    # Ensure you have an XMPP server running on localhost
    spade.run(main())
    print("--- SPADE WorldAgent Finished ---")
