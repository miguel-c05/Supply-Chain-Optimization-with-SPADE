from world.world import World

w = World(
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

for i in range(1, 11):
    w.tick()
    print(f"Tick {i} completed.")
    w.plot_graph()
    start, target = input("Enter start and target node IDs: ").split(" ")
    path, fuel, time = w.graph.djikstra(int(start), int(target))
    print(f"Path: {path[0].id} --> {'-->'.join(str(node.id) for node in path[1:])} \nFuel needed: {fuel} liters\nTime needed: {time} seconds")
    w.plot_graph()