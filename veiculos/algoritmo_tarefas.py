"""
Algoritmo A* para Otimização de Rotas de Entrega Multi-Tarefa.

Este módulo implementa um algoritmo de busca A* adaptado para o problema de Vehicle
Routing Problem (VRP) com restrições de capacidade e combustível. O algoritmo encontra
a sequência ótima de pickups e deliveries que minimiza o tempo total de viagem.

O problema é modelado como uma árvore de busca onde:
- Cada nó representa um estado (localização atual + tarefas completadas)
- Arestas representam transições (mover para pickup ou delivery)
- Heurística h(n) estima o custo restante até completar todas as tarefas
- Custo g(n) é o tempo acumulado desde o início

Características principais:
    - Cache de Dijkstra para evitar recálculos de rotas
    - Heurística admissível baseada em custo médio por tarefa
    - Penalização de tarefas ativas (λ-penalty) para evitar sobrecarga
    - Restrições de capacidade e combustível verificadas dinamicamente
    - Visualização da árvore de busca com matplotlib/networkx

Classes:
    TreeNode: Representa um estado na árvore de busca A*.

Funções:
    get_dijkstra_cached: Retorna resultado de Dijkstra com cache.
    clear_dijkstra_cache: Limpa cache global de rotas.
    calculate_heuristic: Calcula h(n) para um estado.
    A_star_task_algorithm: Executa A* e retorna rota ótima.

Exemplo de uso:
    >>> from world.graph import Graph
    >>> graph = Graph()
    >>> orders = [order1, order2, order3]  # Lista de Order objects
    >>> path, time, tree = A_star_task_algorithm(
    ...     graph=graph,
    ...     start=0,
    ...     tasks=orders,
    ...     capacity=50,
    ...     max_fuel=100
    ... )
    >>> print(path)  # [(0, None), (3, 1), (5, 1), (7, 2), ...]
    >>> print(f"Tempo total: {time}s")
    >>> tree.plot_tree("search_tree.png")  # Visualização opcional

Notas técnicas:
    - Otimizações: Cache de Dijkstra reduz chamadas ao algoritmo de rota
    - Admissibilidade: h(n) é admissível se average_cost ≤ custo real mínimo
"""

import sys
import os
from typing import TYPE_CHECKING

# Adicionar o diretório pai ao path para importações absolutas
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from world.graph import Graph

# Importação condicional para evitar circular import
if TYPE_CHECKING:
    from veiculos.veiculos import Order

# Cache global para armazenar resultados do Dijkstra
_dijkstra_cache = {}

def get_dijkstra_cached(graph: Graph, start: int, end: int):
    """
    Retorna o resultado do algoritmo de Dijkstra usando cache para evitar recálculos.
    
    Implementa um sistema de memoização para chamadas ao algoritmo de Dijkstra.
    Como o grafo não muda durante a execução do A*, rotas entre os mesmos pontos
    sempre terão o mesmo resultado. O cache é indexado por (start, end).
    
    Args:
        graph: Instância de Graph contendo a topologia da rede.
        start: ID do nó de origem.
        end: ID do nó de destino.
    
    Returns:
        Tupla (path, fuel, time) onde:
        - path (list[Node]): Lista de nós no caminho mais curto.
        - fuel (float): Combustível necessário para percorrer o caminho.
        - time (float): Tempo total de viagem em segundos.
    
    Side Effects:
        Modifica o dicionário global _dijkstra_cache ao adicionar novos resultados.
    
    Exemplo:
        >>> result1 = get_dijkstra_cached(graph, 3, 7)  # Calcula e armazena
        >>> result2 = get_dijkstra_cached(graph, 3, 7)  # Retorna do cache (instantâneo)
        >>> assert result1 == result2
    
    Note:
        - Cache é global e persiste entre chamadas ao A*
        - Usar clear_dijkstra_cache() para limpar antes de nova execução
        - Performance: O(1) para hits, O(V²) para misses (Dijkstra completo)
    """
    cache_key = (start, end)
    if cache_key not in _dijkstra_cache:
        _dijkstra_cache[cache_key] = graph.djikstra(start, end)
    return _dijkstra_cache[cache_key]

def clear_dijkstra_cache():
    """
    Limpa o cache global de resultados do Dijkstra.
    
    Deve ser chamado antes de cada execução do A* para evitar usar rotas
    desatualizadas caso o grafo tenha mudado (ex: atualização de trânsito).
    
    Side Effects:
        Reseta o dicionário global _dijkstra_cache para vazio.
    
    Exemplo:
        >>> clear_dijkstra_cache()
        >>> # Cache vazio - próximas chamadas a get_dijkstra_cached calcularão tudo
    
    Note:
        Chamado automaticamente em A_star_task_algorithm antes de iniciar a busca.
    """
    global _dijkstra_cache
    _dijkstra_cache = {}

