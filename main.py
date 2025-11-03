from world.world import World

w = World(width=5, height=5, mode="uniform", seed=None, gas_stations=0, warehouses=1, suppliers=0, stores=1, highway=False)

for i in range(1, 11):
    w.tick(traffic_interval=1)
    print(f"Tick {i} completed.")
    w.plot_graph()