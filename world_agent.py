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
    """A SPADE agent that manages and simulates the supply chain world.
    
    This agent serves as the central coordinator for the supply chain simulation,
    managing the world state, executing simulation ticks, and handling communication
    with other agents (Store, Warehouse, Supplier, and Event agents). It implements
    the FIPA Agent Management Specification for agent discovery and coordination.
    
    The WorldAgent acts as a service provider, offering query services for world
    state information and event simulation. It follows FIPA protocols for:
    - Request/Response interactions (for time-delta and traffic simulations)
    - Inform interactions (for world state broadcasts and query responses)
    
    Attributes:
        world (World): The World instance containing the graph structure and
            simulation state (nodes, edges, facilities, etc.).
        subscribers (list): A list of agent JIDs subscribed to world state updates.
        tick_interval (float): Time in seconds between consecutive world ticks.
    
    Responsibilities:
        - Manage and maintain the world state and simulation progress
        - Execute world ticks at regular intervals and simulate time progression
        - Handle traffic dynamics and traffic simulation requests from Event agents
        - Respond to queries from other agents about world state (nodes, edges, facilities)
        - Broadcast world state updates to subscribed agents
        - Coordinate time-delta simulations with configurable duration
    """
    
    def __init__(self, jid, password, world=None):
        """Initialize the WorldAgent.
        
        Creates a new WorldAgent instance and optionally associates it with a World
        object. The agent initializes with empty subscriber list and default
        tick interval. If no world is provided, it must be set before the agent
        is fully operational.
        
        Args:
            jid (str): The Jabber ID (JID) for this agent on the XMPP server.
                Format: 'agent_name@server_address'
            password (str): The authentication password for the agent on the XMPP server.
            world (World, optional): A pre-initialized World instance containing
                the simulation graph and state. If None, must be assigned before
                the agent starts handling simulation requests. Defaults to None.
        
        Returns:
            None: Constructor initializes the parent Agent class and stores references.
        """
        super().__init__(jid, password)
        self.world = world

    class TimeDeltaBehaviour(CyclicBehaviour):
        """Handles time-delta simulation requests and traffic simulation requests.
        
        This behaviour implements FIPA Request/Response protocol for handling two types
        of simulation requests from other agents:
        
        1. Traffic Simulation Requests: Receive requests from Event agents to simulate
           traffic dynamics. Processes "simulate_traffic" action requests, runs the
           simulation for the specified duration, and returns generated traffic events.
        
        2. Time-Delta Requests: Receive requests to advance the simulation by a
           specified number of ticks. Tracks edge weight changes (travel times and
           fuel consumption) during the simulation period and returns detailed
           information about which edges changed and when.
        
        FIPA Protocol Compliance:
        - Implements the FIPA Request interaction protocol
        - Receives REQUEST messages with performative="request"
        - Sends back INFORM messages with performative="inform"
        - Gracefully handles protocol violations with JSON decode errors
        
        This behaviour runs cyclically (continuously) checking for incoming messages
        with a timeout to prevent blocking the agent's other behaviours.
        """
        
        async def run(self):
            """Process time-delta messages and simulate world.
            
            Executes one iteration of the cyclic behaviour. This method:
            1. Waits for incoming messages with a 1-second timeout
            2. If a message is received, parses its JSON content
            3. Identifies the message type (traffic simulation or time-delta)
            4. Routes to appropriate handler based on action metadata
            5. Sends response back to sender with simulation results
            6. Handles exceptions gracefully, logging errors
            
            The method operates on two distinct message types:
            - Traffic Simulation: Calls world.get_events() to simulate traffic
            - Time-Delta: Simulates multiple ticks and tracks edge state changes
            
            For time-delta requests, the behaviour:
            - Records initial edge weights before simulation
            - Executes the requested number of ticks sequentially
            - For each edge that changes, calculates fuel consumption
            - Tracks the tick index where each change occurred
            - Returns complete change history to the requester
            
            Raises:
                json.JSONDecodeError: If message body is invalid JSON (logged, not raised)
                Exception: Any other runtime error (logged, not raised)
            
            Yields:
                None: This cyclic behaviour continues indefinitely
            """
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    # Check if it's a traffic simulation request from event agent
                    if msg.get_metadata("performative") == "request" and msg.get_metadata("action") == "simulate_traffic":
                        content = json.loads(msg.body)
                        simulation_time = content.get("simulation_time", 10)
                        sender = str(msg.sender)
                        
                        print(f"\n[{self.agent.name}] Traffic simulation request received")
                        print(f"  Sender: {sender}")
                        print(f"  Simulation time: {simulation_time}s")
                        
                        # Simulate traffic events using get_events
                        events = self.agent.world.get_events(int(simulation_time))
                        
                        print(f"[{self.agent.name}] Simulation completed: {len(events)} events generated")
                        
                        # Send response with traffic events (FIPA Inform)
                        response = Message(to=sender)
                        response.set_metadata("performative", "inform")
                        response.set_metadata("action", "traffic_events")
                        response.body = json.dumps({
                            "events": events,
                            "simulation_time": simulation_time
                        })
                        await self.send(response)
                        
                        print(f"[{self.agent.name}] Traffic events sent to {sender}\n")
                        return
                    
                    # Handle normal time-delta requests (FIPA Request/Response pattern)
                    content = json.loads(msg.body)
                    delta_time = content.get("delta_time", 1)
                    sender = str(msg.sender)
                    
                    print(f"\n[{self.agent.name}] Received time-delta request: {delta_time} ticks from {sender}")
                    
                    # Store initial edge states for change detection
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
                    
                    # Send response with all edge states (FIPA Inform)
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
        """Handles incoming messages from other agents.
        
        This behaviour processes all general query and subscription messages from
        other agents in the supply chain system. It operates as a message dispatcher,
        routing incoming messages to specialized handler methods based on the
        message type field.
        
        Supported message types and their handlers:
        - "query_world_state": Returns complete world simulation state
        - "query_node_info": Returns information about a specific graph node
        - "query_edge_info": Returns information about a specific edge
        - "query_facilities": Returns locations of all supply chain facilities
        - "subscribe": Registers an agent for periodic world state updates
        
        FIPA Protocol Compliance:
        - Processes messages from agents following FIPA protocols
        - Sends INFORM messages (performative="inform") for successful queries
        - Returns ERROR messages for queries that fail or have invalid parameters
        - Handles SUBSCRIBE messages for publish/subscribe pattern coordination
        
        Message Flow:
        1. Receives a message with JSON body containing "type" field
        2. Validates JSON structure and extracts message type
        3. Routes to appropriate private handler method (_handle_*)
        4. Handler method constructs response with agent's data
        5. Response sent back to originating agent
        
        Error Handling:
        - JSON decode errors are logged and ignored
        - Unknown message types are logged with diagnostic info
        - Handler exceptions are caught and logged
        
        This behaviour runs cyclically with a 1-second timeout between iterations.
        """
        
        async def run(self):
            """Process incoming messages.
            
            Executes one iteration of the cyclic message handling. This method:
            1. Waits up to 1 second for an incoming message
            2. If no message arrives within timeout, cycles immediately
            3. If a message arrives, attempts to parse it as JSON
            4. Extracts the "type" field to determine message category
            5. Dispatches to the appropriate handler coroutine
            6. Catches and logs any JSON or handler exceptions
            
            The dispatcher pattern allows different message types to be handled
            by specialized methods, keeping this method focused on high-level
            message routing and error handling.
            
            Raises:
                json.JSONDecodeError: If msg.body is not valid JSON (caught, logged)
                Exception: Any handler exception (caught, logged)
            
            Yields:
                None: Continues indefinitely as a cyclic behaviour
            """
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
            """Handle query for complete world state.
            
            Responds to queries requesting the complete world state snapshot.
            Compiles all relevant world information including simulation progress,
            grid dimensions, facility counts, and infected edge statistics.
            
            This handler follows the FIPA Query interaction protocol by:
            - Receiving a query request message
            - Preparing comprehensive state information
            - Sending an INFORM message with the complete state
            
            Args:
                msg (Message): The incoming query message from sender agent.
                    Expected to be of type "query_world_state" in JSON body.
            
            Returns:
                None: Sends response asynchronously via FIPA INFORM message
            
            Response payload includes:
                - tick: Current simulation time step counter
                - width/height: Grid dimensions in the world graph
                - seed: Random seed used for deterministic reproduction
                - mode: Simulation mode (e.g., "traffic" or other modes)
                - num_nodes: Total number of nodes in the supply chain graph
                - num_edges: Total number of edges in the supply chain graph
                - infected_edges: Count of edges currently experiencing traffic
                - gas_stations: Number and IDs of gas station facilities
                - warehouses: Number and IDs of warehouse facilities
                - suppliers: Number and IDs of supplier facilities
                - stores: Number and IDs of store facilities
            """
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
            print(f"[{self.agent.name}] World state sent to {sender}")

        async def _handle_node_query(self, msg):
            """Handle query for information about a specific node.
            
            Responds to queries requesting detailed information about a single node
            in the supply chain graph. The node is identified by its ID in the
            query message. Returns node coordinates, facility affiliations, and
            other node-specific metadata.
            
            FIPA Query/Response Protocol:
            - Receives QUERY message with specific node_id parameter
            - Searches graph for the requested node
            - Returns INFORM message with node data if found
            - Returns ERROR message if node not found
            
            Args:
                msg (Message): The incoming query message from sender agent.
                    Message body must include JSON with:
                    - type: "query_node_info"
                    - node_id: The ID of the node to query
            
            Returns:
                None: Sends FIPA response message (INFORM or ERROR)
            
            Response for successful query:
                - id: The node identifier
                - x: X-coordinate position in the world grid
                - y: Y-coordinate position in the world grid
                - warehouse: Boolean indicating if node hosts a warehouse
                - supplier: Boolean indicating if node hosts a supplier
                - store: Boolean indicating if node hosts a store
                - gas_station: Boolean indicating if node has a gas station
            
            Response for failed query (node not found):
                - type: "error"
                - message: Descriptive error message
            
            Raises:
                Exception: Any runtime error during query processing
                    (caught and reported in error response)
            """
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
                print(f"[{self.agent.name}] Node {node_id} information sent to {sender}")
                
            except Exception as e:
                response = Message(to=sender)
                response.body = json.dumps({
                    "type": "error",
                    "message": str(e)
                })
                await self.send(response)

        async def _handle_edge_query(self, msg):
            """Handle query for information about edges.
            
            Responds to queries requesting detailed information about a specific edge
            in the supply chain graph. The edge is identified by its two endpoint nodes
            (node_u and node_v). Returns edge properties including traversal time,
            distance, fuel consumption, and infection status.
            
            FIPA Query/Response Protocol:
            - Receives QUERY message with node_u and node_v parameters
            - Looks up edge in graph using get_edge() method
            - Returns INFORM message with edge data if found
            - Returns ERROR message if edge not found
            
            Args:
                msg (Message): The incoming query message from sender agent.
                    Message body must include JSON with:
                    - type: "query_edge_info"
                    - node_u: Source node ID
                    - node_v: Destination node ID
            
            Returns:
                None: Sends FIPA response message (INFORM or ERROR)
            
            Response for successful query:
                - node_u: Source node ID
                - node_v: Destination node ID
                - weight: Current edge weight (travel time in current tick)
                - initial_weight: Original edge weight from graph initialization
                - distance: Geometric distance between nodes
                - fuel_consumption: Fuel needed to traverse this edge
                - is_infected: Boolean indicating if edge has traffic/infection
            
            Response for failed query (edge not found):
                - type: "error"
                - message: Descriptive error message
            
            Raises:
                Exception: Any runtime error during query processing
                    (caught and reported in error response)
            """
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
                print(f"[{self.agent.name}] Edge ({node_u}, {node_v}) information sent to {sender}")
                
            except Exception as e:
                response = Message(to=sender)
                response.body = json.dumps({
                    "type": "error",
                    "message": str(e)
                })
                await self.send(response)

        async def _handle_facilities_query(self, msg):
            """Handle query for facility locations.
            
            Responds to queries requesting the complete list of all supply chain
            facility locations organized by type. This includes warehouses, suppliers,
            gas stations, and stores. The facilities are represented by their node IDs
            in the supply chain graph.
            
            FIPA Query/Response Protocol:
            - Receives QUERY message for facility locations
            - Iterates through all nodes in graph checking facility flags
            - Returns INFORM message with categorized facility lists
            
            This query is useful for agents that need to plan routes or coordinate
            with specific facility types without needing full node data.
            
            Args:
                msg (Message): The incoming query message from sender agent.
                    Expected to be of type "query_facilities" in JSON body.
            
            Returns:
                None: Sends FIPA INFORM message with facilities categorized by type
            
            Response payload structure:
                - warehouses: List of node IDs hosting warehouse facilities
                - suppliers: List of node IDs hosting supplier facilities
                - stores: List of node IDs hosting store facilities
                - gas_stations: List of node IDs hosting gas station facilities
            
            Note:
                A single node can host multiple facilities simultaneously.
                Facilities are identified based on boolean flags on node objects.
            """
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
            print(f"[{self.agent.name}] Facilities information sent to {sender}")

        async def _handle_subscribe(self, msg):
            """Handle subscription requests for world state updates.
            
            Processes subscription requests from agents that wish to receive
            periodic world state update broadcasts. When an agent subscribes,
            it is added to the WorldAgent's subscriber list and will receive
            INFORM messages whenever the world state changes significantly
            (e.g., when new traffic events occur).
            
            FIPA Publish/Subscribe Pattern:
            - Receives SUBSCRIBE message from requesting agent
            - Validates agent is not already subscribed (prevents duplicates)
            - Adds agent JID to internal subscriber list
            - Sends confirmation message back to subscriber
            
            The subscription mechanism allows agents to stay informed about
            world state changes without polling for updates.
            
            Args:
                msg (Message): The incoming subscription request message.
                    Expected to be of type "subscribe" in JSON body.
            
            Returns:
                None: Adds sender to subscribers and sends confirmation
            
            Side Effects:
                - Adds sender JID to self.agent.subscribers list
                - Logs subscription confirmation message
            
            Confirmation Response:
                - type: "subscription_confirmed"
                - performative: "confirm"
            
            Once subscribed, the agent will receive messages via
            _broadcast_world_state() when updates are available.
            """
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
        """Broadcast world state to all subscribed agents.
        
        Sends a world state update message to all agents that have subscribed
        to receive periodic updates. This implements the Publish/Subscribe pattern
        from FIPA interactions, allowing multiple consumer agents to receive
        notifications about world state changes without polling.
        
        FIPA Publish/Subscribe Pattern:
        - Sends INFORM messages to all subscribed agents
        - Includes current simulation tick and infected edge count
        - Called whenever significant world state changes occur
        
        Message Structure:
        Each broadcast message contains:
        - type: "world_tick_update" identifying the message type
        - tick: Current simulation time counter
        - infected_edges: Current count of traffic-affected edges
        
        This method iterates through self.subscribers list and sends a copy
        of the world update message to each subscriber independently. If a
        subscriber is no longer available, the XMPP server will handle the
        delivery failure appropriately.
        
        Args:
            None: Uses self.world and self.subscribers from agent instance
        
        Returns:
            None: Sends messages asynchronously, does not wait for delivery
        
        Side Effects:
            - Sends XMPP MESSAGE stanzas to all subscribers
            - Does not modify agent state
        """
        world_update = {
            "type": "world_tick_update",
            "tick": self.world.tick_counter,
            "infected_edges": len(self.world.graph.infected_edges),
        }
        
        for subscriber in self.subscribers:
            msg = Message(to=subscriber)
            msg.set_metadata("performative", "inform")
            msg.body = json.dumps(world_update)
            await self.send(msg)

    async def setup(self):
        """Set up the WorldAgent with its behaviors.
        
        Initializes the WorldAgent by configuring all required attributes,
        validating the world instance, and registering the agent's behaviours.
        This method is called once when the agent starts, before it begins
        processing messages or executing behaviours.
        
        SPADE Agent Lifecycle:
        - Called automatically by SPADE after agent initialization
        - Must call parent's setup if overriding (implicitly done via parent)
        - Should register all behaviours before returning
        
        Initialization Steps:
        1. Initialize subscribers list if not already present
        2. Initialize tick_interval (seconds between simulation steps)
        3. Verify World instance is properly set
        4. Log diagnostic information about world configuration
        5. Register TimeDeltaBehaviour with template for specific messages
        6. Register MessageHandlerBehaviour for general message handling
        
        Behaviours Registered:
        - TimeDeltaBehaviour: Handles time-delta requests and traffic simulation
          This behaviour uses a template to match messages with specific metadata
        - MessageHandlerBehaviour: Routes incoming queries to specialized handlers
          This behaviour runs without template, accepting all remaining messages
        
        Warning Conditions:
        - If world is None, agent will be non-functional but will start
        - Logs diagnostic warnings to help identify configuration issues
        
        Args:
            None: Uses self attributes set during __init__
        
        Returns:
            None: Configures agent in-place and returns
        
        Side Effects:
            - Initializes self.subscribers to empty list
            - Sets self.tick_interval to 2 seconds (default)
            - Registers behaviours with the SPADE framework
            - Prints diagnostic setup information
        """
        print(f"[{self.name}] Setting up WorldAgent...")
        
        # Initialize agent attributes if not set
        if not hasattr(self, 'subscribers'):
            self.subscribers = []
        if not hasattr(self, 'tick_interval'):
            self.tick_interval = 2  # Seconds between world ticks
        
        if self.world is not None:
            print(f"[{self.name}] World instance provided")
            print(f"[{self.name}] Grid: {self.world.width}x{self.world.height}")
            print(f"[{self.name}] Seed: {self.world.seed}")
        else:
            print(f"[{self.name}] WARNING: No World instance provided!")
        
        # Add time-delta behaviour with template
        template = Template()
        template.set_metadata("performative", "request")
        template.metadata = {"performative": "request"}
        self.add_behaviour(self.TimeDeltaBehaviour(), template)
        
        self.add_behaviour(self.MessageHandlerBehaviour())
        
        print(f"[{self.name}] WorldAgent setup complete!")


