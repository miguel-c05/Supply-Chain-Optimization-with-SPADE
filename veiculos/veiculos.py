from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from ..world.graph import Graph  # Supondo que tens uma classe Graph definida em world/graph.py
from collections import deque

class VehicleAgent(Agent):
    """
    Representa um veículo na rede. 
    Cada veículo tem combustível, capacidade e um grafo local do mapa.
    Ele recebe propostas de entrega e atualizações de mapa.
    """

    def __init__(self, jid, password, graph: Graph, capacity: int, fuel: float):
        super().__init__(jid, password)
        self.graph = graph                # Grafo local (objeto da tua classe Graph)
        self.capacity = capacity          # Capacidade máxima do veículo
        self.fuel = fuel                  # Quantidade atual de combustível
        self.max_fuel = fuel              # Fuel máximo do veículo
        self.current_route = []           # Rota atual, lista de edges
        self.current_position = None      # Nó atual no mapa
        self.target_vertex = None         # Vértice para o qual está se deslocando
        self.pending_deliveries = deque() # Queue de pedidos pendentes (FIFO)
        self.is_moving = False            # Flag para indicar se está em movimento

    async def setup(self):
        print(f"[{self.name}] Pronto para receber mensagens.")
        self.add_behaviour(self.VehicleBehaviour())

    class VehicleBehaviour(CyclicBehaviour):
        """
        Comportamento principal: escuta mensagens de propostas e atualizações.
        """

        async def run(self):
            msg = await self.receive(timeout=5)
            if msg:
                if msg.metadata and msg.metadata.get("type") == "proposal":
                    await self.handle_delivery_proposal(msg)
                elif msg.metadata and msg.metadata.get("type") == "graph_update":
                    await self.handle_graph_update(msg)
                elif msg.metadata and msg.metadata.get("type") == "init_graph":
                    await self.handle_initial_graph(msg)
            else:
                # Podes usar este espaço para verificar se há entregas em curso
                pass

        async def handle_initial_graph(self, msg: Message):
            """
            Recebe o grafo inicial do servidor ou de outro agente.
            """
            # Exemplo: o corpo da mensagem contém uma versão serializada do grafo
            data = msg.body
            self.agent.graph.load_from_serialized(data)
            print(f"[{self.agent.name}] Grafo inicial carregado com sucesso.")

        async def handle_delivery_proposal(self, msg: Message):
            """
            Recebe uma proposta de entrega: origem, destino e quantidade.
            Adiciona a tarefa no final da queue (última prioridade).
            """
            proposal = self.parse_proposal(msg.body)
            print(f"[{self.agent.name}] Proposta recebida: {proposal}")

            # Adicionar tarefa no final da queue (última prioridade)
            task = {
                'origin': proposal.get('origin'),
                'destination': proposal.get('destination'),
                'quantity': proposal.get('quantity', 0)
            }
            self.agent.pending_deliveries.append(task)
            print(f"[{self.agent.name}] Tarefa adicionada à queue. Total de tarefas pendentes: {len(self.agent.pending_deliveries)}")
            
            # Se não está em movimento, calcular nova rota
            if not self.agent.is_moving:
                await self.calculate_and_start_route()

        async def handle_graph_update(self, msg: Message):
            """
            Recebe uma atualização do grafo e aplica-a localmente.
            Apenas faz reroute quando o veículo não está em movimento.
            """
            update_data = self.parse_graph_update(msg.body)
            print(f"[{self.agent.name}] Atualização de mapa recebida: {update_data}")

            # Atualizar o grafo local
            # TODO: implementar graph.update_edge() com os dados de update_data
            # Exemplo: self.agent.graph.update_edge(update_data['from'], update_data['to'], update_data)
            
            # Se está em movimento, espera chegar ao target_vertex antes de fazer reroute
            if self.agent.is_moving:
                print(f"[{self.agent.name}] Em movimento para {self.agent.target_vertex}. Reroute será feito ao chegar.")
            else:
                # Se não está em movimento, pode fazer reroute imediatamente
                print(f"[{self.agent.name}] Calculando novo reroute...")
                await self.reroute()

        def parse_proposal(self, raw_data):
            """
            Converte a string recebida em estrutura de dados de proposta.
            Exemplo: '{"origin": "A", "destination": "C", "quantity": 5}'
            """
            import json
            return json.loads(raw_data)

        def parse_graph_update(self, raw_data):
            """
            Converte a mensagem de atualização em dicionário.
            Exemplo: '{"from": "A", "to": "B", "distance": 10, "status": "blocked"}'
            """
            import json
            return json.loads(raw_data)
        
        async def calculate_and_start_route(self):
            """
            Calcula a rota inicial para todas as tarefas pendentes.
            """
            if not self.agent.pending_deliveries:
                print(f"[{self.agent.name}] Sem tarefas pendentes.")
                return
            
            print(f"[{self.agent.name}] Calculando rota para {len(self.agent.pending_deliveries)} tarefas...")
            
            # Calcular rota completa usando a ordem atual da queue
            route = self.calculate_route_from_queue()
            
            if route:
                self.agent.current_route = route
                print(f"[{self.agent.name}] Rota calculada com {len(route)} edges.")
                await self.start_movement()
            else:
                print(f"[{self.agent.name}] Não foi possível calcular rota válida.")
        
        async def reroute(self):
            """
            Recalcula a rota mantendo a ordem das tarefas, mas ajustando o caminho.
            Remove o target_vertex atual da rota se o veículo está em movimento.
            """
            if not self.agent.pending_deliveries:
                print(f"[{self.agent.name}] Sem tarefas para fazer reroute.")
                return
            
            print(f"[{self.agent.name}] Recalculando rota...")
            
            # Calcular nova rota a partir da posição atual
            route = self.calculate_route_from_queue()
            
            if route:
                self.agent.current_route = route
                print(f"[{self.agent.name}] Reroute concluído. Nova rota com {len(route)} edges.")
                
                # Se não está em movimento, iniciar
                if not self.agent.is_moving:
                    await self.start_movement()
            else:
                print(f"[{self.agent.name}] Reroute falhou. Sem rota válida.")
        
        def calculate_route_from_queue(self):
            """
            Calcula a rota seguindo a ordem FIFO das tarefas pendentes.
            Usa min_caminho para calcular cada segmento.
            
            Returns:
                Lista de edges formando a rota completa, ou None se não houver rota válida
            """
            if not self.agent.pending_deliveries:
                return None
            
            current_pos = self.agent.current_position
            current_fuel = self.agent.fuel
            complete_route = []
            
            # Processar cada tarefa na ordem da queue
            for task in self.agent.pending_deliveries:
                origin = task['origin']
                destination = task['destination']
                
                # Caminho 1: posição atual até origem da tarefa
                fuel1, time1, edges1 = self.min_caminho(self.agent.graph, current_pos, origin)
                
                if fuel1 is None or fuel1 > current_fuel:
                    print(f"[{self.agent.name}] Sem combustível para chegar à origem {origin}.")
                    return None  # Não consegue completar a rota
                
                # Adicionar edges ao percurso
                complete_route.extend(edges1)
                
                # Abastecer ao chegar na origem
                current_fuel = self.agent.max_fuel
                current_pos = origin
                
                # Caminho 2: origem até destino da tarefa
                fuel2, time2, edges2 = self.min_caminho(self.agent.graph, origin, destination)
                
                if fuel2 is None or fuel2 > current_fuel:
                    print(f"[{self.agent.name}] Sem combustível para completar entrega {origin} -> {destination}.")
                    return None
                
                # Adicionar edges ao percurso
                complete_route.extend(edges2)
                
                # Abastecer ao chegar no destino
                current_fuel = self.agent.max_fuel
                current_pos = destination
            
            return complete_route if complete_route else None
        
        async def start_movement(self):
            """
            Inicia o movimento do veículo seguindo a rota calculada.
            """
            if not self.agent.current_route:
                print(f"[{self.agent.name}] Sem rota para seguir.")
                return
            
            self.agent.is_moving = True
            
            # Definir o próximo vértice alvo (primeiro edge da rota)
            if self.agent.current_route:
                first_edge = self.agent.current_route[0]
                # Assumindo que edge tem atributo 'to' ou similar
                self.agent.target_vertex = first_edge.target if hasattr(first_edge, 'target') else first_edge.to
                print(f"[{self.agent.name}] Iniciando movimento para {self.agent.target_vertex}.")
        
        async def on_arrival_at_vertex(self):
            """
            Chamada quando o veículo chega ao target_vertex.
            Atualiza a posição, remove o edge da rota e verifica se completou alguma tarefa.
            """
            if not self.agent.is_moving:
                return
            
            print(f"[{self.agent.name}] Chegou ao vértice {self.agent.target_vertex}.")
            
            # Atualizar posição atual
            self.agent.current_position = self.agent.target_vertex
            
            # Remover o primeiro edge da rota (já percorrido)
            if self.agent.current_route:
                completed_edge = self.agent.current_route.pop(0)
                
                # Atualizar combustível (subtrair o consumido)
                # Assumindo que edge tem weight que representa consumo
                if hasattr(completed_edge, 'weight'):
                    self.agent.fuel -= completed_edge.weight
            
            # Verificar se completou alguma tarefa
            await self.check_task_completion()
            
            # Verificar se há mais edges na rota
            if self.agent.current_route:
                # Continuar para o próximo vértice
                next_edge = self.agent.current_route[0]
                self.agent.target_vertex = next_edge.target if hasattr(next_edge, 'target') else next_edge.to
                print(f"[{self.agent.name}] Próximo destino: {self.agent.target_vertex}.")
            else:
                # Rota completada
                self.agent.is_moving = False
                self.agent.target_vertex = None
                print(f"[{self.agent.name}] Rota completada. Veículo parado.")
        
        async def check_task_completion(self):
            """
            Verifica se a posição atual corresponde ao destino de alguma tarefa.
            Remove tarefas completadas da queue.
            """
            if not self.agent.pending_deliveries:
                return
            
            # Verificar a primeira tarefa da queue (FIFO)
            first_task = self.agent.pending_deliveries[0]
            
            # Se chegou ao destino da tarefa, completou a entrega
            if self.agent.current_position == first_task['destination']:
                completed_task = self.agent.pending_deliveries.popleft()
                print(f"[{self.agent.name}] Tarefa completada: {completed_task['origin']} -> {completed_task['destination']}")
                
                # Reabastecer ao completar entrega
                self.agent.fuel = self.agent.max_fuel
                print(f"[{self.agent.name}] Combustível reabastecido: {self.agent.fuel}")
            
            # Se chegou à origem de uma tarefa, também pode reabastecer
            elif self.agent.current_position == first_task['origin']:
                self.agent.fuel = self.agent.max_fuel
                print(f"[{self.agent.name}] Chegou à origem. Combustível reabastecido: {self.agent.fuel}")
        
        def min_caminho(self, graph: Graph, inicio, fim):
            """
            Calcula o caminho mínimo entre dois nós usando Dijkstra.
            Retorna: (fuel_consumido, tempo, lista_de_edges)
            """
            import heapq
            
            # Dijkstra para encontrar o caminho mais curto
            distances = {node_id: float('inf') for node_id in graph.nodes}
            distances[inicio] = 0
            previous = {node_id: None for node_id in graph.nodes}
            pq = [(0, inicio)]  # (distância, nó)
            
            while pq:
                current_dist, current_node = heapq.heappop(pq)
                
                if current_dist > distances[current_node]:
                    continue
                
                if current_node == fim:
                    break
                
                # Explorar vizinhos
                for neighbor in graph.get_neighbors(current_node):
                    edge = graph.get_edge(current_node, neighbor.id)
                    if edge and edge.weight is not None:
                        distance = current_dist + edge.weight
                        
                        if distance < distances[neighbor.id]:
                            distances[neighbor.id] = distance
                            previous[neighbor.id] = current_node
                            heapq.heappush(pq, (distance, neighbor.id))
            
            # Reconstruir o caminho
            if distances[fim] == float('inf'):
                return None, None, None  # Caminho não existe
            
            path = []
            edges = []
            current = fim
            while previous[current] is not None:
                path.append(current)
                edge = graph.get_edge(previous[current], current)
                edges.append(edge)
                current = previous[current]
            path.append(inicio)
            path.reverse()
            edges.reverse()
            
            # Assumindo que fuel e tempo são proporcionais ao peso da aresta
            total_fuel = distances[fim]
            total_time = distances[fim]
            
            return total_fuel, total_time, edges
            
            