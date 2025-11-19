"""
Logging Utilities for Supply Chain Optimization System.

This module provides centralized logging functionality for tracking messages,
route calculations, and other metrics across all agents in the simulation.
Each simulation run creates timestamped log files for analysis.

Log Files Generated:
    - messages_<timestamp>.csv: All inter-agent messages with sender, receiver, type, and time
    - route_calculations_<timestamp>.csv: Vehicle route recalculations with algorithm used
    - vehicle_metrics_<timestamp>.csv: Vehicle-specific metrics (fuel, load, location)
    - inventory_changes_<timestamp>.csv: Stock changes in warehouses and stores
    - order_lifecycle_<timestamp>.csv: Complete order tracking from creation to delivery

Usage:
    >>> from logger_utils import MessageLogger, RouteCalculationLogger
    >>> msg_logger = MessageLogger.get_instance()
    >>> msg_logger.log_message("vehicle1@localhost", "warehouse1@localhost", "order-proposal", 15.5)
"""

import os
import csv
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any


class LoggerBase:
    """Base class for all logger types with singleton pattern and thread safety."""
    
    _instances: Dict[str, 'LoggerBase'] = {}
    _locks: Dict[str, Lock] = {}
    
    def __init__(self, log_dir: str = "logs"):
        """Initialize logger with timestamped log directory.
        
        Args:
            log_dir: Base directory for log files. Defaults to "logs".
        """
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_dir = os.path.join(log_dir, self.timestamp)
        os.makedirs(self.log_dir, exist_ok=True)
        self.lock = Lock()
    
    @classmethod
    def get_instance(cls):
        """Get singleton instance of logger (thread-safe).
        
        Returns:
            LoggerBase: Singleton instance of the logger class.
        """
        class_name = cls.__name__
        if class_name not in cls._locks:
            cls._locks[class_name] = Lock()
        
        with cls._locks[class_name]:
            if class_name not in cls._instances:
                cls._instances[class_name] = cls()
            return cls._instances[class_name]
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for new simulation runs)."""
        class_name = cls.__name__
        if class_name in cls._instances:
            del cls._instances[class_name]


class MessageLogger(LoggerBase):
    """Logger for inter-agent message tracking.
    
    Tracks all messages exchanged between agents including:
    - Sender and receiver JIDs
    - Message type/performative
    - Timestamp (simulation time)
    - Real-world timestamp
    - Message metadata
    
    CSV Format:
        timestamp_real, timestamp_sim, sender, receiver, message_type, performative, metadata
    """
    
    def __init__(self, log_dir: str = "logs"):
        super().__init__(log_dir)
        self.log_file = os.path.join(self.log_dir, "messages.csv")
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers."""
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp_real',
                'timestamp_sim',
                'sender',
                'receiver',
                'message_type',
                'performative',
                'body_preview',
                'metadata'
            ])
    
    def log_message(self, sender: str, receiver: str, message_type: str,
                   timestamp_sim: float = None, performative: str = "",
                   body: str = "", metadata: str = ""):
        """Log a message exchange.
        
        Args:
            sender: JID of the sending agent
            receiver: JID of the receiving agent
            message_type: Type of message (e.g., "order-proposal", "store-buy")
            timestamp_sim: Simulation time when message was sent
            performative: FIPA performative (e.g., "inform", "request")
            body: Message body (truncated to 100 chars for preview)
            metadata: Additional metadata as string
        """
        with self.lock:
            timestamp_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            body_preview = (body[:100] + '...') if len(body) > 100 else body
            
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_real,
                    timestamp_sim if timestamp_sim is not None else "",
                    sender,
                    receiver,
                    message_type,
                    performative,
                    body_preview,
                    metadata
                ])