class TreeNode:
    """
    Representa um nó na árvore de busca do algoritmo A*.
    
    Cada TreeNode encapsula um estado completo do problema de roteamento:
    - Localização atual do veículo
    - Tarefas já iniciadas (pickups realizados)
    - Tarefas já completadas (deliveries realizados)
    - Carga atual e combustível disponível
    - Custos g(n) e h(n) para avaliação A*
    
    A árvore é construída dinamicamente pelo algoritmo A*, expandindo nós com
    menor f(n) = g(n) + h(n) até atingir a profundidade alvo (2 * num_tasks).
    
    Attributes:
        state (list[tuple]): Estado global das tarefas como [(sender, receiver, qty, orderid), ...].
        parent (TreeNode | None): Nó pai na árvore (None para raiz).
        location (int): ID do nó atual no grafo.
        order_id (int | None): ID da ordem associada à transição que gerou este nó.
        children (list[TreeNode]): Lista de nós filhos expandidos.
        initial_points_reached (list[tuple]): Pickups realizados como [(orderid, location), ...].
        end_points_reached (list[tuple]): Deliveries realizados como [(orderid, location), ...].
        available_points (list[tuple]): Pontos disponíveis para próxima expansão.
        depth (int): Profundidade na árvore (0 = raiz, objetivo = 2*num_tasks).
        quantity (int): Carga atual do veículo.
        max_fuel (int): Capacidade máxima do tanque.
        max_quantity (int): Capacidade máxima de carga.
        h (float): Heurística h(n) - estimativa de custo até o objetivo.
        g (float): Custo g(n) - custo acumulado desde a raiz.
        f (float): Função de avaliação f(n) = g(n) + h(n).
        average_cost_per_task (float): Custo médio por tarefa (usado em h(n)).
        lambda_penalty (int): Penalização por tarefas ativas (padrão: 2).
    
    Exemplo:
        >>> root = TreeNode(
        ...     location=0,
        ...     state=[(3, 7, 10, 1), (5, 9, 15, 2)],
        ...     max_quantity=50,
        ...     max_fuel=100,
        ...     depth=0,
        ...     initial_points_reached=[],
        ...     end_points_reached=[],
        ...     h=45.5,
        ...     g=0.0
        ... )
        >>> root.available_points = root.evaluate_available_points(graph)
        >>> root.create_childs()
        >>> print(len(root.children))  # 2 (um filho para cada pickup disponível)
    
    Note:
        - Comparação (__gt__, __eq__) baseada em f(n) para PriorityQueue
        - order_id é None para nó raiz
        - depth objetivo = 2 * num_tasks (pickup + delivery para cada tarefa)
    """
    
    def __init__(self, 
                 location,
                 state: list["Order"],
                 max_quantity:int=0, 
                 max_fuel:int=0,parent=None,
                 depth=0,initial_points_reached:list[int]=0,
                 end_points_reached:list[int]=0, 
                 h=0,
                 g=0,
                 average_cost_per_task:float=0,
                 lambda_penalty:int=2,
                 order_id=None):
        """
        Inicializa um novo nó na árvore de busca A*.
        
        Args:
            location: ID do nó atual no grafo.
            state: Lista de tarefas como tuplas (sender, receiver, qty, orderid).
            max_quantity: Capacidade máxima de carga do veículo.
            max_fuel: Capacidade máxima do tanque de combustível.
            parent: Nó pai na árvore (None para raiz).
            depth: Profundidade na árvore (incrementa a cada expansão).
            initial_points_reached: Lista de pickups realizados [(orderid, location), ...].
            end_points_reached: Lista de deliveries realizados [(orderid, location), ...].
            h: Valor da heurística h(n).
            g: Custo acumulado g(n).
            average_cost_per_task: Custo médio por tarefa para cálculo de h(n).
            lambda_penalty: Penalização por tarefas ativas (padrão: 2).
            order_id: ID da ordem associada à transição (None para raiz).
        
        Note:
            - f(n) é calculado automaticamente como g + h
            - quantity é inicializado como 0 e atualizado em create_childs()
        """
        self.state = state
        self.parent = parent
        self.location = location
        self.order_id = order_id  # ID da ordem associada a este nó
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
        """
        Operador de comparação maior que (>) baseado em f(n).
        
        Usado pela PriorityQueue para ordenar nós. Nós com menor f(n) têm
        maior prioridade (são expandidos primeiro).
        
        Args:
            other: Outro TreeNode para comparar.
        
        Returns:
            True se self.f > other.f, False caso contrário.
        """
        return self.f > other.f
    
    def __eq__ (self, other):
        """
        Operador de igualdade (==) baseado em estado.
        
        Dois nós são iguais se têm o mesmo estado de tarefas, independentemente
        de localização ou custos. Usado para detectar estados duplicados.
        
        Args:
            other: Outro TreeNode para comparar.
        
        Returns:
            True se self.state == other.state, False caso contrário.
        """
        return self.state == other.state
    
    def add_child(self, child_node):
        """
        Adiciona um nó filho à lista de filhos.
        
        Args:
            child_node: TreeNode a ser adicionado como filho.
        
        Side Effects:
            Modifica self.children.
        """
        self.children.append(child_node)

    def create_childs(self):
        """
        Expande o nó atual criando todos os filhos viáveis.
        
        Para cada ponto disponível (pickup ou delivery), cria um novo nó filho
        representando a transição para esse ponto. Atualiza estado, carga,
        custos e calcula nova heurística.
        
        Algoritmo:
            1. Para cada ponto em available_points:
               - Copia listas de pontos alcançados
               - Atualiza carga (+ para pickup, - para delivery)
               - Cria novo TreeNode com depth+1
               - Calcula g(n) = parent.g + tempo_viagem
               - Calcula h(n) com novo estado
               - Adiciona filho à lista de children
        
        Side Effects:
            - Modifica self.children (adiciona novos nós)
            - Cada filho tem referência a self como parent
        
        Formato de available_points:
            Lista de tuplas (location, orderid, quantity, time, type) onde:
            - location: ID do nó destino
            - orderid: ID da ordem
            - quantity: Quantidade a carregar/descarregar
            - time: Tempo de viagem até location
            - type: 1=warehouse (pickup), 0=customer (delivery)
        
        Exemplo:
            >>> node.available_points = [(3, 1, 10, 5.5, 1), (7, 2, 15, 8.2, 1)]
            >>> node.create_childs()
            >>> print(len(node.children))  # 2
            >>> print(node.children[0].location)  # 3
            >>> print(node.children[0].quantity)  # 10 (pickup)
        
        Note:
            - Deve chamar evaluate_available_points() antes deste método
            - Filhos herdam state, max_quantity, max_fuel do pai
            - order_id associado ao filho identifica qual ordem gerou a transição
        """
        for point in self.available_points:
            new_initial_points_reached = self.initial_points_reached.copy()
            new_end_points_reached = self.end_points_reached.copy()
            new_quantity = self.quantity
            point_order_id = point[1]  # order_id está no índice 1
            
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
                average_cost_per_task=self.average_cost_per_task,
                order_id=point_order_id  # Associar order_id ao nó
            )
            child_node.quantity = new_quantity
            self.add_child(child_node)

    def evaluate_available_points(self,graph: Graph):
        """
        Avalia quais pontos (pickups/deliveries) são alcançáveis a partir do nó atual.
        
        Verifica todas as tarefas no estado e determina quais transições são viáveis
        considerando:
        - Restrições de capacidade (não exceder max_quantity)
        - Restrições de combustível (não exceder max_fuel)
        - Sequência lógica (pickup antes de delivery)
        - Pontos já visitados (evitar duplicatas)
        
        Lógica de Decisão:
            Para cada tarefa (sender, receiver, qty, orderid) em state:
            
            1. Se pickup ainda não realizado:
               - Verifica se qty + current_load ≤ max_quantity
               - Calcula rota e combustível usando get_dijkstra_cached
               - Se fuel ≤ max_fuel: adiciona sender aos disponíveis (type=1)
            
            2. Se pickup já realizado mas delivery não:
               - Calcula rota e combustível até receiver
               - Se fuel ≤ max_fuel: adiciona receiver aos disponíveis (type=0)
        
        Args:
            graph: Instância de Graph para calcular rotas via Dijkstra.
        
        Returns:
            Lista de tuplas (location, orderid, quantity, time, type) onde:
            - location (int): ID do nó destino
            - orderid (int): ID da ordem associada
            - quantity (int): Quantidade a carregar/descarregar
            - time (float): Tempo de viagem até location
            - type (int): 1=warehouse (pickup), 0=customer (delivery)
        
        Exemplo:
            >>> node = TreeNode(location=0, state=[(3, 7, 10, 1), (5, 9, 15, 2)], ...)
            >>> available = node.evaluate_available_points(graph)
            >>> print(available)
            # [(3, 1, 10, 5.5, 1), (5, 2, 15, 8.2, 1)]  # Dois pickups disponíveis
            
            >>> # Após fazer pickup da ordem 1:
            >>> node2 = TreeNode(location=3, initial_points_reached=[(1, 3)], ...)
            >>> available2 = node2.evaluate_available_points(graph)
            >>> print(available2)
            # [(7, 1, 10, 3.2, 0), (5, 2, 15, 6.1, 1)]  # Delivery 1 + Pickup 2
        
        Note:
            - Usa cache de Dijkstra via get_dijkstra_cached para performance
            - Não modifica estado do nó (método puro)
            - Resultado deve ser atribuído a self.available_points manualmente
        """
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
        """
        Cria uma visualização gráfica da árvore de busca usando matplotlib e networkx.
        
        Gera uma imagem PNG mostrando toda a árvore de busca expandida pelo A*.
        Cada nó mostra:
        - Localização (Loc)
        - Profundidade (D)
        - Função de avaliação f(n)
        - Componentes g(n) e h(n)
        
        Características visuais:
        - Cores: Gradiente por profundidade (viridis colormap)
        - Layout: Hierárquico (raiz no topo, crescendo para baixo)
        - Setas: Indicam direção pai → filho
        - Tamanho: 32x20 polegadas, 300 DPI
        
        Limitações:
        - Não gera imagem se total_nodes >= 1000 (evita arquivo enorme)
        - Requer matplotlib e networkx instalados
        
        Args:
            filename: Nome do arquivo PNG a salvar (padrão: "search_tree.png").
        
        Side Effects:
            - Cria arquivo de imagem no diretório atual
            - Imprime estatísticas da árvore (total de nós, profundidade máxima)
        
        Raises:
            ImportError: Se matplotlib ou networkx não estiverem instalados.
        
        Exemplo:
            >>> path, time, tree = A_star_task_algorithm(...)
            >>> tree.plot_tree("my_search_tree.png")
            # 📊 Estatísticas da árvore de pesquisa:
            #   Total de nós: 245
            #   Profundidade máxima: 6
            # ✓ Árvore de pesquisa salva em: my_search_tree.png
        
        Note:
            - Função auxiliar count_nodes percorre recursivamente
            - Função auxiliar get_max_depth calcula profundidade
            - Layout usa algoritmo hierárquico com espaçamento adaptativo
        """
        
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
    """
    Calcula a heurística h(n) para estimativa de custo restante até o objetivo.
    
    Implementa uma heurística admissível baseada em:
    1. Custo médio por tarefa × tarefas restantes (estimativa otimista)
    2. Penalização por tarefas ativas (incentiva a pegar tarefas antes de acabar outras)
    
    Fórmula:
        h(n) = custo_médio_por_tarefa × (tarefas_totais - tarefas_concluídas)
               - λ × tarefas_ativas
    
    Onde:
        - tarefas_totais = len(state)
        - tarefas_concluídas = len(end_points_reached)
        - tarefas_ativas = len(initial_points_reached) - tarefas_concluídas
        - λ = lambda_penalty (padrão: 2)
    
    Admissibilidade:
        A heurística é admissível se average_cost_per_task ≤ custo real mínimo
        por tarefa. Como average_cost é calculado a partir das tarefas reais,
        isto geralmente é verdade (pode subestimar por não considerar backtracking).
    
    Args:
        state: Lista de tarefas como [(sender, receiver, qty, orderid), ...].
        end_points_reached: Lista de deliveries completados [(orderid, location), ...].
        initial_points_reached: Lista de pickups realizados [(orderid, location), ...].
        average_cost_per_task: Custo médio por tarefa calculado no início.
        lambda_penalty: Fator de penalização para tarefas ativas (padrão: 2).
    
    Returns:
        Valor da heurística h(n) como float.
    
    Exemplo:
        >>> state = [(3, 7, 10, 1), (5, 9, 15, 2), (2, 8, 5, 3)]
        >>> h = calculate_heuristic(
        ...     state=state,
        ...     end_points_reached=[(1, 7)],  # Tarefa 1 completada
        ...     initial_points_reached=[(1, 3), (2, 5)],  # Tarefas 1 e 2 iniciadas
        ...     average_cost_per_task=10.0,
        ...     lambda_penalty=2
        ... )
        >>> # h = 10.0 * (3 - 1) - 2 * (2 - 1) = 20.0 - 2.0 = 18.0
        >>> print(h)  # 18.0
    
    Note:
        - Penalização λ incentiva veículo a completar deliveries antes de novos pickups
        - Valor mais alto de λ favorece rotas com menos carga simultânea
        - Valor λ=0 ignora penalização 
    """
    total_tasks = len(state)
    completed_tasks = len(end_points_reached)
    active_tasks = len(initial_points_reached) - completed_tasks
    average_cost_per_task = average_cost_per_task
    return (average_cost_per_task * (total_tasks - completed_tasks)) - (lambda_penalty * active_tasks)


