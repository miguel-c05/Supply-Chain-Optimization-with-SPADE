"""
Exemplo de como integrar o VehicleAgent com o ClockAgent
usando as funções utilitárias.
"""

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from collections import deque
import json

# Importar utilitários do relógio
import sys
sys.path.append('..')
from Relogio.clock_utils import ClockSyncMixin, confirm_tick, is_new_tick_message, parse_tick_message


class VehicleAgentWithClock(Agent, ClockSyncMixin):
    """
    VehicleAgent integrado com o ClockAgent.
    Usa ClockSyncMixin para facilitar a sincronização.
    """

    def __init__(self, jid, password, graph, capacity: int, fuel: float, clock_jid: str):
        super().__init__(jid, password)
        
        # Atributos do veículo
        self.graph = graph
        self.capacity = capacity
        self.fuel = fuel
        self.max_fuel = fuel
        self.current_route = []
        self.current_position = None
        self.target_vertex = None
        self.pending_deliveries = deque()
        self.is_moving = False
        
        # Configurar sincronização com o relógio
        self.setup_clock_sync(clock_jid)

    async def setup(self):
        print(f"[{self.name}] Veículo iniciando...")
        
        # Adicionar comportamento do veículo
        self.add_behaviour(self.VehicleBehaviour())
        
        # Adicionar comportamento de sincronização com o relógio
        self.add_behaviour(self.ClockSyncBehaviour())
        
        # Registrar no relógio (UMA VEZ)
        await self.register_with_clock()
        print(f"[{self.name}] Registrado no relógio.")

    class VehicleBehaviour(CyclicBehaviour):
        """
        Comportamento principal do veículo: escuta propostas e atualizações.
        """

        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                msg_type = msg.metadata.get("type") if msg.metadata else None
                
                if msg_type == "proposal":
                    await self.handle_delivery_proposal(msg)
                elif msg_type == "graph_update":
                    await self.handle_graph_update(msg)

        async def handle_delivery_proposal(self, msg: Message):
            """Adiciona proposta de entrega à queue"""
            proposal = json.loads(msg.body)
            print(f"[{self.agent.name}] Proposta recebida: {proposal}")
            
            task = {
                'origin': proposal.get('origin'),
                'destination': proposal.get('destination'),
                'quantity': proposal.get('quantity', 0)
            }
            self.agent.pending_deliveries.append(task)
            print(f"[{self.agent.name}] Tarefa adicionada. Total: {len(self.agent.pending_deliveries)}")

        async def handle_graph_update(self, msg: Message):
            """Processa atualização do grafo"""
            update_data = json.loads(msg.body)
            print(f"[{self.agent.name}] Atualização de mapa: {update_data}")
            # Implementar lógica de atualização do grafo

    class ClockSyncBehaviour(CyclicBehaviour):
        """
        Comportamento dedicado à sincronização com o relógio.
        Processa cada tick e executa a lógica do veículo.
        """

        async def run(self):
            msg = await self.receive(timeout=10)
            
            if msg:
                # Usar o mixin para processar mensagens do relógio
                msg_type, data = self.agent.handle_clock_message(msg)
                
                if msg_type == 'register_confirm':
                    print(f"[{self.agent.name}] Confirmação de registro no relógio. Tick: {data.get('current_tick')}")
                
                elif msg_type == 'new_tick':
                    tick = data['tick']
                    tick_duration = data['tick_duration']
                    
                    # Processar lógica do veículo para este tick
                    await self.process_vehicle_tick(tick, tick_duration)
                    
                    # Confirmar tick processado (usando o mixin)
                    await self.agent.confirm_tick(tick, {
                        'position': self.agent.current_position,
                        'fuel': self.agent.fuel,
                        'is_moving': self.agent.is_moving
                    })

        async def process_vehicle_tick(self, tick: int, tick_duration: float):
            """
            Lógica do veículo executada a cada tick.
            
            Args:
                tick: Número do tick atual
                tick_duration: Duração do tick em segundos
            """
            print(f"[{self.agent.name}] Processando tick {tick}")
            
            # 1. Se está em movimento, mover um passo
            if self.agent.is_moving and self.agent.current_route:
                await self.move_one_step()
            
            # 2. Verificar se completou alguma tarefa
            await self.check_task_completion()
            
            # 3. Se não está em movimento e há tarefas, calcular rota
            if not self.agent.is_moving and self.agent.pending_deliveries:
                await self.calculate_and_start_route()

        async def move_one_step(self):
            """
            Move o veículo um edge na rota.
            Simula movimento de um vértice para o próximo.
            """
            if not self.agent.current_route:
                return
            
            # Pegar o próximo edge
            current_edge = self.agent.current_route[0]
            
            # Assumindo que edge tem atributo 'to' ou similar
            next_vertex = current_edge.to if hasattr(current_edge, 'to') else current_edge[1]
            
            print(f"[{self.agent.name}] Movendo de {self.agent.current_position} para {next_vertex}")
            
            # Atualizar posição
            self.agent.current_position = next_vertex
            
            # Consumir combustível
            if hasattr(current_edge, 'weight'):
                self.agent.fuel -= current_edge.weight
            
            # Remover edge da rota
            self.agent.current_route.pop(0)
            
            # Verificar se chegou ao destino
            if not self.agent.current_route:
                self.agent.is_moving = False
                self.agent.target_vertex = None
                print(f"[{self.agent.name}] Chegou ao destino {next_vertex}!")

        async def check_task_completion(self):
            """
            Verifica se completou alguma entrega.
            Reabastece ao chegar em origem ou destino.
            """
            if not self.agent.pending_deliveries:
                return
            
            first_task = self.agent.pending_deliveries[0]
            
            # Completou a entrega
            if self.agent.current_position == first_task['destination']:
                completed = self.agent.pending_deliveries.popleft()
                print(f"[{self.agent.name}] ✓ Entrega completada: {completed['origin']} → {completed['destination']}")
                
                # Reabastecer
                self.agent.fuel = self.agent.max_fuel
                print(f"[{self.agent.name}] Reabastecido. Fuel: {self.agent.fuel}")
            
            # Chegou à origem
            elif self.agent.current_position == first_task['origin']:
                self.agent.fuel = self.agent.max_fuel
                print(f"[{self.agent.name}] Na origem. Reabastecido. Fuel: {self.agent.fuel}")

        async def calculate_and_start_route(self):
            """
            Calcula rota para as tarefas pendentes e inicia movimento.
            """
            print(f"[{self.agent.name}] Calculando rota para {len(self.agent.pending_deliveries)} tarefas...")
            
            # Aqui você implementaria a lógica de cálculo de rota
            # usando min_caminho() ou update_route()
            
            # Exemplo simplificado:
            # route = self.calculate_route_from_queue()
            # if route:
            #     self.agent.current_route = route
            #     self.agent.is_moving = True
            #     self.agent.target_vertex = route[0].to
            #     print(f"[{self.agent.name}] Iniciando movimento...")


# Exemplo de uso
async def example_vehicle_simulation():
    """
    Exemplo de simulação com ClockAgent e VehicleAgent.
    """
    import asyncio
    from Relogio.Relogio import ClockAgent
    
    # Criar relógio
    clock = ClockAgent("clock@localhost", "password", tick_duration_seconds=1.0)
    await clock.start()
    
    # Criar veículos (exemplo sem grafo real)
    vehicle1 = VehicleAgentWithClock(
        "vehicle1@localhost", 
        "password",
        graph=None,  # Passar grafo real aqui
        capacity=100,
        fuel=50.0,
        clock_jid="clock@localhost"
    )
    
    await vehicle1.start()
    
    # Aguardar registro
    await asyncio.sleep(2)
    
    # Iniciar simulação
    print("\n========== INICIANDO SIMULAÇÃO ==========\n")
    clock.start_simulation()
    
    # Simular por 10 ticks
    await asyncio.sleep(10)
    
    # Parar
    print("\n========== PARANDO SIMULAÇÃO ==========\n")
    clock.stop_simulation()
    
    await vehicle1.stop()
    await clock.stop()


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_vehicle_simulation())