class RouteCalculationLogger(LoggerBase):
    """Logger for vehicle route calculation tracking.
    
    Tracks every route recalculation performed by vehicles including:
    - Vehicle identifier
    - Algorithm used (Dijkstra or A*)
    - Number of orders in calculation
    - Computation time
    - Route details
    
    CSV Format:
        timestamp_real, timestamp_sim, vehicle_jid, algorithm, num_orders, 
        computation_time_ms, route_length, total_distance, total_fuel
    """
    
    def __init__(self, log_dir: str = "logs"):
        super().__init__(log_dir)
        self.log_file = os.path.join(self.log_dir, "route_calculations.csv")
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers."""
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp_real',
                'timestamp_sim',
                'vehicle_jid',
                'algorithm',
                'num_orders',
                'computation_time_ms',
                'route_length',
                'total_distance',
                'total_fuel',
                'route_nodes'
            ])
    
    def log_calculation(self, vehicle_jid: str, algorithm: str, num_orders: int,
                       computation_time_ms: float, route_length: int = 0,
                       total_distance: float = 0, total_fuel: float = 0,
                       route_nodes: str = "", timestamp_sim: float = None):
        """Log a route calculation event.
        
        Args:
            vehicle_jid: JID of the vehicle performing calculation
            algorithm: Algorithm used ("dijkstra" or "astar")
            num_orders: Number of orders in the calculation
            computation_time_ms: Time taken for computation in milliseconds
            route_length: Number of nodes in calculated route
            total_distance: Total distance of route
            total_fuel: Total fuel required for route
            route_nodes: String representation of route nodes
            timestamp_sim: Simulation time when calculation occurred
        """
        with self.lock:
            timestamp_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_real,
                    timestamp_sim if timestamp_sim is not None else "",
                    vehicle_jid,
                    algorithm,
                    num_orders,
                    round(computation_time_ms, 3),
                    route_length,
                    round(total_distance, 3),
                    round(total_fuel, 3),
                    route_nodes
                ])


class VehicleMetricsLogger(LoggerBase):
    """Logger for vehicle state metrics.
    
    Tracks vehicle state changes including fuel, load, and location.
    
    CSV Format:
        timestamp_real, timestamp_sim, vehicle_jid, current_fuel, current_load,
        current_location, next_node, num_active_orders, num_pending_orders
    """
    
    def __init__(self, log_dir: str = "logs"):
        super().__init__(log_dir)
        self.log_file = os.path.join(self.log_dir, "vehicle_metrics.csv")
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers."""
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp_real',
                'timestamp_sim',
                'vehicle_jid',
                'current_fuel',
                'current_load',
                'current_location',
                'next_node',
                'num_active_orders',
                'num_pending_orders',
                'status'
            ])
    
    def log_vehicle_state(self, vehicle_jid: str, current_fuel: float,
                         current_load: int, current_location: int,
                         next_node: Optional[int], num_active_orders: int,
                         num_pending_orders: int, status: str = "",
                         timestamp_sim: float = None):
        """Log vehicle state snapshot.
        
        Args:
            vehicle_jid: JID of the vehicle
            current_fuel: Current fuel level
            current_load: Current cargo load
            current_location: Current node ID
            next_node: Next destination node ID (None if idle)
            num_active_orders: Number of orders in execution
            num_pending_orders: Number of orders awaiting execution
            status: Current status (e.g., "moving", "idle", "refueling")
            timestamp_sim: Simulation time
        """
        with self.lock:
            timestamp_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_real,
                    timestamp_sim if timestamp_sim is not None else "",
                    vehicle_jid,
                    round(current_fuel, 3),
                    current_load,
                    current_location,
                    next_node if next_node is not None else "",
                    num_active_orders,
                    num_pending_orders,
                    status
                ])


