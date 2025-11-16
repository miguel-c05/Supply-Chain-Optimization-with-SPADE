"""
Test client for WorldAgent time-delta simulation.
Sends a time-delta request and receives edge state updates.
"""

import spade
import asyncio
from spade.agent import Agent
from spade.behaviour import OneShotBehaviour
from spade.message import Message
import json


class TestAgent(Agent):
    """Test agent that sends time-delta requests to WorldAgent."""
    
    class SendTimeDeltaBehaviour(OneShotBehaviour):
        """Sends a time-delta request to WorldAgent."""
        
        async def run(self):
            """Send time-delta request and wait for response."""
            print(f"[{self.agent.name}] Sending time-delta request...")
            
            # Create time-delta request
            msg = Message(to="world@localhost")
            msg.set_metadata("performative", "request")
            msg.body = json.dumps({
                "delta_time": 5  # Simulate 5 ticks
            })
            
            await self.send(msg)
            print(f"[{self.agent.name}] Time-delta request sent (delta_time=5)")
            
            # Wait for response
            response = await self.receive(timeout=30)
            
            if response:
                try:
                    content = json.loads(response.body)
                    print(f"\n[{self.agent.name}] Received response:")
                    print(f"  Type: {content.get('type')}")
                    print(f"  Delta Time: {content.get('delta_time')}")
                    print(f"  Final Tick: {content.get('final_tick')}")
                    print(f"  Number of Edges: {len(content.get('edges', []))}")
                    
                    # Show first 5 edges as example
                    edges = content.get('edges', [])
                    if edges:
                        print(f"\n  Sample Edge Updates (first 5):")
                        for i, edge in enumerate(edges[:5]):
                            print(f"    Edge {i+1}: {edge['node1_id']} -> {edge['node2_id']}")
                            print(f"      Time: {edge['new_time']}")
                            print(f"      Fuel: {edge['new_fuel_consumption']} L")
                            print(f"      Instant: {edge['time_instant']}")
                    
                    # Show edges with traffic (weight changed)
                    print(f"\n  Edges with Traffic:")
                    traffic_count = 0
                    for edge in edges:
                        if edge['new_time'] > 1:  # Assuming initial weight is 1
                            traffic_count += 1
                            print(f"    {edge['node1_id']} -> {edge['node2_id']}: time={edge['new_time']}, fuel={edge['new_fuel_consumption']}L")
                            if traffic_count >= 10:  # Limit output
                                break
                    
                    print(f"\n[{self.agent.name}] Total edges with traffic: {sum(1 for e in edges if e['new_time'] > 1)}")
                    
                except json.JSONDecodeError as e:
                    print(f"[{self.agent.name}] Error decoding response: {e}")
            else:
                print(f"[{self.agent.name}] No response received (timeout)")
            
            # Stop the agent
            await self.agent.stop()
    
    async def setup(self):
        """Set up the test agent."""
        print(f"[{self.name}] Test agent starting...")
        self.add_behaviour(self.SendTimeDeltaBehaviour())


async def main():
    """Main entry point for the test client."""
    print("--- Starting Test Agent ---")
    
    # Create and start the test agent
    test_agent = TestAgent("test@localhost", "password")
    
    try:
        await test_agent.start()
        print("Test agent started successfully!")
        
        # Wait for the agent to finish
        while test_agent.is_alive():
            await asyncio.sleep(1)
        
        print("\n--- Test Agent Finished ---")
        
    except KeyboardInterrupt:
        print("\n--- Stopping Test Agent ---")
        await test_agent.stop()
    except Exception as e:
        print(f"Error: {e}")
        await test_agent.stop()


if __name__ == "__main__":
    # Run the test agent
    # Ensure you have an XMPP server and WorldAgent running
    spade.run(main())
