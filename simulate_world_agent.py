"""
Standalone simulation of WorldAgent with time-delta messaging.
No XMPP server required - simulates message passing in-memory.
"""

import json
import time
from world.world import World


class SimulatedWorldAgent:
    """
    Simulated WorldAgent that processes time-delta messages and returns JSON responses.
    """
    
    def __init__(self, width=7, height=7, mode="different", max_cost=4, seed=None,
                 gas_stations=1, warehouses=2, suppliers=3, stores=2, highway=True,
                 traffic_probability=0.4, traffic_spread_probability=0.75,
                 traffic_interval=3, untraffic_probability=0.4):
        """Initialize the world agent with world parameters."""
        print("[WorldAgent] Initializing World...")
        
        self.world = World(
            width=width,
            height=height,
            mode=mode,
            max_cost=max_cost,
            seed=seed,
            gas_stations=gas_stations,
            warehouses=warehouses,
            suppliers=suppliers,
            stores=stores,
            highway=highway,
            traffic_probability=traffic_probability,
            traffic_spread_probability=traffic_spread_probability,
            traffic_interval=traffic_interval,
            untraffic_probability=untraffic_probability
        )
        
        print(f"[WorldAgent] World initialized successfully!")
        print(f"[WorldAgent] World Grid: {self.world.width}x{self.world.height}")
        print(f"[WorldAgent] World Seed: {self.world.seed}")
        print(f"[WorldAgent] Nodes: {len(self.world.graph.nodes)}")
        print(f"[WorldAgent] Edges: {len(self.world.graph.edges)}")
        print(f"[WorldAgent] Warehouses: {self.world.warehouses}")
        print(f"[WorldAgent] Suppliers: {self.world.suppliers}")
        print(f"[WorldAgent] Stores: {self.world.stores}")
        print(f"[WorldAgent] Gas Stations: {self.world.gas_stations}")
    
    def process_time_delta_message(self, delta_time):
        """
        Process a time-delta message and simulate the world.
        
        Args:
            delta_time (int): Number of ticks to simulate
            
        Returns:
            dict: JSON response with edge updates
        """
        print(f"\n[WorldAgent] ===== Processing Time-Delta Request =====")
        print(f"[WorldAgent] Delta Time: {delta_time} ticks")
        
        # Simulate delta_time ticks and track when edges change
        results = []
        
        # Store initial edge states
        initial_states = {}
        for edge in self.world.graph.edges:
            initial_states[(edge.node1.id, edge.node2.id)] = edge.weight
        
        # Simulate each tick and track changes
        for i in range(delta_time):
            self.world.get_events(1)  # Simulate one tick at a time
            current_tick = self.world.tick_counter
            
            print(f"[WorldAgent] Simulated tick {i+1}/{delta_time} (current tick: {current_tick}, infected edges: {len(self.world.graph.infected_edges)})")
            
            # Check which edges changed in this tick
            for edge in self.world.graph.edges:
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
        
        # Create response
        response = {
            "type": "time_delta_response",
            "delta_time": delta_time,
            "final_tick": self.world.tick_counter,
            "edges": results
        }
        
        print(f"[WorldAgent] Simulation complete!")
        print(f"[WorldAgent] Total edge updates: {len(results)}")
        print(f"[WorldAgent] Final tick: {self.world.tick_counter}")
        
        return response
    
    def get_world_state(self):
        """Get current world state summary."""
        return {
            "type": "world_state",
            "tick": self.world.tick_counter,
            "width": self.world.width,
            "height": self.world.height,
            "seed": self.world.seed,
            "mode": self.world.mode,
            "num_nodes": len(self.world.graph.nodes),
            "num_edges": len(self.world.graph.edges),
            "infected_edges": len(self.world.graph.infected_edges)
        }
    
    def get_edges_with_traffic(self, edges_data):
        """Filter edges that have traffic (weight > initial_weight)."""
        traffic_edges = []
        seen_pairs = set()
        
        for edge_info in edges_data:
            # Get actual edge from graph
            edge = self.world.graph.get_edge(edge_info["node1_id"], edge_info["node2_id"])
            if edge and edge.weight > edge.initial_weight:
                # Avoid duplicates for bidirectional edges
                pair = tuple(sorted([edge_info["node1_id"], edge_info["node2_id"]]))
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    traffic_edges.append(edge_info)
        
        return traffic_edges