class InventoryLogger(LoggerBase):
    """Logger for inventory changes in warehouses and stores.
    
    CSV Format:
        timestamp_real, timestamp_sim, agent_jid, agent_type, product,
        change_type, quantity, stock_before, stock_after
    """
    
    def __init__(self, log_dir: str = "logs"):
        super().__init__(log_dir)
        self.log_file = os.path.join(self.log_dir, "inventory_changes.csv")
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers."""
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp_real',
                'timestamp_sim',
                'agent_jid',
                'agent_type',
                'product',
                'change_type',
                'quantity',
                'stock_before',
                'stock_after'
            ])
    
    def log_inventory_change(self, agent_jid: str, agent_type: str, product: str,
                            change_type: str, quantity: int, stock_before: int,
                            stock_after: int, timestamp_sim: float = None):
        """Log inventory change event.
        
        Args:
            agent_jid: JID of the agent (warehouse or store)
            agent_type: Type of agent ("warehouse" or "store")
            product: Product identifier
            change_type: Type of change ("purchase", "delivery", "sale", "lock", "unlock")
            quantity: Quantity changed
            stock_before: Stock level before change
            stock_after: Stock level after change
            timestamp_sim: Simulation time
        """
        with self.lock:
            timestamp_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_real,
                    timestamp_sim if timestamp_sim is not None else "",
                    agent_jid,
                    agent_type,
                    product,
                    change_type,
                    quantity,
                    stock_before,
                    stock_after
                ])


class OrderLifecycleLogger(LoggerBase):
    """Logger for complete order lifecycle tracking.
    
    Tracks orders from creation through delivery with state transitions.
    
    CSV Format:
        timestamp_real, timestamp_sim, order_id, sender, receiver, product,
        quantity, event_type, details
    """
    
    def __init__(self, log_dir: str = "logs"):
        super().__init__(log_dir)
        self.log_file = os.path.join(self.log_dir, "order_lifecycle.csv")
        self._init_csv()
    
    def _init_csv(self):
        """Initialize CSV file with headers."""
        with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'timestamp_real',
                'timestamp_sim',
                'order_id',
                'sender',
                'receiver',
                'product',
                'quantity',
                'event_type',
                'vehicle',
                'details'
            ])
    
    def log_order_event(self, order_id: int, sender: str, receiver: str,
                       product: str, quantity: int, event_type: str,
                       vehicle: str = "", details: str = "",
                       timestamp_sim: float = None):
        """Log order lifecycle event.
        
        Args:
            order_id: Unique order identifier
            sender: JID of sender agent
            receiver: JID of receiver agent
            product: Product identifier
            quantity: Order quantity
            event_type: Event type ("created", "proposed", "accepted", "rejected",
                       "pickup", "in_transit", "delivered", "failed")
            vehicle: JID of assigned vehicle (if applicable)
            details: Additional details about the event
            timestamp_sim: Simulation time
        """
        with self.lock:
            timestamp_real = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp_real,
                    timestamp_sim if timestamp_sim is not None else "",
                    order_id,
                    sender,
                    receiver,
                    product,
                    quantity,
                    event_type,
                    vehicle,
                    details
                ])


def initialize_loggers(log_dir: str = "logs"):
    """Initialize all loggers for a new simulation run.
    
    This function should be called at the start of each simulation to ensure
    fresh log files are created with a new timestamp.
    
    Args:
        log_dir: Base directory for log files. Defaults to "logs".
    
    Returns:
        dict: Dictionary containing all logger instances
    """
    # Reset all existing instances
    MessageLogger.reset_instance()
    RouteCalculationLogger.reset_instance()
    VehicleMetricsLogger.reset_instance()
    InventoryLogger.reset_instance()
    OrderLifecycleLogger.reset_instance()
    
    # Create new instances
    loggers = {
        'message': MessageLogger.get_instance(),
        'route': RouteCalculationLogger.get_instance(),
        'vehicle': VehicleMetricsLogger.get_instance(),
        'inventory': InventoryLogger.get_instance(),
        'order': OrderLifecycleLogger.get_instance()
    }
    
    print(f"[LOGGER] Initialized logging system")
    print(f"[LOGGER] Log directory: {loggers['message'].log_dir}")
    
    return loggers
