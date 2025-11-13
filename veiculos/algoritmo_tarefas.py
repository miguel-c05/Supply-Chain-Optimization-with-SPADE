import sys
import os
from ..world.graph import Graph

# Cache global para armazenar resultados do Dijkstra
_dijkstra_cache = {}

def get_dijkstra_cached(graph: Graph, start: int, end: int):
    """
    Retorna o resultado do Dijkstra usando cache para evitar recalcular rotas.
    
    Returns:
        tuple: (path, fuel, time)
    """
    cache_key = (start, end)
    if cache_key not in _dijkstra_cache:
        _dijkstra_cache[cache_key] = graph.djikstra(start, end)
    return _dijkstra_cache[cache_key]

def clear_dijkstra_cache():
    """Limpa o cache do Dijkstra"""
    global _dijkstra_cache
    _dijkstra_cache = {}

class TreeNode:
    def __init__(self, 
                 location,
                 state: list[Order],
                 max_quantity:int=0, 
                 max_fuel:int=0,parent=None,
                 depth=0,initial_points_reached:list[int]=0,
                 end_points_reached:list[int]=0, 
                 h=0,
                 g=0,
                 average_cost_per_task:float=0,
                 lambda_penalty:int=2):
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
        self.lambda_penalty = lambda_penalty

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
                    average_cost_per_task=self.average_cost_per_task,
                    lambda_penalty=self.lambda_penalty

                ),
                average_cost_per_task=self.average_cost_per_task
            )
            child_node.quantity = new_quantity
            #print(f"Depth:{child_node.depth}")
            self.add_child(child_node)

    def evaluate_available_points(self,graph: Graph):
        available_points = []
        for sender_location, receiver_location, quantity,orderid in self.state:
            if quantity + self.quantity > self.max_quantity:
                continue
            if (orderid,sender_location) not in self.initial_points_reached:
                _ ,fuel,time = get_dijkstra_cached(graph, self.location, sender_location)
                if fuel <= self.max_fuel:
                    available_points.append((sender_location, orderid, quantity,time, 1))
            else: 
                if (orderid,receiver_location) not in self.end_points_reached:
                    _ ,fuel,time = get_dijkstra_cached(graph, self.location, receiver_location)
                    if fuel <= self.max_fuel:
                        available_points.append((receiver_location, orderid, quantity,time, 0))

        return available_points
    
    def plot_tree(self, filename="search_tree.png"):
        """Cria uma visualização gráfica da árvore de pesquisa usando matplotlib e networkx"""
        
        # Primeiro, contar o número total de nós
        def count_nodes(node):
            count = 1
            for child in node.children:
                count += count_nodes(child)
            return count
        
        total_nodes = count_nodes(self)
        print(f"\n📊 Estatísticas da árvore de pesquisa:")
        print(f"  Total de nós: {total_nodes}")
        
        # Calcular profundidade máxima
        def get_max_depth(node):
            if not node.children:
                return node.depth
            return max(get_max_depth(child) for child in node.children)
        
        max_depth = get_max_depth(self)
        print(f"  Profundidade máxima: {max_depth}")
        
        # Se houver mais de 1000 nós, não gerar imagem
        if total_nodes >= 1000:
            print(f"\n⚠️  Árvore muito grande ({total_nodes} nós). Pulando geração de imagem.")
            return
        
        # Continuar com a geração da imagem
        try:
            import matplotlib.pyplot as plt
            import networkx as nx
        except ImportError:
            print("Erro: matplotlib e networkx são necessários para plotar a árvore")
            print("Instale com: pip install matplotlib networkx")
            return
        
        # Criar grafo direcionado
        G = nx.DiGraph()
        pos = {}
        labels = {}
        node_colors = []
        
        # Função auxiliar para adicionar nós recursivamente
        def add_nodes_recursive(node, x=0, y=0, layer_width=2.0):
            node_id = id(node)
            
            # Adicionar nó ao grafo
            G.add_node(node_id)
            pos[node_id] = (x, -y)  # y negativo para crescer para baixo
            
            # Criar label com informações do nó
            label = f"Loc:{node.location}\n"
            label += f"D:{node.depth}\n"
            label += f"f:{node.f:.1f}\n"
            label += f"g:{node.g:.1f}|h:{node.h:.1f}"
            labels[node_id] = label
            
            # Colorir nó baseado na profundidade (gradiente)
            node_colors.append(node.depth)
            
            # Adicionar filhos
            num_children = len(node.children)
            if num_children > 0:
                # Calcular espaçamento horizontal para os filhos
                child_width = layer_width / max(num_children, 1)
                start_x = x - (layer_width / 2) + (child_width / 2)
                
                for i, child in enumerate(node.children):
                    child_x = start_x + i * child_width
                    child_y = y + 1
                    
                    # Adicionar aresta
                    G.add_edge(node_id, id(child))
                    
                    # Recursão para o filho
                    add_nodes_recursive(child, child_x, child_y, layer_width * 0.8)
        
        # Construir a árvore começando da raiz
        add_nodes_recursive(self, x=0, y=0, layer_width=10.0)
        
        # Criar figura
        plt.figure(figsize=(32, 20))
        
        # Desenhar o grafo
        nx.draw(
            G, pos,
            labels=labels,
            node_color=node_colors,
            cmap=plt.cm.viridis,
            node_size=2000,
            font_size=7,
            font_weight='bold',
            arrows=True,
            arrowsize=10,
            edge_color='gray',
            linewidths=2,
            with_labels=True
        )
        
        # Adicionar título
        plt.title(f"Árvore de Pesquisa A*\nTotal de nós: {len(G.nodes)}", 
                 fontsize=14, fontweight='bold')
        
        # Salvar figura
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"\n✓ Árvore de pesquisa salva em: {filename}")
        
        plt.close()
    
def calculate_heuristic(state,end_points_reached,initial_points_reached,average_cost_per_task,lambda_penalty:int=2):
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
    
    # Limpar cache do Dijkstra para nova execução
    clear_dijkstra_cache()
    
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
    target_depth = 2 * len(tasks)
    
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
            
            # Retornar: caminho, tempo total, árvore de pesquisa
            total_time = current_node.g
            return path, total_time, root
        
        # Avaliar pontos disponíveis
        current_node.available_points = current_node.evaluate_available_points(graph)
        # Criar filhos
        current_node.create_childs()
        
        # Adicionar filhos à fila de prioridade
        for child in current_node.children:
            open_list.put((child.f, id(child), child))
    
    return None, float('inf'), root