def A_star_task_algorithm(graph: Graph, start:int, tasks:list["Order"],capacity:int, max_fuel: int):
    """
    Executa o algoritmo A* para encontrar a sequência ótima de pickups e deliveries.
    
    Resolve o problema de Vehicle Routing Problem (VRP) com restrições de capacidade
    e combustível, encontrando a rota que minimiza o tempo total de execução de
    todas as tarefas.
    
    Algoritmo:
        1. Inicialização:
           - Limpa cache de Dijkstra
           - Calcula custo médio por tarefa para heurística
           - Cria estado inicial como lista de (sender, receiver, qty, orderid)
           - Cria nó raiz em location=start
        
        2. Busca A*:
           - Usa PriorityQueue para expandir nós com menor f(n)
           - Para cada nó: avalia pontos disponíveis, cria filhos
           - Adiciona filhos à fila
           - Para quando depth = 2 * num_tasks (todas tarefas concluídas)
        
        3. Reconstrução de Caminho:
           - Percorre parent links do nó objetivo até raiz
           - Constrói lista de (location, order_id)
           - Reverte lista para ordem cronológica
    
    Args:
        graph: Instância de Graph com a topologia da rede.
        start: ID do nó inicial do veículo.
        tasks: Lista de objetos Order a serem executados.
        capacity: Capacidade máxima de carga do veículo.
        max_fuel: Capacidade máxima do tanque de combustível.
    
    Returns:
        Tupla (path, total_time, tree) onde:
        - path (list[tuple]): Sequência de (node_id, order_id) representando a rota.
          - Primeiro elemento: (start, None) - posição inicial
          - Elementos seguintes: (location, orderid) - pickups e deliveries
        - total_time (float): Tempo total para completar todas as tarefas.
        - tree (TreeNode): Raiz da árvore de busca (para visualização).
    
    Exemplo:
        >>> from world.graph import Graph
        >>> graph = Graph()
        >>> orders = [
        ...     Order(product="A", quantity=10, orderid=1, 
        ...           sender="w1", receiver="s1", 
        ...           sender_location=3, receiver_location=7),
        ...     Order(product="B", quantity=15, orderid=2,
        ...           sender="w2", receiver="s2",
        ...           sender_location=5, receiver_location=9)
        ... ]
        >>> path, time, tree = A_star_task_algorithm(
        ...     graph=graph,
        ...     start=0,
        ...     tasks=orders,
        ...     capacity=50,
        ...     max_fuel=100
        ... )
        >>> print(path)
        # [(0, None), (3, 1), (7, 1), (5, 2), (9, 2)]
        >>> print(f"Tempo total: {time}s")
        # Tempo total: 45.3s
        >>> tree.plot_tree("route_search.png")
    
    Edge Cases:
        - Se tasks vazio: retorna ([(start, None)], 0.0, root)
        - Se nenhuma solução viável: retorna (None, float('inf'), root)
    
    Note:
        - Objetivo é depth = 2 * len(tasks) (1 pickup + 1 delivery por tarefa)
        - PriorityQueue usa (f, id(node), node) para desempate por ID
        - order_id=None no nó raiz (posição inicial sem tarefa associada)
    """
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
            # Reconstruir o caminho como lista de tuplos (location, order_id)
            path = []
            node = current_node
            while node is not None:
                if node.order_id is not None:  # Pular o nó raiz que não tem order_id
                    path.append((node.location, node.order_id))
                elif node.parent is None:  # Nó raiz - adicionar só a localização inicial
                    path.append((node.location, None))
                node = node.parent
            path.reverse()
            
            # Retornar: caminho com tuplos (location, order_id), tempo total, árvore de pesquisa
            total_time = current_node.g
            return path, total_time, root
        
        # Avaliar pontos disponíveis
        current_node.available_points = current_node.evaluate_available_points(graph)
        # Criar filhos
        current_node.create_childs()
        
        # Adicionar filhos à fila de prioridade
        for child in current_node.children:
            open_list.put((child.f, id(child), child))
    
    root.plot_tree("route_search.png")
    
    return None, float('inf'), root


