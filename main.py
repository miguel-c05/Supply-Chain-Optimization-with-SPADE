from world.world import World

w = World(width=5, height=5, mode="different", seed=107, gas_stations=0, warehouses=2, suppliers=3, stores=4)
print("Cost Matrix:")
for row in w.cost_matrix[1:]:
    print(row[1:])
w.plot_graph()