async def main():
    """Main entry point for the WorldAgent.
    
    Initializes and starts the WorldAgent instance, handling its lifecycle
    from startup through shutdown. This is the entry function used when
    running the WorldAgent as a standalone SPADE agent.
    
    Prerequisites:
    - An XMPP server (such as ejabberd) must be running and accessible
    - Default configuration uses localhost:5222 (standard XMPP port)
    - An agent account must exist on the XMPP server with matching JID/password
    
    Configuration:
    - Agent JID: "world@localhost" (change to match your XMPP server)
    - Password: "password" (change to match registered account)
    - Server: localhost (default XMPP configuration)
    
    Lifecycle:
    1. Creates a new WorldAgent instance
    2. Calls start() to initialize the agent on XMPP server
    3. Enters infinite loop to keep agent running
    4. On KeyboardInterrupt (Ctrl+C), cleanly stops the agent
    5. Handles any exceptions during execution
    
    Error Handling:
    - KeyboardInterrupt: Graceful shutdown with cleanup
    - Other Exceptions: Logged and agent stopped with cleanup
    
    Args:
        None: Entry function with no parameters
    
    Returns:
        None: Async coroutine, called via spade.run()
    
    Usage:
        Run via: python world_agent.py
        Stop via: Press Ctrl+C in terminal
    
    Note:
        This function is called by spade.run() which manages the asyncio event loop
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
