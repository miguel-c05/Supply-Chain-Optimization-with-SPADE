from world.world import World

w = World(
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

for i in range(1, 11):
    w.tick()
    print(f"Tick {i} completed.")
    w.plot_graph()