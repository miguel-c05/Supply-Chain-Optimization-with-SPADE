"""Event-driven agent system for supply chain simulation.

This module implements an event management system based on temporal priorities,
using a min heap data structure to efficiently order and process events.
The agent is responsible for receiving, storing, and distributing events related to
supply chain simulation, including vehicle arrival events, traffic changes, and other
temporal occurrences.

The system follows FIPA (Foundation for Intelligent Physical Agents) standards for
agent communication, utilizing XMPP as the transport protocol and ACL (Agent Communication
Language) performatives for message semantics.

Classes:
    Event: Represents an individual event with type, time, and associated data.
    EventDrivenAgent: SPADE agent that manages the event heap and processes periodically.

FIPA Compliance:
    - Uses FIPA ACL performatives (inform, request) in message metadata
    - Follows FIPA interaction protocols for agent communication
    - Implements presence-based subscription model for agent discovery
    - Uses XMPP (Extensible Messaging and Presence Protocol) as transport layer

Dependencies:
    - asyncio: Asynchronous I/O operations
    - heapq: Heap data structure for efficient ordering
    - json: Message serialization
    - typing: Type annotations
    - spade: Multi-agent system framework

Examples:
    >>> # Create and start an event-driven agent
    >>> event_agent = EventDrivenAgent(
    ...     jid="event_agent@localhost",
    ...     password="password",
    ...     simulation_interval=5.0,
    ...     registered_vehicles=["vehicle1@localhost"],
    ...     registered_warehouses=["warehouse1@localhost"],
    ...     registered_stores=["store1@localhost"],
    ...     registered_suppliers=["supplier1@localhost"],
    ...     world_agent="world@localhost",
    ...     world_simulation_time=10.0,
    ...     verbose=True
    ... )
    >>> await event_agent.start()

Note:
    This module requires a running XMPP server (e.g., Openfire, Prosody, ejabberd)
    and properly registered agent accounts for communication.

Version:
    1.0.0

Author:
    Supply Chain Optimization Team
"""

import asyncio
import heapq
import json
from datetime import datetime
from typing import List, Dict, Any
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.presence import PresenceType, PresenceShow
from logger_utils import MessageLogger


