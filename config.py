import os

BASE_DIR =  os.getcwd()

SEED_DIR = os.path.join(BASE_DIR ,"seeds")

# ========================================
# PRODUTOS
# ========================================
PRODUCTS = ["A", "B", "C", "D"]

# ========================================
# WAREHOUSE CONFIGURATION
# ========================================
WAREHOUSE_MAX_PRODUCT_CAPACITY = 80
WAREHOUSE_RESUPPLY_THRESHOLD = 20

# ========================================
# STORE CONFIGURATION
# ========================================
STORE_MAX_BUY_QUANTITY = 20
STORE_BUY_FREQUENCY = 5  # seconds
STORE_BUY_PROBABILITY = 0.6  # 60% chance to buy each cycle

# ========================================
# VEHICLE CONFIGURATION
# ========================================
VEHICLE_CAPACITY = 200
VEHICLE_MAX_FUEL = 10
VEHICLE_MAX_ORDERS = 10
VEHICLE_WEIGHT = 1500

# ========================================
# AGENT QUANTITIES (for simulation)
# ========================================
NUM_VEHICLES = 3
NUM_WAREHOUSES = 2
NUM_STORES = 2
NUM_SUPPLIERS = 2

# ========================================
# WORLD CONFIGURATION
# ========================================
WORLD_WIDTH = 5
WORLD_HEIGHT = 5
WORLD_MODE = "different"  # "uniform" or "different"
WORLD_MAX_COST = 4
WORLD_GAS_STATIONS = 0
WORLD_WAREHOUSES = NUM_WAREHOUSES  # Igual ao número de warehouses a criar
WORLD_SUPPLIERS = NUM_SUPPLIERS    # Igual ao número de suppliers a criar
WORLD_STORES = NUM_STORES          # Igual ao número de stores a criar
WORLD_HIGHWAY = True
WORLD_TRAFFIC_PROBABILITY = 0.5
WORLD_TRAFFIC_SPREAD_PROBABILITY = 0.8
WORLD_TRAFFIC_INTERVAL = 2
WORLD_UNTRAFFIC_PROBABILITY = 0.4

# ========================================
# EVENT AGENT CONFIGURATION
# ========================================
EVENT_AGENT_SIMULATION_INTERVAL = 10.0  # seconds
EVENT_AGENT_WORLD_SIMULATION_TIME = 10.0  # seconds