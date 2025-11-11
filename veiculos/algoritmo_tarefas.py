from ..world.graph import Graph

class Order:
    def __init__(self, product:str, quantity:int, orderid:int, sender:str, receiver:str, tick_received:int):
        self.product = product
        self.quantity = quantity
        self.sender = sender
        self.receiver = receiver
        self.tick_received = tick_received

        self.deliver_time = None
        self.route = None
        self.sender_location = None
        self.receiver_location = None
        self.orderid = orderid
        self.fuel = None
        

    def __str__(self):
        return f"Order({self.orderid}, {self.product}, {self.quantity}, {self.sender}, {self.receiver}, {self.tick_received})"
    def time_to_deliver(self,sender_location:int,receiver_location:int ,map: Graph,weight: float):
        #calcula o tempo de entrega baseado no mapa
        route, time, fuel= map.get_route_time(sender_location,receiver_location,weight)
        self.route = route
        self.deliver_time = time
        self.fuel = fuel
        self.sender_location = sender_location
        self.receiver_location = receiver_location

class TreeNode:
    def __init__(self, location,state: list[Order],max_quantity:int=0, max_fuel:int=0,parent=None, depth=0,initial_points_reached:list[int]=0,end_points_reached:list[int]=0, h=0,g=0,average_cost_per_task:float=0):
        self.state = state
        self.parent = parent
        self.location = location
        self.children = []
        self.initial_points_reached = initial_points_reached
        self.end_points_reached = end_points_reached
        self.available_points = 0
        self.depth = depth
        self.quantity= 0
        self.max_fuel = max_fuel
        self.max_quantity = max_quantity
        self.h = h
        self.g = g
        self.f= self.g + self.h
        self.average_cost_per_task = average_cost_per_task

    def __gt__(self, other):
        return self.f > other.f
    def __eq__ (self, other):
        return self.state == other.state
    def add_child(self, child_node):
        self.children.append(child_node)

    def create_childs(self):
        for point in self.available_points:
            new_initial_points_reached = self.initial_points_reached.copy()
            new_end_points_reached = self.end_points_reached.copy()
            new_quantity = self.quantity
            if point[4] == 1:  # warehouse
                new_initial_points_reached.append((point[1],point[0]))
                new_quantity += point[2]
            else:  # customer
                new_end_points_reached.append((point[1],point[0]))
                new_quantity -= point[2]
            child_node = TreeNode(
                location=point[0],
                state=self.state,
                max_quantity=self.max_quantity,
                max_fuel=self.max_fuel,
                parent=self,
                depth=self.depth + 1,
                initial_points_reached=new_initial_points_reached,
                end_points_reached=new_end_points_reached,
                g=self.g + point[3],
                h=calculate_heuristic(
                    self.state,
                    new_end_points_reached,
                    new_initial_points_reached,
                    average_cost_per_task=self.average_cost_per_task
                ),
                average_cost_per_task=self.average_cost_per_task
            )
            child_node.quantity = new_quantity
            self.add_child(child_node)

    def evaluate_available_points(self,graph: Graph):
        available_points = []
        for sender_location, receiver_location, quantity,orderid in self.state:
            if quantity + self.quantity > self.max_quantity:
                continue
            if (orderid,sender_location) not in self.initial_points_reached:
                time,fuel = graph.get_route_time(self.location, sender_location)
                if fuel <= self.max_fuel:
                    available_points.append((sender_location, orderid, quantity,time, 1))
            else: 
                if (orderid,receiver_location) not in self.end_points_reached:
                    time,fuel = graph.get_route_time(self.location, receiver_location)
                    if fuel <= self.max_fuel:
                        available_points.append((receiver_location, orderid, quantity,time, 0))

        return available_points
    
def calculate_heuristic(state,end_points_reached,initial_points_reached,average_cost_per_task,lambda_penalty:int=0.3):
    """h(n) = custo_médio_por_tarefa * (tarefas_totais - tarefas_concluídas)
    - λ * tarefas_ativas"""
    total_tasks = len(state)
    completed_tasks = len(end_points_reached)
    active_tasks = len(initial_points_reached) - completed_tasks

    average_cost_per_task = average_cost_per_task

    return (average_cost_per_task * (total_tasks - completed_tasks)) - (lambda_penalty * active_tasks)


def A_star_task_algorithm(graph: Graph, start:int, tasks:list[Order],capacity:int, max_fuel: int):
    # Implementação simplificada do algoritmo A* para ordenação de tarefas
    from queue import PriorityQueue
    
    # Calcular o custo médio por tarefa
    total_time = sum(order.deliver_time for order in tasks)
    average_cost_per_task = total_time / len(tasks) if tasks else 0
    
    # Criar o estado inicial (sender_location, receiver_location, quantity, orderid)
    initial_state = [
        (order.sender_location, order.receiver_location, order.quantity, order.orderid)
        for order in tasks
    ]
    
    # Criar o nó raiz
    root = TreeNode(
        location=start,
        state=initial_state,
        max_quantity=capacity,
        max_fuel=max_fuel,
        parent=None,
        depth=0,
        initial_points_reached=[],
        end_points_reached=[],
        h=calculate_heuristic(initial_state, [], [], average_cost_per_task),
        g=0,
        average_cost_per_task=average_cost_per_task
    )
    
    # Fila de prioridade para o A*
    open_list = PriorityQueue()
    open_list.put((root.f, id(root), root))
    
    # Profundidade alvo (2 * número de tarefas)
    target_depth = 2 * len(tasks) 
    
    visited = set()
    
    while not open_list.empty():
        _, _, current_node = open_list.get()
        
        # Verificar se chegamos ao objetivo
        if current_node.depth == target_depth:
            # Reconstruir o caminho
            path = []
            node = current_node
            while node is not None:
                path.append(node.location)
                node = node.parent
            path.reverse()
            return path, current_node.g
        
        # Avaliar pontos disponíveis
        current_node.available_points = current_node.evaluate_available_points(graph)
        
        # Criar filhos
        current_node.create_childs()
        
        # Adicionar filhos à fila de prioridade
        for child in current_node.children:
            open_list.put((child.f, id(child), child))

    return None, float('inf')