def main():
    """Main simulation demonstration."""
    print("=" * 70)
    print("WORLDAGENT TIME-DELTA SIMULATION")
    print("=" * 70)
    
    # Create the simulated world agent
    agent = SimulatedWorldAgent(
        width=7,
        height=7,
        mode="different",
        max_cost=4,
        seed=None,  # Random seed (or use specific seed if available in seeds folder)
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
    
    print("\n" + "=" * 70)
    print("INITIAL WORLD STATE")
    print("=" * 70)
    initial_state = agent.get_world_state()
    print(json.dumps(initial_state, indent=2))
    
    # Simulate receiving a time-delta message
    print("\n" + "=" * 70)
    print("SIMULATING TIME-DELTA MESSAGE")
    print("=" * 70)
    
    delta_time = 5
    print(f"\nMessage received: {{'delta_time': {delta_time}}}")
    
    # Process the message
    response = agent.process_time_delta_message(delta_time)
    
    # Display response summary
    print("\n" + "=" * 70)
    print("RESPONSE SUMMARY")
    print("=" * 70)
    print(f"Response Type: {response['type']}")
    print(f"Delta Time Simulated: {response['delta_time']}")
    print(f"Final Tick: {response['final_tick']}")
    print(f"Total Edge Updates: {len(response['edges'])}")
    
    # Show sample edges
    print("\n--- Sample Edge Data (first 5) ---")
    for i, edge in enumerate(response['edges'][:5]):
        print(f"\nEdge {i+1}:")
        print(f"  Route: {edge['node1_id']} → {edge['node2_id']}")
        print(f"  Time: {edge['new_time']}")
        print(f"  Fuel: {edge['new_fuel_consumption']} L")
        print(f"  Instant (tick): {edge['instant']}")
    
    # Show edges with traffic
    print("\n--- Edges with Traffic ---")
    traffic_edges = agent.get_edges_with_traffic(response['edges'][-len(agent.world.graph.edges):])  # Last tick only
    print(f"Number of congested edges: {len(traffic_edges)}")
    
    for i, edge in enumerate(traffic_edges[:10]):  # Show first 10
        print(f"  {edge['node1_id']} → {edge['node2_id']}: "
              f"time={edge['new_time']}, fuel={edge['new_fuel_consumption']}L")
    
    if len(traffic_edges) > 10:
        print(f"  ... and {len(traffic_edges) - 10} more")
    
    # Save full response to file
    output_file = "world_agent_response.json"
    with open(output_file, 'w') as f:
        json.dump(response, f, indent=2)
    print(f"\n✓ Full response saved to: {output_file}")
    
    # Calculate statistics
    print("\n" + "=" * 70)
    print("STATISTICS")
    print("=" * 70)
    
    last_tick_edges = response['edges'][-len(agent.world.graph.edges):]
    total_fuel = sum(e['new_fuel_consumption'] for e in last_tick_edges)
    avg_time = sum(e['new_time'] for e in last_tick_edges) / len(last_tick_edges)
    
    print(f"Total network fuel consumption: {total_fuel:.2f} L")
    print(f"Average edge travel time: {avg_time:.2f}")
    print(f"Congestion rate: {len(traffic_edges) / len(last_tick_edges) * 100:.1f}%")
    
    # Demonstrate multiple requests
    print("\n" + "=" * 70)
    print("SECOND TIME-DELTA REQUEST")
    print("=" * 70)
    
    delta_time_2 = 3
    print(f"\nMessage received: {{'delta_time': {delta_time_2}}}")
    response_2 = agent.process_time_delta_message(delta_time_2)
    
    print(f"\nResponse Type: {response_2['type']}")
    print(f"Delta Time Simulated: {response_2['delta_time']}")
    print(f"Final Tick: {response_2['final_tick']}")
    print(f"Total Edge Updates: {len(response_2['edges'])}")
    
    print("\n" + "=" * 70)
    print("SIMULATION COMPLETE")
    print("=" * 70)
    print(f"✓ World is now at tick {agent.world.tick_counter}")
    print(f"✓ Total simulated ticks: {delta_time + delta_time_2}")
    print(f"✓ Ready for more time-delta requests!")


if __name__ == "__main__":
    main()