class Event:
    """Temporal event representation for supply chain simulation.
    
    This class encapsulates information about events that occur at specific moments
    during the simulation. Events are comparable and orderable by time, allowing
    their use in a min heap structure for chronological processing.
    
    The event system supports various event types representing different occurrences
    in the supply chain:
        - **arrival**: Vehicle arrival at a node (warehouse, store, gas station)
        - **transit**: Traffic condition changes on a graph edge
        - **updatesimulation**: Request for traffic simulation update
        - Custom types as needed by the simulation
    
    Comparison operations are based solely on the `time` attribute, implementing
    a total ordering for heap-based priority queue operations.
    
    Attributes:
        event_type (str): Type of event (e.g., "arrival", "transit", "updatesimulation").
            Defines the processing behavior and data structure expected.
        time (float): Event occurrence time in simulation seconds. Used for
            heap ordering - lower values have higher priority.
        data (Dict[str, Any]): Event-specific data dictionary. Structure varies by type:
            - arrival: {"location": str, "vehicle": str}
            - transit: {"edges": List[Dict], "node1": int, "node2": int, "weight": float}
            - updatesimulation: {"action": str}
        sender (str, optional): Full JID of the sending agent (format: "name@server").
            None for internal or system-generated events.

    Examples:
        >>> # Create vehicle arrival event
        >>> arrival_event = Event(
        ...     event_type="arrival",
        ...     time=15.5,
        ...     data={"location": "warehouse_1"},
        ...     sender="vehicle1@localhost"
        ... )
        >>> 
        >>> # Create traffic change event
        >>> transit_event = Event(
        ...     event_type="transit",
        ...     time=20.0,
        ...     data={
        ...         "edges": [{
        ...             "node1": 5,
        ...             "node2": 8,
        ...             "weight": 12.3,
        ...             "fuel_consumption": 2.5
        ...         }]
        ...     }
        ... )
        >>> 
        >>> # Compare events by time
        >>> arrival_event < transit_event
        True
        >>> 
        >>> # Use in heap
        >>> import heapq
        >>> heap = []
        >>> heapq.heappush(heap, transit_event)
        >>> heapq.heappush(heap, arrival_event)
        >>> next_event = heapq.heappop(heap)  # Returns arrival_event (earlier time)
    
    Note:
        Event comparison is performed exclusively based on the `time` attribute.
        Events with the same time are considered equal for ordering purposes,
        but may have different types and data content.
        
        This design follows the principle of temporal consistency in discrete
        event simulation systems.
    """
    
    def __init__(self, event_type: str, time: float, data: Dict[str, Any], 
                 sender: str = None):
        """Initialize a new event instance.
        
        Creates an event object with specified type, temporal occurrence, associated data,
        and optional sender identification. This constructor performs no validation,
        relying on the caller to provide semantically correct values.
        
        Args:
            event_type (str): Event type identifier. Common values include "arrival",
                "transit", "updatesimulation". Determines event processing behavior
                and expected data structure.
            time (float): Event occurrence time in simulation seconds. Used for
                heap ordering - lower values indicate higher priority and earlier
                processing. Must be non-negative.
            data (Dict[str, Any]): Event-specific data dictionary. Structure varies
                by event type:
                - **arrival**: {"location": str, "vehicle": str} - Location and vehicle ID
                - **transit**: {"edges": List[Dict], "node1": int, "node2": int, 
                  "weight": float, "fuel_consumption": float} - Graph edge updates
                - **updatesimulation**: {"action": str, "requester": str} - Simulation requests
            sender (str, optional): Full JID of sending agent in format "name@server".
                None indicates internal/system-generated event. Defaults to None.
        
        Examples:
            >>> # Simple arrival event
            >>> event = Event("arrival", 10.5, {"vehicle": "v1"}, "vehicle1@localhost")
            >>> event.time
            10.5
            >>> event.event_type
            'arrival'
            >>> 
            >>> # Transit event without sender (system-generated)
            >>> transit = Event("transit", 5.0, {"edges": [...]})
            >>> transit.sender is None
            True
        
        Note:
            The constructor does not validate event_type values or data structure.
            Validation should be performed by event processors based on type.
        """
        self.event_type = event_type  # Event type: "arrival", "transit", etc.
        self.time = time  # Event occurrence time
        self.data = data  # Event-specific data payload
        self.sender = sender  # Originating agent JID
    
    def __lt__(self, other):
        """Less-than comparison operator for min heap ordering.
        
        Implements the less-than comparison required by Python's heapq module
        for maintaining min heap invariant. Events with earlier times have
        higher priority and are processed first.
        
        Args:
            other (Event): Another event instance for comparison.
        
        Returns:
            bool: True if this event has earlier time (higher priority),
                False otherwise.
        
        Examples:
            >>> early = Event("arrival", 5.0, {})
            >>> late = Event("transit", 10.0, {})
            >>> early < late
            True
            >>> late < early
            False
        
        Note:
            This method is essential for heapq module functionality.
            Events with lower time values are processed first (min heap property).
            Only the time attribute is compared; other attributes are ignored.
        """
        return self.time < other.time
    
    def __le__(self, other):
        """Less-than-or-equal comparison operator.
        
        Compares events based on their temporal occurrence, supporting
        sorting and filtering operations.
        
        Args:
            other (Event): Another event instance for comparison.
        
        Returns:
            bool: True if this event occurs at or before the other event.
        
        Examples:
            >>> e1 = Event("arrival", 5.0, {})
            >>> e2 = Event("transit", 5.0, {})
            >>> e1 <= e2
            True
        """
        return self.time <= other.time
    
    def __gt__(self, other):
        """Greater-than comparison operator.
        
        Compares events based on temporal occurrence for reverse ordering
        and filtering operations.
        
        Args:
            other (Event): Another event instance for comparison.
        
        Returns:
            bool: True if this event occurs after the other event.
        
        Examples:
            >>> late = Event("arrival", 10.0, {})
            >>> early = Event("transit", 5.0, {})
            >>> late > early
            True
        """
        return self.time > other.time
    
    def __ge__(self, other):
        """Greater-than-or-equal comparison operator.
        
        Compares events based on temporal occurrence, supporting
        sorting and filtering in descending order.
        
        Args:
            other (Event): Another event instance for comparison.
        
        Returns:
            bool: True if this event occurs at or after the other event.
        
        Examples:
            >>> e1 = Event("arrival", 5.0, {})
            >>> e2 = Event("transit", 5.0, {})
            >>> e1 >= e2
            True
        """
        return self.time >= other.time
    
    def __eq__(self, other):
        """Equality comparison operator.
        
        Determines if two events occur at the same simulation time.
        Note that events are considered equal for ordering purposes even
        if they have different types or data content.
        
        Args:
            other (Event): Another event instance for comparison.
        
        Returns:
            bool: True if events have identical occurrence time.
        
        Examples:
            >>> e1 = Event("arrival", 5.0, {"a": 1})
            >>> e2 = Event("transit", 5.0, {"b": 2})
            >>> e1 == e2
            True
        
        Note:
            Only the time attribute is compared. Events with same time but
            different types are considered equal for ordering purposes.
            This design enables simultaneous processing of concurrent events.
        """
        return self.time == other.time
    
    def __repr__(self):
        """Return string representation of event for debugging.
        
        Provides a human-readable representation including event type,
        occurrence time, and sender information. Useful for logging,
        debugging, and interactive inspection.
        
        Returns:
            str: Formatted string with key event information in format:
                "Event(type=<type>, time=<time>, sender=<sender>)"
                Time is formatted to 2 decimal places.
        
        Examples:
            >>> event = Event("arrival", 15.5, {}, "vehicle1@localhost")
            >>> repr(event)
            'Event(type=arrival, time=15.50, sender=vehicle1@localhost)'
            >>> 
            >>> print(event)
            Event(type=arrival, time=15.50, sender=vehicle1@localhost)
        
        Note:
            The data attribute is not included in the representation to
            keep output concise. Use event.data for full details.
        """
        return f"Event(type={self.event_type}, time={self.time:.2f}, sender={self.sender})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary format for XMPP message transmission.
        
        Serializes the event into a format suitable for sending through the SPADE
        messaging system. The dictionary structure varies by event type to optimize
        data transmission and maintain FIPA ACL compliance.
        
        This method follows FIPA principles by creating a structured content format
        that can be embedded in FIPA ACL message bodies.
        
        Returns:
            Dict[str, Any]: Dictionary with fields appropriate to event type:
                - **arrival**: {"type": str, "time": float, "vehicle": str}
                  Vehicle name extracted from sender JID (before '@').
                - **transit**: {"type": str, "time": float, "data": Dict}
                  Complete data payload including edge updates.
                - **other types**: {"type": str, "time": float, "data": Dict}
                  Generic structure with full data content.
        
        Examples:
            >>> # Arrival event serialization
            >>> arrival_event = Event("arrival", 10.5, {}, "vehicle1@localhost")
            >>> arrival_event.to_dict()
            {'type': 'arrival', 'time': 10.5, 'vehicle': 'vehicle1'}
            >>>
            >>> # Transit event serialization
            >>> transit_event = Event("transit", 5.0, {"edges": [...]})
            >>> transit_event.to_dict()
            {'type': 'transit', 'time': 5.0, 'data': {'edges': [...]}}
            >>>
            >>> # Custom event serialization
            >>> custom_event = Event("custom", 3.0, {"key": "value"})
            >>> custom_event.to_dict()
            {'type': 'custom', 'time': 3.0, 'data': {'key': 'value'}}
        
        Note:
            For arrival events, the vehicle name is extracted from the sender JID
            (portion before '@'). For transit events, all data is included.
            This serialization format is designed for JSON encoding and XMPP
            message transmission.
        
        FIPA Compliance:
            The returned dictionary serves as the content of FIPA ACL messages,
            providing structured semantic information that agents can interpret
            according to the event type.
        """
        if self.event_type == "arrival":
            return {
                "type": self.event_type,
                "time": self.time,
                "vehicle": self.sender.split('@')[0],
            }
        elif self.event_type == "Transit" or self.event_type == "transit":
            return {
                "type": self.event_type,
                "time": self.time,
                "data": self.data
            }
        else:
            return {
                "type": self.event_type,
                "time": self.time,
                "data": self.data
            }


class EventDrivenAgent(Agent):
    """Event-driven agent managing temporal simulation with heap-based priority queue.
    
    This agent serves as the core of the event management system for supply chain simulation.
    It uses a min heap data structure to maintain events ordered by time and processes them
    periodically at configurable intervals. The agent coordinates communications between
    vehicles, warehouses, stores, suppliers, and the world agent, ensuring all participants
    receive relevant event notifications.
    
    The agent implements FIPA (Foundation for Intelligent Physical Agents) standards for
    multi-agent communication, using XMPP as transport protocol and ACL performatives
    for semantic message exchange.
    
    Architecture:
        - **Min Heap**: Stores general events ordered by time (O(log n) operations)
        - **Transit Events List**: Separate list for traffic change events with temporal decay
        - **Arrival Events Buffer**: Temporary buffer for vehicle arrival grouping
        - **Behaviours**: Set of asynchronous behaviours executing different functionalities:
            * ReceiveEventsBehaviour: Continuous message reception (CyclicBehaviour)
            * ProcessEventsBehaviour: Periodic event processing (PeriodicBehaviour)
            * SendInitialSignalBehaviour: Initial system activation (PeriodicBehaviour)
            * RegisterTransitBehaviour: Initial traffic simulation request (OneShotBehaviour)
    
    Workflow:
        1. **Initialization**: Subscribe all registered agents and send initial signal
        2. **Continuous Reception**: Cyclic behaviour receives events from all agents
        3. **Periodic Processing**: At each interval, process events from heap
        4. **Notification**: Distribute processed events to appropriate agents
        5. **Resimulation**: Request new traffic simulation when needed
    
    Attributes:
        event_heap (List[Event]): Min heap of general events ordered by time.
        transit_events (List[Event]): Separate list for active traffic events with time decay.
        arrival_events (List[Event]): Temporary buffer for vehicle arrival events.
        simulation_interval (float): Interval in seconds between processing cycles.
        registered_vehicles (List[str]): JIDs of vehicles registered in the system.
        registered_warehouses (List[str]): JIDs of registered warehouses.
        registered_stores (List[str]): JIDs of registered stores.
        registered_suppliers (List[str]): JIDs of registered suppliers.
        world_agent (str): JID of the world agent for traffic simulation.
        world_simulation_time (float): Duration in seconds of each traffic simulation.
        event_count (int): Total counter of events received.
        processed_count (int): Total counter of events processed.
        last_simulation_time (float): Timestamp of last processed simulation.
        time_simulated (float): Total accumulated simulation time.
        verbose (bool): Flag to enable detailed logging.
        first_arrival_received (bool): Flag indicating if first arrival has been received.
        initial_signal_behaviour (PeriodicBehaviour): Reference to initial signal behaviour.
    
    Behaviours:
        SendInitialSignalBehaviour: Sends initial signal to vehicles (PeriodicBehaviour).
        RegisterTransitBehaviour: Requests initial traffic simulation (OneShotBehaviour).
        ReceiveEventsBehaviour: Receives events continuously (CyclicBehaviour).
        ProcessEventsBehaviour: Processes events periodically (PeriodicBehaviour).
    
    Examples:
        >>> # Create event agent with basic configuration
        >>> event_agent = EventDrivenAgent(
        ...     jid="event_agent@localhost",
        ...     password="password123",
        ...     simulation_interval=5.0,
        ...     registered_vehicles=["vehicle1@localhost", "vehicle2@localhost"],
        ...     registered_warehouses=["warehouse1@localhost"],
        ...     registered_stores=["store1@localhost"],
        ...     registered_suppliers=["supplier1@localhost"],
        ...     world_agent="world@localhost",
        ...     world_simulation_time=10.0,
        ...     verbose=True
        ... )
        >>> 
        >>> # Start the agent
        >>> await event_agent.start()
        >>> 
        >>> # The agent will:
        >>> # 1. Subscribe all registered agents
        >>> # 2. Send initial signal to vehicles
        >>> # 3. Request traffic simulation from world agent
        >>> # 4. Receive and process events continuously
    
    Note:
        The agent uses a hybrid processing strategy:
        - Transit events are kept separate with time decremented each cycle
        - Arrival events are grouped before processing for efficiency
        - General events are processed in strict temporal order
        
        Only events with the same time as the first event in heap are processed
        in each cycle, ensuring correct temporal synchronization.
    
    FIPA Compliance:
        - Uses FIPA ACL performatives in message metadata ("inform", "request")
        - Follows FIPA interaction protocols for agent coordination
        - Implements presence-based subscription for agent discovery (XMPP)
        - Content is encoded as JSON for interoperability
        - Sender and receiver identification through JIDs (Jabber IDs)
    
    Warning:
        The agent requires a running XMPP server before initialization.
        All registered JIDs must exist and be accessible for communication.
    
    """
    
    def __init__(self, jid: str, password: str, simulation_interval: float, registered_vehicles: List[str],
                 registered_warehouses: List[str], registered_stores: List[str] ,registered_suppliers: List[str],
                 world_agent: str, world_simulation_time: float, verbose: bool):
        """Initialize EventDrivenAgent with simulation settings and registered agents.
        
        Creates an event-driven agent instance configured for supply chain simulation
        with specified processing interval and registered agent participants. This
        constructor initializes all data structures but does not start behaviours or
        subscribe agents - those actions occur in the setup() method.
        
        Args:
            jid (str): Complete Jabber ID of the agent (format: "name@server").
                Must be registered on the XMPP server before use.
            password (str): Password for XMPP server authentication.
            simulation_interval (float): Interval in seconds between event processing
                cycles. Typical values: 1.0 to 10.0 seconds. Determines temporal
                granularity of the simulation.
            registered_vehicles (List[str]): List of vehicle JIDs participating in
                simulation. These agents will receive event notifications and
                traffic updates.
            registered_warehouses (List[str]): List of registered warehouse JIDs.
                Warehouses receive transit events for route optimization.
            registered_stores (List[str]): List of registered store JIDs.
                Stores receive traffic updates for delivery planning.
            registered_suppliers (List[str]): List of registered supplier JIDs.
                Suppliers receive event notifications for supply coordination.
            world_agent (str): JID of the world agent responsible for traffic simulation.
                If None, traffic simulation features are disabled.
            world_simulation_time (float): Duration in seconds of each traffic simulation
                requested from world agent. Determines temporal forecasting horizon.
            verbose (bool): If True, enable detailed logs for debugging and monitoring.
                If False, only essential messages are displayed.
        
        Examples:
            >>> # Small simulation configuration with 2 vehicles
            >>> agent = EventDrivenAgent(
            ...     jid="events@localhost",
            ...     password="pass123",
            ...     simulation_interval=5.0,
            ...     registered_vehicles=["v1@localhost", "v2@localhost"],
            ...     registered_warehouses=["w1@localhost"],
            ...     registered_stores=["s1@localhost", "s2@localhost"],
            ...     registered_suppliers=["sup1@localhost"],
            ...     world_agent="world@localhost",
            ...     world_simulation_time=15.0,
            ...     verbose=False
            ... )
            >>> 
            >>> # Large simulation configuration with detailed logging
            >>> agent_verbose = EventDrivenAgent(
            ...     jid="events@localhost",
            ...     password="pass123",
            ...     simulation_interval=2.0,
            ...     registered_vehicles=[f"vehicle{i}@localhost" for i in range(10)],
            ...     registered_warehouses=[f"warehouse{i}@localhost" for i in range(5)],
            ...     registered_stores=[f"store{i}@localhost" for i in range(20)],
            ...     registered_suppliers=[f"supplier{i}@localhost" for i in range(3)],
            ...     world_agent="world@localhost",
            ...     world_simulation_time=30.0,
            ...     verbose=True
            ... )
        
        Note:
            The constructor only initializes data structures. Agent subscription
            and behaviour initialization occur in the setup() method, which is
            called automatically by SPADE framework when start() is invoked.
        """
        super().__init__(jid, password)
        self.event_heap = []  # Min heap of events (non-transit)
        self.transit_events = []  # Separate list for transit events
        self.arrival_events = []  # Separate list for arrival events
        self.simulation_interval = simulation_interval  # Simulation interval (e.g., 5s)
        self.registered_vehicles = registered_vehicles  # Registered vehicles
        self.registered_warehouses = registered_warehouses  # Registered warehouses
        self.registered_stores = registered_stores  # Registered stores
        self.registered_suppliers = registered_suppliers  # Registered suppliers
        self.world_agent = world_agent  # World agent JID
        self.world_simulation_time = world_simulation_time  # World simulation duration
        self.event_count = 0  # Counter of events received
        self.processed_count = 0  # Counter of events processed
        self.last_simulation_time = 0.0  # Last simulation timestamp
        self.time_simulated = 0.0  # Total simulated time
        self.verbose = verbose  # Verbose mode flag
        self.first_arrival_received = False  # Flag for first arrival received
        self.initial_signal_behaviour = None  # Reference to initial signal behaviour
    async def setup(self):
        """Configure and initialize all behaviours and agent subscriptions.
        
        This method is called automatically by the SPADE framework when the agent
        is started. It configures XMPP presence, subscribes all registered agents,
        and adds the necessary behaviours for system operation.
        
        Initialization Sequence:
            1. Set presence as available (AVAILABLE/CHAT) following XMPP protocol
            2. Automatically approve all subscription requests (trust model)
            3. Subscribe vehicles, warehouses, stores, suppliers, and world agent
            4. Add ReceiveEventsBehaviour for continuous message reception
            5. Add SendInitialSignalBehaviour (periodic until first arrival)
            6. Add RegisterTransitBehaviour to request initial traffic simulation
            7. Add ProcessEventsBehaviour for periodic event processing
        
        FIPA Compliance:
            Uses XMPP presence mechanism for agent discovery and availability,
            which aligns with FIPA's agent management specifications.
        
        Raises:
            SPADEException: If there are problems with XMPP connection or subscription.
        
        Note:
            The order of behaviour addition is important. The initial signal and
            traffic simulation request should execute before processing begins.
            
            The agent sets presence.approve_all = True to automatically accept
            all subscription requests, implementing a trust-based agent society.
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"[{self.name}] Event-Driven Agent started")
            print(f"[{self.name}] Simulation interval: {self.simulation_interval}s")
            print(f"[{self.name}] World simulation time: {self.world_simulation_time}s")
            print(f"{'='*70}\n")
        else:
            print(f"[{self.name}] Event-Driven Agent started")
        self.presence.approve_all = True
        
        # Subscribe each agent individually
        all_agents = self.registered_vehicles + self.registered_warehouses + self.registered_stores
        if self.world_agent:
            all_agents.append(self.world_agent)
        
        for agent_jid in all_agents:
            self.presence.subscribe(agent_jid)
        
        self.presence.set_presence(PresenceType.AVAILABLE, PresenceShow.CHAT)
        
        # Behaviour to continuously receive events (must be active from the start)
        receive_behaviour = self.ReceiveEventsBehaviour()
        self.add_behaviour(receive_behaviour)
        
        # Behaviour to send initial signal periodically (until first arrival received)
        self.initial_signal_behaviour = self.SendInitialSignalBehaviour(period=10)  # Send every 10s
        self.add_behaviour(self.initial_signal_behaviour)
        
        # Behaviour to register transit (request initial traffic simulation)
        transit_registration_behaviour = self.RegisterTransitBehaviour()
        self.add_behaviour(transit_registration_behaviour)
        
        # Periodic behaviour to process events (every X seconds)
        # Will start only after receiving first arrival
        process_behaviour = self.ProcessEventsBehaviour(period=self.simulation_interval)
        self.add_behaviour(process_behaviour)
    
    class RegisterTransitBehaviour(OneShotBehaviour):
        """One-shot behaviour requesting initial traffic simulation.
        
        This behaviour executes only once during EventDrivenAgent initialization,
        sending a request to the world agent to simulate traffic conditions for a
        specified period. The initial simulation is crucial for having transit data
        available before event processing begins.
        
        The behaviour follows FIPA Request interaction protocol, where this agent
        acts as the initiator sending a REQUEST performative to the world agent
        (participant), which will respond with traffic event data.
        
        Workflow:
            1. Wait for agent to be fully initialized
            2. Create request message with performative "request"
            3. Set action as "simulate_traffic"
            4. Send simulation time and requester JID
            5. World agent responds with transit events
        
        Attributes:
            Inherits attributes from OneShotBehaviour (no own attributes).
        
        Message Format (FIPA ACL compliant):
            Metadata:
                performative: "request"
                action: "simulate_traffic"
            Body (JSON):
                {
                    "simulation_time": float,  # Simulation duration in seconds
                    "requester": str           # Event agent JID
                }
        
        FIPA Compliance:
            Implements FIPA Request Interaction Protocol:
            - Initiator: EventDrivenAgent (this behaviour)
            - Participant: WorldAgent
            - Performative: REQUEST
            - Expected response: INFORM with traffic events
        
        Note:
            The world agent response is processed by ReceiveEventsBehaviour,
            which adds transit events to the transit_events list.
        """
        
        async def run(self):
            """Execute traffic simulation request to world agent.
            
            Sends an XMPP message to the world agent requesting traffic condition
            simulation. The world agent will process the request and respond with
            a list of transit events that will be received by ReceiveEventsBehaviour.
            
            This method implements the REQUEST performative of FIPA ACL, initiating
            a request-response interaction pattern.
            
            Raises:
                SPADEException: If message sending fails.
            
            Note:
                This method executes only once. Subsequent simulation requests
                are managed by "updatesimulation" type events in the heap.
                
            FIPA Compliance:
                Sends REQUEST performative with structured content following
                FIPA ACL semantics for service requests.
            """
            if self.agent.verbose:
                print(f"\n{'='*70}")
                print(f"[{self.agent.name}] 🌍 REQUESTING TRAFFIC SIMULATION FROM WORLD AGENT")
                print(f"  Recipient: {self.agent.world_agent}")
                print(f"  Simulation time: {self.agent.world_simulation_time}s")
                print(f"{'='*70}\n")
            else:
                print(f"[{self.agent.name}] 🌍 REQUESTING TRAFFIC SIMULATION FROM WORLD AGENT")
            # Create simulation request message
            msg = Message(to=self.agent.world_agent)
            msg.set_metadata("performative", "request")
            msg.set_metadata("action", "simulate_traffic")
            
            data = {
                "simulation_time": self.agent.world_simulation_time,
                "requester": str(self.agent.jid)
            }
            msg.body = json.dumps(data)
            
            await self.send(msg)
            try:
                msg_logger = MessageLogger.get_instance()
                msg_logger.log_message(
                    sender=str(self.agent.jid),
                    receiver=str(msg.to),
                    message_type="Request",
                    performative="request",
                    body=msg.body
                )
            except Exception:
                pass  # Don't crash on logging errors
            if self.agent.verbose:
                print(f"[{self.agent.name}] ✅ Traffic simulation request sent to world agent")
        
    class SendInitialSignalBehaviour(PeriodicBehaviour):
        """Periodic behaviour for vehicle activation through initial signaling.
        
        This behaviour executes periodically (every 10 seconds) during initialization,
        sending fictitious "arrival" messages to all registered vehicles until the
        first real arrival event is received. The goal is to ensure vehicles are
        active and ready to respond to actual events.
        
        This pattern implements a "heartbeat" or "keep-alive" mechanism to bootstrap
        the simulation, following distributed systems principles for node activation.
        
        Initialization Strategy:
            - Uses fictitious vehicle name ("vehicle_init_signal_999")
            - Event time is 0.1 (near-zero, initial moment)
            - Sends periodically until first real arrival received
            - Terminates automatically when first_arrival_received = True
            - Vehicles ignore the fictitious event but notify event agent
        
        Attributes:
            Inherits attributes from PeriodicBehaviour (period set to 10 seconds).
        
        Message Format (FIPA ACL INFORM):
            Metadata:
                performative: \"inform\"
            Body (JSON):
                {
                    \"type\": \"arrival\",
                    \"vehicle\": \"vehicle_init_signal_999\",  # Fictitious name
                    \"time\": 0.1
                }
        
        Examples:
            >>> # Automatically added in setup() with 10s period
            >>> initial_signal = self.SendInitialSignalBehaviour(period=10.0)
            >>> self.add_behaviour(initial_signal)
        
        Note:
            This mechanism ensures all vehicles are ready to receive events
            before the simulation effectively begins. The behaviour stops
            automatically when the first real arrival is received.
        
        FIPA Compliance:
            Uses INFORM performative to notify vehicles of (fictitious) events,
            implementing a broadcast notification pattern.
        
        Warning:
            If registered_vehicles is empty, behaviour terminates without action
            and emits a warning in the log.
        """
        
        async def run(self):
            """Send initialization signal to all registered vehicles periodically.
            
            Iterates over the list of registered vehicles and sends each one a
            fictitious arrival message. Continues sending until the first real
            arrival is received.
            
            The method implements a broadcast INFORM pattern, notifying all vehicles
            to activate their event reception behaviours.
            
            Returns:
                None: Executes side effects (message sending).
            
            Note:
                The behaviour checks the first_arrival_received flag and terminates
                when it is True. The fictitious name "vehicle_init_signal_999"
                is intentional and should not correspond to any real vehicle.
                
            FIPA Compliance:
                Sends INFORM performatives to all vehicles in a broadcast pattern.
            """
            # Check if first arrival already received
            if self.agent.first_arrival_received:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ✅ First arrival received. Stopping initial signal sending.")
                else:
                    print(f"[{self.agent.name}] ✅ First arrival received.")
                self.kill()  # Stop this behaviour
                return
            
            if not self.agent.registered_vehicles:
                print(f"[{self.agent.name}] ⚠️ No registered vehicles to send initial signal")
                self.kill()
                return
            
            # Use fictitious name that doesn't correspond to any real vehicle
            fictitious_vehicle_name = "vehicle_init_signal_999"
            
            # Send message to ALL registered vehicles
            if self.agent.verbose:
                print(f"\n{'='*70}")
                print(f"[{self.agent.name}] 🚦 SENDING INITIAL SIGNAL (periodic)")
                print(f"  Recipients: {len(self.agent.registered_vehicles)} vehicles")
                print(f"  Vehicle (fictitious): {fictitious_vehicle_name}")
                print(f"  Type: arrival")
                print(f"  Time: 0.1")
                print(f"{'='*70}")
            else:
                print(f"[{self.agent.name}] 🚦 SENDING INITIAL SIGNAL (waiting for real arrival...)")
            
            for vehicle_jid in self.agent.registered_vehicles:
                # Create initial arrival message with near-zero time
                msg = Message(to=vehicle_jid)
                msg.set_metadata("performative", "inform")
                
                data = {
                    "type": "arrival",
                    "vehicle": fictitious_vehicle_name,  # Fictitious name
                    "time": 0.1
                }
                msg.body = json.dumps(data)
                
                await self.send(msg)
                try:
                    msg_logger = MessageLogger.get_instance()
                    msg_logger.log_message(
                        sender=str(self.agent.jid),
                        receiver=str(msg.to),
                        message_type="Request",
                        performative="inform",
                        body=msg.body
                    )
                except Exception:
                    pass  # Don't crash on logging errors
                
                vehicle_name = str(vehicle_jid).split("@")[0]
                if self.agent.verbose:
                    print(f"  → Sent to: {vehicle_name}")
            
            if self.agent.verbose:
                print(f"{'='*70}\n")
    
    class ReceiveEventsBehaviour(CyclicBehaviour):
        """Cyclic behaviour for continuous event reception from multiple sources.
        
        This behaviour remains permanently active, receiving XMPP messages from
        all registered agents (vehicles, warehouses, stores, suppliers, world agent)
        and classifying them into different event categories. Reception is
        non-blocking with 1-second timeout to allow interruptions.
        
        The behaviour implements a message router pattern, directing different
        event types to appropriate data structures for later processing.
        
        Event Types Processed:
            - **Traffic Events**: Transit events from world agent (complete list)
            - **Transit**: Manual traffic condition change events
            - **Arrival**: Vehicle arrival events at nodes
            - **UpdateSimulation**: Traffic resimulation requests
            - **Other**: Generic events added to main heap
        
        Storage Strategy:
            - Transit events → transit_events (separate list)
            - Arrival events (time > 0) → arrival_events (temporary buffer)
            - Arrival events (time = 0) → discarded (initial signal)
            - Other events → event_heap (min heap)
        
        Attributes:
            Inherits attributes from CyclicBehaviour.
        
        Message Formats:
            Traffic Events (from world agent):
                Metadata:
                    performative: \"inform\"
                    action: \"traffic_events\"
                Body (JSON):
                    {
                        \"events\": [
                            {
                                \"instant\": float,
                                \"node1_id\": int,
                                \"node2_id\": int,
                                \"new_time\": float,
                                \"new_fuel_consumption\": float,
                            },
                            ...
                        ]
                    }
            
            Generic Events:
                Metadata:
                    performative: \"inform\"
                Body (JSON):
                    {
                        \"type\": str,
                        \"time\": float,
                        \"data\": Dict[str, Any],
                    }
        
        Examples:
            >>> # Behaviour executes continuously after addition
            >>> receive_behaviour = self.ReceiveEventsBehaviour()
            >>> self.add_behaviour(receive_behaviour)
        
        Note:
            The 1-second timeout allows the behaviour to periodically check
            if it should terminate (e.g., when agent is stopped). Received
            messages are immediately processed and classified.
        
        FIPA Compliance:
            Processes FIPA ACL messages with INFORM performative, acting as
            a receiver in multiple interaction protocols initiated by other agents.
        
        Warning:
            JSON parsing errors are caught and logged, but do not interrupt
            the behaviour. Malformed events are discarded.
        
        See Also:
            ProcessEventsBehaviour: Processes stored events.
            Event: Data structure for representing events.
        """
        
        async def run(self):
            """Cycle of event message reception and classification.
            
            This method executes continuously, awaiting messages with 1-second
            timeout. When a message is received, it identifies the event type
            and stores it in the appropriate data structure.
            
            Processing Flow:
                1. Await message with 1s timeout
                2. Check if it's traffic events response from world agent
                3. If yes, process complete list of transit events
                4. If no, identify individual event type
                5. Store in transit_events, arrival_events, or event_heap
                6. Increment received events counter
            
            Returns:
                None: Executes continuously until behaviour is removed.
            
            Raises:
                Exception: Catches and logs parsing errors without interrupting.
            
            Note:
                For transit events from world agent, also creates an automatic
                resimulation event after world_simulation_time.
                
            FIPA Compliance:
                Receives and processes INFORM performatives from multiple agents,
                implementing receiver role in FIPA interaction protocols.
            """
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    # Verificar se é resposta do world agent com eventos de trânsito
                    if msg.get_metadata("performative") == "inform" and msg.get_metadata("action") == "traffic_events":
                        # Mensagem do world agent com eventos de trânsito
                        data = json.loads(msg.body)
                        events = data.get("events", [])
                        
                        if self.agent.verbose:
                            print(f"\n{'='*70}")
                            print(f"[{self.agent.name}] 🌍 EVENTOS DE TRÂNSITO DO WORLD AGENT RECEBIDOS")
                            print(f"  Total de eventos: {len(events)}")
                            print(f"{'='*70}\n")
                        else:
                            print(f"[{self.agent.name}] 🌍 EVENTOS DE TRÂNSITO DO WORLD AGENT RECEBIDOS")
                        
                        # Processar cada evento de trânsito
                        for event_data in events:
                            # Criar evento de trânsito
                            transit_event = Event(
                                event_type="Transit",
                                time=event_data.get("instant", 0.0),
                                data={
                                    "edges": [{
                                        "node1": event_data.get("node1_id"),
                                        "node2": event_data.get("node2_id"),
                                        "weight": event_data.get("new_time"),
                                        "fuel_consumption": event_data.get("new_fuel_consumption")
                                    }]
                                },
                                sender=str(msg.sender),
                            )
                            
                            # Adicionar à lista de eventos de trânsito
                            self.agent.transit_events.append(transit_event)
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] 📩 Transit event added: Edge ({event_data.get('node1_id')} → {event_data.get('node2_id')}), time={event_data.get('new_time')}, instant={event_data.get('instant')}")
                        
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] ✅ Total transit events: {len(self.agent.transit_events)}")
                        
                        # Criar evento para solicitar nova simulação após world_simulation_time
                        resimulation_event = Event(
                            event_type="updatesimulation",
                            time=self.agent.world_simulation_time,
                            data={"action": "request_new_simulation"},
                            sender=str(self.agent.jid),
                        )
                        heapq.heappush(self.agent.event_heap, resimulation_event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 🔄 Resimulation event added to heap: {resimulation_event}")
                        
                        return
                    
                    # Processar outros eventos normalmente
                    data = json.loads(msg.body)
                    event_type = data.get("type")
                    time = data.get("time", 0.0)
                    event_data = data.get("data", {})
                    
                    # Debug: mostrar dados recebidos
                    if self.agent.verbose:
                        print(f"[{self.agent.name}] 📨 Mensagem recebida:")
                        print(f"   Sender: {msg.sender}")
                        print(f"   Type: {event_type}")
                        print(f"   Time: {time}")
                        print(f"   Data: {event_data}")
                    else:
                        print(f"[{self.agent.name}] 📨 Mensagem recebida de {msg.sender}")
                    
                    # Criar evento
                    event = Event(
                        event_type=event_type,
                        time=time,
                        data=event_data,
                        sender=str(msg.sender),
                    )
                    
                    # Verificar se é evento de trânsito manual (não do world agent)
                    if event_type == "transit" or event_type == "Transit":
                        # Adicionar à lista de trânsito
                        self.agent.transit_events.append(event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 📩 Manual transit event received: {event}")
                            print(f"   Transit events: {len(self.agent.transit_events)}")
                    elif event_type == "arrival":
                            if not self.agent.first_arrival_received:
                                self.agent.first_arrival_received = True
                                if self.agent.verbose:
                                    print(f"[{self.agent.name}] ✅ PRIMEIRO ARRIVAL RECEBIDO! Iniciando processamento da heap.")
                                else:
                                    print(f"[{self.agent.name}] ✅ PRIMEIRO ARRIVAL RECEBIDO!")
                            
                            self.agent.arrival_events.append(event)
                            if self.agent.verbose:
                                print(f"[{self.agent.name}] 📩 Evento ARRIVAL adicionado à lista: {event}")
                                print(f"   Eventos de arrival: {len(self.agent.arrival_events)}")
                    else:
                        # Adicionar à heap outros tipos de eventos
                        heapq.heappush(self.agent.event_heap, event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 📩 Evento recebido: {event}")
                            print(f"   Eventos na heap: {len(self.agent.event_heap)}")
                        else:
                            print(f"[{self.agent.name}] 📩 Evento recebido: {event}")    
                    self.agent.event_count += 1
                
                except Exception as e:
                    print(f"[{self.agent.name}] ❌ Erro ao processar mensagem: {e}")
    
    class ProcessEventsBehaviour(PeriodicBehaviour):
        """Periodic behaviour responsible for temporal event processing.
        
        This behaviour is the core of the temporal simulation system, executing at
        regular intervals (defined by simulation_interval) to process events that
        occur at the same temporal instant. It implements a sophisticated time
        management strategy, ensuring correct synchronization between all events
        and agents.
        
        The behaviour implements a discrete event simulation (DES) approach, where
        time advances in discrete steps and all events at each time step are
        processed simultaneously.
        
        Processing Strategy:
            1. **Arrival Transfer**: Move arrival events from buffer to heap
            2. **Transit Integration**: Reinsert transit events into heap
            3. **Time Selection**: Extract first event (smallest time)
            4. **Grouping**: Collect all events with same time
            5. **Processing**: Notify relevant agents about events
            6. **Transit Update**: Decrement time of remaining transit events
            7. **Cleanup**: Empty heap (discard future events until next cycle)
            8. **Resimulation**: Request new simulation if needed
        
        Time Management:
            - Only events with time equal to first event are processed
            - Transit events have time decremented continuously
            - First event of each type has real time, subsequent ones time 0
            - Avoids duplicate simulation of same temporal interval
        
        Attributes:
            period (float): Interval in seconds between executions (inherited from PeriodicBehaviour).
        
        Notification Flow:
            - Arrival events → All vehicles (grouped message)
            - Transit events → Vehicles + Warehouses + Stores
            - UpdateSimulation events → World agent
        
        Examples:
            >>> # Automatically created in setup() with configurable period
            >>> process_behaviour = self.ProcessEventsBehaviour(period=5.0)
            >>> self.add_behaviour(process_behaviour)
        
        Note:
            Emptying the heap after processing is intentional. It ensures only
            events from the next temporal instant are considered in the next cycle,
            avoiding temporal inconsistencies.
        
        FIPA Compliance:
            Implements FIPA Inform protocol when notifying agents of processed
            events, acting as initiator in broadcast notification patterns.
        
        Warning:
            If the heap is empty, the cycle is skipped. This is normal when there
            are no pending events.
        
        See Also:
            notify_events: Internal method to distribute processed events.
            Event: Event data structure.
        """
        
        async def run(self):
            """Execute one cycle of event processing.
            
            This method is called periodically by SPADE framework at the interval
            defined by simulation_interval. It coordinates all processing steps,
            from heap preparation to agent notification.
            
            Detailed Steps:
                1. **Heap Preparation**:
                   - Transfer arrival_events to event_heap
                   - Reinsert transit_events into heap
                   - Empty temporary buffers
                
                2. **Event Verification**:
                   - If heap empty, terminate cycle
                   - Log state for monitoring
                
                3. **Event Extraction**:
                   - Remove first event (smallest time)
                   - Collect subsequent events with same time
                   - Create list of events to process
                
                4. **Transit Management**:
                   - Remove transit events from separate list
                   - Detect if last transit event was processed
                   - Update time of remaining events
                
                5. **Notification**:
                   - Call notify_events() to distribute to agents
                   - Await send confirmations
                
                6. **Resimulation**:
                   - If last transit event processed
                   - Send new simulation request to world agent
                
                7. **Statistics**:
                   - Update counters
                   - Generate detailed logs if verbose=True
                
                8. **Cleanup**:
                   - Empty event_heap
                   - Prepare for next cycle
            
            Returns:
                None: Executes side effects (notifications and state updates).
            
            Note:
                Decrementing transit event time ensures remaining time always
                reflects interval until next processing. Processing only begins
                after receiving first real arrival.
            
            Examples:
                >>> # Example verbose log during execution
                [event_agent] 🔄 PROCESSING EVENTS
                [event_agent] Simulation time: 5.0s
                [event_agent] Events in heap: 3
                [event_agent] Transit events: 5
                
                [event_agent] 📤 Next event: Event(type=arrival, time=10.50, sender=vehicle1@localhost)
                [event_agent] 📋 Total events with time 10.50s: 2
                
                [event_agent] 📢 Notifying grouped ARRIVAL event to 3 vehicles
                   Arrived vehicles: ['vehicle1', 'vehicle2']
            
            FIPA Compliance:
                Sends INFORM performatives to notify agents of processed events,
                implementing broadcast notification pattern.
            """
            # Check if first arrival received before processing
            if not self.agent.first_arrival_received:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ⏸️ Waiting for first arrival before processing heap...")
                return  # Don't process until first arrival received
            
            # Adicionar eventos de arrival à heap e esvaziar a lista
            for arrival_event in self.agent.arrival_events:
                heapq.heappush(self.agent.event_heap, arrival_event)
            if len(self.agent.arrival_events) > 0:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 📥 Adicionados {len(self.agent.arrival_events)} eventos de arrival à heap")
            self.agent.arrival_events = []  # Esvaziar a lista
            
            # Recolocar eventos de trânsito na heap no início
            for transit_event in self.agent.transit_events:
                heapq.heappush(self.agent.event_heap, transit_event)
            
            if self.agent.verbose:
                print(f"\n{'='*70}")
                print(f"[{self.agent.name}] 🔄 PROCESSANDO EVENTOS")
                print(f"[{self.agent.name}] Simulation time: {self.agent.simulation_interval}s")
                print(f"[{self.agent.name}] Eventos na heap: {len(self.agent.event_heap)}")
                print(f"[{self.agent.name}] Transit events: {len(self.agent.transit_events)}")
                print(f"{'='*70}\n")
            
            if not self.agent.event_heap:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] ℹ️  Nenhum evento para processar\n")
                return
            
            # Tirar o primeiro evento da heap (menor tempo)
            first_event = heapq.heappop(self.agent.event_heap)
            event_time = first_event.time
            events_to_process = [first_event]
            
            print(f"[{self.agent.name}] 📤 Next event: {first_event}")
            
            # Continuar a dar pop enquanto houver eventos com o mesmo tempo
            while self.agent.event_heap and self.agent.event_heap[0].time == event_time:
                next_event = heapq.heappop(self.agent.event_heap)
                events_to_process.append(next_event)
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 📤 Evento adicional (mesmo tempo): {next_event}")
            
            if self.agent.verbose:
                print(f"[{self.agent.name}] 📋 Total de eventos com tempo {event_time:.2f}s: {len(events_to_process)}")
            
            # Processar remoção de eventos de trânsito da lista
            was_last_transit_event = False
            for event in events_to_process:
                if event.event_type == "transit" or event.event_type == "Transit":
                    if event in self.agent.transit_events:
                        self.agent.transit_events.remove(event)
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 🗑️  Transit event removed from list: {event}")
            
            # Verificar se era o último evento de trânsito
            if len(self.agent.transit_events) == 0:
                # Verificar se algum dos eventos processados era de trânsito
                for event in events_to_process:
                    if event.event_type == "transit" or event.event_type == "Transit":
                        was_last_transit_event = True
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] ⚠️  ÚLTIMO EVENTO DE TRÂNSITO REMOVIDO!")
                        break
            
            # Atualizar tempo de todos os eventos de trânsito restantes
            updated_transit_events = []
            for transit_event in self.agent.transit_events:
                transit_event.time -= event_time
                updated_transit_events.append(transit_event)
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 🔄 Trânsito atualizado: {transit_event} (tempo restante: {transit_event.time:.2f}s)")
            
            # Atualizar lista de eventos de trânsito
            self.agent.transit_events = updated_transit_events
            
            # Notificar todos os veículos sobre os eventos processados (sequencialmente)
            await self.notify_events(events_to_process)
            
            self.agent.processed_count += len(events_to_process)
            
            # Se foi o último evento de trânsito, solicitar nova simulação
            if was_last_transit_event and self.agent.world_agent:
                if self.agent.verbose:
                    print(f"\n{'='*70}")
                    print(f"[{self.agent.name}] 🔄 SOLICITANDO NOVA SIMULAÇÃO DE TRÂNSITO")
                    print(f"  Motivo: Último evento de trânsito processado")
                    print(f"  Destinatário: {self.agent.world_agent}")
                    print(f"{'='*70}\n")
                else:
                    print(f"[{self.agent.name}] 🔄 SOLICITANDO NOVA SIMULAÇÃO DE TRÂNSITO")
                
                # Enviar pedido de nova simulação
                msg = Message(to=self.agent.world_agent)
                msg.set_metadata("performative", "request")
                msg.set_metadata("action", "simulate_traffic")
                
                data = {
                    "simulation_time": self.agent.world_simulation_time,
                    "requester": str(self.agent.jid)
                }
                msg.body = json.dumps(data)
                
                await self.send(msg)
                try:
                    msg_logger = MessageLogger.get_instance()
                    msg_logger.log_message(
                        sender=str(self.agent.jid),
                        receiver=str(msg.to),
                        message_type="Request",
                        performative="simulate_traffic",
                        body=msg.body
                    )
                except Exception:
                    pass  # Don't crash on logging errors
                print(f"[{self.agent.name}] ✅ Pedido de nova simulação enviado\n")
            if self.agent.verbose:
                print(f"\n[{self.agent.name}] 📊 Estatísticas:")
                print(f"   Eventos processados: {len(events_to_process)}")
                print(f"   Tipos: {', '.join([e.event_type for e in events_to_process])}")
                print(f"   Tempo dos eventos: {event_time:.2f}s")
                print(f"   Trânsitos ativos: {len(self.agent.transit_events)}")
                print(f"   Total recebido: {self.agent.event_count}")
                print(f"   Total processado: {self.agent.processed_count}")
                    
                # Imprimir estado completo da heap restante
                print(f"\n[{self.agent.name}] 📋 ESTADO DA HEAP RESTANTE:")
                if len(self.agent.event_heap) == 0 and len(self.agent.transit_events) == 0:
                    print(f"   ➤ Heap vazia (sem eventos)")
                else:
                    # Mostrar eventos normais na heap
                    if len(self.agent.event_heap) > 0:
                        print(f"   ➤ Eventos normais na heap: {len(self.agent.event_heap)}")
                        for i, event in enumerate(sorted(self.agent.event_heap), 1):
                            print(f"      {i}. {event}")
                    else:
                        print(f"   ➤ Eventos normais na heap: 0")
                    
                    # Mostrar eventos de trânsito
                    if len(self.agent.transit_events) > 0:
                        print(f"   ➤ Eventos de trânsito: {len(self.agent.transit_events)}")
                        for i, event in enumerate(sorted(self.agent.transit_events), 1):
                            print(f"      {i}. {event}")
                    else:
                        print(f"   ➤ Eventos de trânsito: 0")
                
                print(f"{'='*70}\n")

            # Esvaziar a heap (descartar outros eventos)
            discarded_count = len(self.agent.event_heap)
            self.agent.event_heap = []
            
            if discarded_count > 0:
                if self.agent.verbose:
                    print(f"[{self.agent.name}] 🗑️  Heap esvaziada: {discarded_count} eventos descartados")
        
        async def notify_events(self, events: List[Event]):
            """
            Notifica agentes apropriados sobre eventos processados com agrupamento inteligente.
            
            Este método distribui eventos aos agentes relevantes, implementando estratégias
            de optimização diferentes para cada tipo de evento. O agrupamento de arrivals
            e o ajuste temporal de trânsito garantem eficiência e consistência temporal.
            
            Estratégias por Tipo:
                1. **Arrival Events**:
                   - Agrupados numa única mensagem por veículo
                   - Lista de todos os veículos que chegaram incluída
                   - Enviada a TODOS os veículos registados
                   - Apenas o tempo do primeiro arrival é usado
                
                2. **Transit Events**:
                   - Enviados individualmente mas sequencialmente
                   - Primeiro evento tem tempo real
                   - Eventos subsequentes têm tempo 0 (evita resimulação)
                   - Enviados a veículos, armazéns e lojas
                
                3. **UpdateSimulation Events**:
                   - Enviados apenas ao world agent
                   - Solicita nova simulação de tráfego
                   - Usa tempo configurado em world_simulation_time
            
            Args:
                events (List[Event]): Lista de eventos a notificar. Podem ser de tipos
                    mistos. O método classifica e processa cada tipo adequadamente.
            
            Returns:
                None: Executa efeitos colaterais (envio de mensagens XMPP).
            
            Message Formats:
                Arrival (agrupado):
                    {
                        "type": "arrival",
                        "time": float,              # Tempo do primeiro arrival
                        "vehicles": List[str]       # Lista de nomes de veículos
                    }
                
                Transit (individual):
                    {
                        "type": "Transit",
                        "time": float,              # Real para primeiro, 0 para restantes
                        "data": {
                            "edges": [
                                {
                                    "node1": int,
                                    "node2": int,
                                    "weight": float,
                                    "fuel_consumption": float
                                }
                            ]
                        }
                    }
                
                UpdateSimulation:
                    {
                        "simulation_time": float,
                        "requester": str            # JID do event agent
                    }
            
            Examples:
                >>> # Processar lista mista de eventos
                >>> events = [
                ...     Event("arrival", 10.5, {}, "vehicle1@localhost"),
                ...     Event("arrival", 10.5, {}, "vehicle2@localhost"),
                ...     Event("transit", 10.5, {"edges": [...]})
                ... ]
                >>> await self.notify_events(events)
                
                # Resultado:
                # - 1 mensagem de arrival para cada veículo registado (lista agrupada)
                # - 1 mensagem de transit para veículos + armazéns + lojas
            
            Note:
                O ajuste de tempo para 0 em eventos subsequentes é crucial para evitar
                que múltiplos eventos causem simulações repetidas do mesmo intervalo
                temporal nos agentes receptores.
            
            Warning:
                Se world_agent não estiver configurado, eventos de updatesimulation
                são ignorados silenciosamente com log de aviso.
            
            See Also:
                Event.to_dict(): Serialização de eventos para mensagens.
                ProcessEventsBehaviour.run(): Método que invoca notify_events.
            """
            # Agrupar eventos por tipo
            arrival_events = []
            transit_events = []
            other_events = []
            
            for event in events:
                if event.event_type == "arrival":
                    arrival_events.append(event)
                elif event.event_type == "transit" or event.event_type == "Transit":
                    transit_events.append(event)
                else:
                    other_events.append(event)
            
            # Processar eventos de arrival agrupados
            if arrival_events:
                # Coletar todos os nomes de veículos
                vehicle_names = [event.sender.split('@')[0] for event in arrival_events]
                # Tempo é do primeiro evento
                event_time = arrival_events[0].time
                
                if self.agent.verbose:
                    print(f"\n[{self.agent.name}] 📢 Notificando evento ARRIVAL agrupado para {len(self.agent.registered_vehicles)} veículos")
                    print(f"   Veículos que chegaram: {vehicle_names}")
                else:
                    print(f"\n[{self.agent.name}] 📢 Notificando evento ARRIVAL agrupado para {len(self.agent.registered_vehicles)} veículos")

                # Enviar uma única mensagem para todos os veículos registrados
                recipients = (self.agent.registered_vehicles + 
                            self.agent.registered_stores
                            ) # TODO + self.agent.registered_warehouses + self.agent.registered_suppliers
                for recipient_jid in recipients:
                    msg = Message(to=recipient_jid)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("event_type", "arrival")
                    
                    # Criar mensagem com lista de veículos
                    event_dict = {
                        "type": "arrival",
                        "time": event_time,
                        "vehicles": vehicle_names  # Lista de veículos
                    }
                    
                    msg.body = json.dumps(event_dict)
                    
                    await self.send(msg)
                    try:
                        msg_logger = MessageLogger.get_instance()
                        msg_logger.log_message(
                            sender=str(self.agent.jid),
                            receiver=str(msg.to),
                            message_type="Notify",
                            performative="inform",
                            body=msg.body
                        )
                    except Exception:
                        pass  # Don't crash on logging errors
                    recipient_name = recipient_jid.split('@')[0]
                    
                    if self.agent.verbose:
                        print(f"[{self.agent.name}]   → {recipient_name}: arrival (vehicles={vehicle_names}, time={event_time:.4f}s)")
            
            # Processar eventos de trânsito
            for idx, event in enumerate(transit_events):
                recipients = (self.agent.registered_vehicles + 
                            self.agent.registered_stores
                            ) # TODO + self.agent.registered_warehouses + self.agent.registered_suppliers
                if self.agent.verbose:
                    print(f"\n[{self.agent.name}] 📢 Notificando evento TRANSIT para {len(recipients)} agentes")
                
                for recipient_jid in recipients:
                    msg = Message(to=recipient_jid)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("event_type", "Transit")
                    
                    event_dict = event.to_dict()
                    
                    # Apenas o primeiro evento tem o tempo real
                    if idx > 0:
                        original_time = event_dict["time"]
                        event_dict["time"] = 0
                        if self.agent.verbose:
                            print(f"[{self.agent.name}] 🔄 Ajustando tempo do evento Transit para 0 (original={original_time:.2f}s) para {recipient_jid.split('@')[0]}")
                    
                    msg.body = json.dumps(event_dict)
                    
                    await self.send(msg)
                    try:
                        msg_logger = MessageLogger.get_instance()
                        msg_logger.log_message(
                            sender=str(self.agent.jid),
                            receiver=str(msg.to),
                            message_type="Notify",
                            performative="inform",
                            body=msg.body
                        )
                    except Exception:
                        pass  # Don't crash on logging errors
                    recipient_name = recipient_jid.split('@')[0]
                    if self.agent.verbose:
                        print(f"[{self.agent.name}]   → {recipient_name}: Transit (time={event_dict['time']:.4f}s)")
            
            # Processar outros eventos (updatesimulation, etc)
            for event in other_events:
                if event.event_type == "updatesimulation":
                    if self.agent.world_agent:
                        if self.agent.verbose:
                            print(f"\n[{self.agent.name}] 📢 Processando evento UPDATESIMULATION - Solicitando nova simulação")
                        
                        msg = Message(to=self.agent.world_agent)
                        msg.set_metadata("performative", "request")
                        msg.set_metadata("action", "simulate_traffic")
                        
                        data = {
                            "simulation_time": self.agent.world_simulation_time,
                            "requester": str(self.agent.jid)
                        }
                        msg.body = json.dumps(data)
                        
                        await self.send(msg)
                        try:
                            msg_logger = MessageLogger.get_instance()
                            msg_logger.log_message(
                                sender=str(self.agent.jid),
                                receiver=str(msg.to),
                                message_type="Request",
                                performative="request",
                                body=msg.body
                            )
                        except Exception:
                            pass  # Don't crash on logging errors
                        print(f"[{self.agent.name}]   → Pedido de re-simulação enviado ao world agent")
                    else:
                        print(f"\n[{self.agent.name}] ⚠️  Agente do mundo não registrado, evento ignorado")
    

