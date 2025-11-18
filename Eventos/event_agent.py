"""
Event-Driven Agent para simular eventos do ambiente.
Usa uma min heap para ordenar eventos por tempo e processa periodicamente.
"""

import asyncio
import heapq
import json
from datetime import datetime
from typing import List, Dict, Any
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.presence import PresenceType, PresenceShow


class Event:
    """
    Classe para representar um evento.
    Comparável para ordenação na min heap por tempo.
    """
    
    def __init__(self, event_type: str, time: float, data: Dict[str, Any], 
                 sender: str = None, timestamp: str = None):
        self.event_type = event_type  # "arrival", "transit", etc.
        self.time = time  # Tempo do evento
        self.data = data  # Dados do evento
        self.sender = sender  # Quem enviou o evento
        self.timestamp = timestamp or datetime.now().isoformat()
    
    def __lt__(self, other):
        """Comparação para min heap - menor tempo tem prioridade"""
        return self.time < other.time
    
    def __le__(self, other):
        return self.time <= other.time
    
    def __gt__(self, other):
        return self.time > other.time
    
    def __ge__(self, other):
        return self.time >= other.time
    
    def __eq__(self, other):
        return self.time == other.time
    
    def __repr__(self):
        return f"Event(type={self.event_type}, time={self.time:.2f}, sender={self.sender})"
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte o evento para dicionário para envio"""
        if self.event_type == "arrival":
            return {
                "type": self.event_type,
                "time": self.time,
                "vehicle": self.sender.split('@')[0],
            }


class EventDrivenAgent(Agent):
    """
    Agente que gerencia eventos usando min heap.
    Recebe eventos continuamente e processa a cada 5 segundos.
    """
    
    def __init__(self, jid: str, password: str, simulation_interval: float = 5.0, registered_vehicles: List[str] = [],
                 registered_warehouses: List[str] = [], registered_stores: List[str] = [],
                 world_agent: str = None):
        super().__init__(jid, password)
        self.event_heap = []  # Min heap de eventos (não-trânsito)
        self.transit_events = []  # Lista separada para eventos de trânsito
        self.simulation_interval = simulation_interval  # Intervalo de simulação (5s)
        self.registered_vehicles = registered_vehicles  # Veículos registrados
        self.registered_warehouses = registered_warehouses  # Warehouses registrados
        self.registered_stores = registered_stores  # Stores registrados
        self.world_agent = world_agent  # Agente do mundo
        self.event_count = 0  # Contador de eventos recebidos
        self.processed_count = 0  # Contador de eventos processados
        self.last_simulation_time = 0.0  # Tempo da última simulação
        self.time_simulated = 0.0  # Tempo total simulado
        
    async def setup(self):
        
        print(f"\n{'='*70}")
        print(f"[{self.name}] Event-Driven Agent iniciado")
        print(f"[{self.name}] Intervalo de simulação: {self.simulation_interval}s")
        print(f"{'='*70}\n")
        self.presence.approve_all = True
        
        # Subscribe a cada agente individualmente
        all_agents = self.registered_vehicles + self.registered_warehouses + self.registered_stores
        for agent_jid in all_agents:
            self.presence.subscribe(agent_jid)
        
        self.presence.set_presence(PresenceType.AVAILABLE, PresenceShow.CHAT)
    
        # Behaviour para enviar mensagem sinaleira inicial
        initial_signal = self.SendInitialSignalBehaviour()
        self.add_behaviour(initial_signal)
        
        # Behaviour para receber eventos continuamente
        receive_behaviour = self.ReceiveEventsBehaviour()
        self.add_behaviour(receive_behaviour)
        
        # Behaviour periódico para processar eventos (a cada 5 segundos)
        process_behaviour = self.ProcessEventsBehaviour(period=self.simulation_interval)
        self.add_behaviour(process_behaviour)
        
        # Behaviour para registrar veículos
    
    class SendInitialSignalBehaviour(OneShotBehaviour):
        """
        Behaviour que envia uma mensagem sinaleira inicial aos veículos.
        Executa apenas uma vez no início do agente.
        """
        
        async def run(self):
            # Aguardar um pouco para garantir que os veículos estejam registrados
            
            if not self.agent.registered_vehicles:
                print(f"[{self.agent.name}] ⚠️ Nenhum veículo registrado para enviar sinal inicial")
                return
            
            # Usar nome fictício que não corresponde a nenhum veículo real
            vehicle_name_ficticio = "vehicle_init_signal_999"
            
            # Enviar mensagem para TODOS os veículos registrados
            print(f"\n{'='*70}")
            print(f"[{self.agent.name}] 🚦 ENVIANDO SINAL INICIAL")
            print(f"  Destinatários: {len(self.agent.registered_vehicles)} veículos")
            print(f"  Veículo (fictício): {vehicle_name_ficticio}")
            print(f"  Tipo: arrival")
            print(f"  Tempo: 0.0")
            print(f"  Nota: Mensagem será ignorada pelos veículos (nome não corresponde e tempo zero mas vao notificar o agente)")
            print(f"{'='*70}")
            
            for vehicle_jid in self.agent.registered_vehicles:
                # Criar mensagem de arrival inicial com tempo zero
                msg = Message(to=vehicle_jid)
                msg.set_metadata("performative", "inform")
                
                data = {
                    "type": "arrival",
                    "vehicle": vehicle_name_ficticio,  # Nome fictício
                    "time": 0.0
                }
                msg.body = json.dumps(data)
                
                await self.send(msg)
                
                vehicle_name = str(vehicle_jid).split("@")[0]
                print(f"  → Enviado para: {vehicle_name}")
            
            print(f"{'='*70}\n")
    
    class ReceiveEventsBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico que recebe eventos continuamente e adiciona à heap.
        """
        
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    event_type = data.get("type")
                    time = data.get("time", 0.0)
                    event_data = data.get("data", {})
                    
                    # Criar evento
                    event = Event(
                        event_type=event_type,
                        time=time,
                        data=event_data,
                        sender=str(msg.sender),
                        timestamp=data.get("timestamp")
                    )
                    
                    # Verificar se é evento de trânsito
                    if event_type == "transit" or event_type == "Transit":
                        # Adicionar à lista de trânsito
                        self.agent.transit_events.append(event)
                        print(f"[{self.agent.name}] 📩 Evento de trânsito recebido: {event}")
                        print(f"   Eventos de trânsito: {len(self.agent.transit_events)}")
                    else:
                        # Adicionar à heap
                        heapq.heappush(self.agent.event_heap, event)
                        print(f"[{self.agent.name}] 📩 Evento recebido: {event}")
                        print(f"   Eventos na heap: {len(self.agent.event_heap)}")
                    
                    self.agent.event_count += 1
                
                except Exception as e:
                    print(f"[{self.agent.name}] ❌ Erro ao processar mensagem: {e}")
    
    class ProcessEventsBehaviour(PeriodicBehaviour):
        """
        Behaviour periódico que processa eventos da heap a cada 5 segundos.
        """
        
        async def run(self):
            # Recolocar eventos de trânsito na heap no início
            for transit_event in self.agent.transit_events:
                heapq.heappush(self.agent.event_heap, transit_event)
            
            print(f"\n{'='*70}")
            print(f"[{self.agent.name}] 🔄 PROCESSANDO EVENTOS")
            print(f"[{self.agent.name}] Tempo de simulação: {self.agent.simulation_interval}s")
            print(f"[{self.agent.name}] Eventos na heap: {len(self.agent.event_heap)}")
            print(f"[{self.agent.name}] Eventos de trânsito: {len(self.agent.transit_events)}")
            print(f"{'='*70}\n")
            
            if not self.agent.event_heap:
                print(f"[{self.agent.name}] ℹ️  Nenhum evento para processar\n")
                return
            
            # Tirar apenas o primeiro evento da heap (menor tempo)
            first_event = heapq.heappop(self.agent.event_heap)
            event_time = first_event.time
            
            print(f"[{self.agent.name}] 📤 Processando evento: {first_event}")
            
            # Se o primeiro evento for de trânsito, remover da lista de trânsito
            if first_event.event_type == "transit" or first_event.event_type == "Transit":
                if first_event in self.agent.transit_events:
                    self.agent.transit_events.remove(first_event)
                    print(f"[{self.agent.name}] 🗑️  Evento de trânsito removido da lista")
            
            # Atualizar tempo de todos os eventos de trânsito
            updated_transit_events = []
            for transit_event in self.agent.transit_events:
                transit_event.time -= event_time
            
                # Ainda tem tempo restante - manter na lista
                updated_transit_events.append(transit_event)
                print(f"[{self.agent.name}] 🔄 Trânsito atualizado: {transit_event} (tempo restante: {transit_event.time:.2f}s)")
            
            # Atualizar lista de eventos de trânsito
            self.agent.transit_events = updated_transit_events
            
            # Esvaziar a heap (descartar outros eventos)
            discarded_count = len(self.agent.event_heap)
            self.agent.event_heap = []
            
            if discarded_count > 0:
                print(f"[{self.agent.name}] 🗑️  Heap esvaziada: {discarded_count} eventos descartados")
            
            # Notificar todos os veículos sobre o primeiro evento
            await self.notify_events([first_event])
            
            self.agent.processed_count += 1
            
            print(f"\n[{self.agent.name}] 📊 Estatísticas:")
            print(f"   Evento notificado: {first_event.event_type}")
            print(f"   Tempo do evento: {event_time:.2f}s")
            print(f"   Eventos descartados: {discarded_count}")
            print(f"   Trânsitos ativos: {len(self.agent.transit_events)}")
            print(f"   Total recebido: {self.agent.event_count}")
            print(f"   Total processado: {self.agent.processed_count}")
            print(f"{'='*70}\n")
        
        async def notify_events(self, events: List[Event]):
            """
            Notifica os agentes apropriados sobre os eventos.
            - Transit: notifica veículos, warehouses e stores
            - arrival: notifica apenas veículos
            - updatesimulation: notifica apenas agente do mundo
            """
            for event in events:
                recipients = []
                
                # Determinar destinatários baseado no tipo de evento
                if event.event_type == "transit" or event.event_type == "Transit":
                    # Trânsito: veículos + warehouses + stores
                    recipients = (self.agent.registered_vehicles + 
                                self.agent.registered_warehouses + 
                                self.agent.registered_stores)
                    print(f"\n[{self.agent.name}] 📢 Notificando evento TRANSIT para {len(recipients)} agentes")
                
                elif event.event_type == "arrival":
                    # Chegada: apenas veículos
                    recipients = self.agent.registered_vehicles
                    print(f"\n[{self.agent.name}] 📢 Notificando evento ARRIVAL para {len(recipients)} veículos")
                
                elif event.event_type == "updatesimulation":
                    # Update: apenas agente do mundo
                    if self.agent.world_agent:
                        recipients = [self.agent.world_agent]
                        print(f"\n[{self.agent.name}] 📢 Notificando evento UPDATESIMULATION para agente do mundo")
                    else:
                        print(f"\n[{self.agent.name}] ⚠️  Agente do mundo não registrado, evento ignorado")
                        continue
                
                # Enviar mensagem para todos os destinatários
                for recipient_jid in recipients:
                    msg = Message(to=recipient_jid)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("event_type", event.event_type)
                    msg.body = json.dumps(event.to_dict())
                    
                    await self.send(msg)
                    recipient_name = recipient_jid.split('@')[0]
                    print(f"[{self.agent.name}]   → {recipient_name}: {event.event_type}")
    


async def main():
    """
    Função principal para executar o teste do Event Agent.
    Cria um mundo, veículos, warehouse de teste e o event agent.
    """
    import sys
    import os
    
    # Adicionar diretório pai ao path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    from veiculos.veiculos import Veiculo
    from veiculos.test_vehicle_agent import TestWarehouseAgent
    from world.world import World
    
    # Configurações dos agentes
    EVENT_AGENT_JID = "event_agent@localhost"
    EVENT_AGENT_PASSWORD = "event123"
    WAREHOUSE_JID = "warehouse_test@localhost"
    WAREHOUSE_PASSWORD = "warehouse123"
    VEHICLE_JID = "vehicle1@localhost"
    VEHICLE_PASSWORD = "vehicle123"
    VEHICLE_JID_2 = "vehicle2@localhost"
    VEHICLE_PASSWORD_2 = "vehicle234"
    
    print("="*70)
    print("TESTE DO EVENT-DRIVEN AGENT")
    print("="*70)
    
    # Criar o mundo
    print("\n🌍 Criando o mundo...")
    world = World(
        width=8,
        height=4,
        mode="different", 
        max_cost=4, 
        gas_stations=2, 
        warehouses=5,
        suppliers=2, 
        stores=6, 
        highway=True,
        traffic_probability=0.3,
        traffic_spread_probability=0.7,
        traffic_interval=3,
        untraffic_probability=0.4
    )
    
    import matplotlib.pyplot as plt
    #world.plot_graph()
    
    print(f"✓ Mundo criado: {world.width}x{world.height}")
    print(f"✓ Nós no grafo: {len(world.graph.nodes)}")
    print(f"✓ Arestas no grafo: {len(world.graph.edges)}")
    
    # Identificar uma localização inicial para o veículo (primeiro store)
    store_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'store') and node.store:
            store_locations.append(node_id)
    
    if not store_locations:
        print("❌ ERRO: Não foram encontrados stores para localização inicial do veículo!")
        return
    
    initial_location = store_locations[0]
    initial_location1 = store_locations[1]
    
    print(f"\n🚚 Criando veículo...")
    print(f"   Localização inicial: {initial_location}")
    print(f"   Capacidade: 1000 kg")
    print(f"   Combustível máximo: 100 L")
    
    # Criar o veículo
    vehicle = Veiculo(
        jid=VEHICLE_JID,
        password=VEHICLE_PASSWORD,
        max_fuel=100,
        capacity=1000,
        max_orders=10,
        map=world.graph,
        weight=1500,
        current_location=initial_location,
        event_agent_jid=EVENT_AGENT_JID
    )
    vehicle_2 = Veiculo(
        jid=VEHICLE_JID_2,
        password=VEHICLE_PASSWORD_2,
        max_fuel=100,
        capacity=1000,
        max_orders=10,
        map=world.graph,
        weight=1500,
        current_location=initial_location1,
        event_agent_jid=EVENT_AGENT_JID
    )
    
    # Criar event agent com lista de veículos registrados
    print(f"\n⚙️ Criando Event Agent...")
    event_agent = EventDrivenAgent(
        jid=EVENT_AGENT_JID,
        password=EVENT_AGENT_PASSWORD,
        simulation_interval=5.0,
        registered_vehicles=[VEHICLE_JID, VEHICLE_JID_2],
        registered_warehouses=[WAREHOUSE_JID],
        registered_stores=[]
    )
    
    # Criar warehouse de teste
    print(f"\n📦 Criando Warehouse de teste...")
    try:
        warehouse = TestWarehouseAgent(
            jid=WAREHOUSE_JID,
            password=WAREHOUSE_PASSWORD,
            vehicle_jids=[VEHICLE_JID, VEHICLE_JID_2],
            world=world
        )
    except ValueError as e:
        print(f"\n❌ ERRO: {e}")
        print("Certifique-se de que o mundo tem warehouses e stores suficientes!")
        return
    
    print("\n" + "="*70)
    print(f"Event Agent JID: {EVENT_AGENT_JID}")
    print(f"Warehouse JID: {WAREHOUSE_JID}")
    print(f"Vehicle JID: {VEHICLE_JID}")
    print("="*70)
    
    # Iniciar todos os agentes
    print("\n🚀 Iniciando agentes...")
    await vehicle.start()
    print(f"✓ Veículo iniciado: {VEHICLE_JID}")
    await vehicle_2.start()
    print(f"✓ Veículo iniciado: {VEHICLE_JID_2}")
    await warehouse.start()
    print(f"✓ Warehouse de teste iniciado: {WAREHOUSE_JID}")
    await event_agent.start()
    print(f"✓ Event Agent iniciado: {EVENT_AGENT_JID}")
    
    print(f"\n[SISTEMA] ✓ Sistema de teste iniciado!")
    print(f"[SISTEMA] 🎯 Event Agent processando a cada {event_agent.simulation_interval}s")
    print(f"[SISTEMA] 📦 Enviando ordens aleatórias a cada 5 segundos...")
    print(f"[SISTEMA] 🗺️  Usando {len(warehouse.warehouse_locations)} warehouses e {len(warehouse.store_locations)} stores")
    print(f"[SISTEMA] 🚚 Veículo em localização {initial_location}")
    print(f"[SISTEMA] ⌨️  Pressione Ctrl+C para parar\n")
    
    try:
        # Manter os agentes rodando
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[SISTEMA] Parando agentes...")
    finally:
        await event_agent.stop()
        await warehouse.stop()
        await vehicle.stop()
        print("[SISTEMA] ✓ Agentes parados!")



if __name__ == "__main__":
    """
    TESTE DO EVENT-DRIVEN AGENT
    ============================
    
    Este script testa o Event-Driven Agent integrado com veículos e warehouse.
    
    CARACTERÍSTICAS DO TESTE:
    -------------------------
    - Cria um mundo 8x4 com 5 warehouses, 6 stores, 2 gas stations
    - Inicia 1 veículo que se comunica com o event agent
    - Warehouse envia ordens aleatórias a cada 5 segundos
    - Event agent processa eventos a cada 5 segundos
    - Simula arrival e transit events para testar o sistema completo
    
    AGENTES CRIADOS:
    ----------------
    1. EventDrivenAgent: Gerencia heap de eventos e notifica veículos
    2. Veiculo: Recebe ordens, calcula rotas, envia eventos de arrival
    3. TestWarehouseAgent: Simula warehouse enviando ordens e arrival/transit
    
    FLUXO DE TESTE:
    ---------------
    1. Event agent envia sinal inicial (fictício) aos veículos
    2. Warehouse envia ordens ao veículo
    3. Veículo responde com propostas (can_fit + delivery_time)
    4. Warehouse confirma ordens (80% aceitas)
    5. Veículo envia eventos de arrival ao event agent
    6. Event agent processa eventos na heap e notifica veículos
    7. Warehouse simula arrival/transit a cada 10s para testar MovementBehaviour
    
    COMO EXECUTAR:
    --------------
    1. Certifique-se de que o servidor XMPP está rodando (Openfire/Prosody)
    2. Execute: python Eventos/event_agent.py
    3. Observe os logs dos 3 agentes interagindo
    4. Pressione Ctrl+C para parar
    
    REGISTRO DE VEÍCULOS:
    ---------------------
    Os veículos são registrados no event agent via lista registered_vehicles.
    Para adicionar mais veículos, inclua seus JIDs na lista ao criar o EventDrivenAgent.
    
    EVENTOS TESTADOS:
    -----------------
    - arrival: Veículo chega a um nó (pickup ou delivery)
    - Transit: Mudança de peso em arestas (trânsito)
    - Sinal inicial: Mensagem fictícia para testar broadcast
    
    OBSERVAÇÕES:
    ------------
    - Event agent usa min heap para ordenar eventos por tempo
    - Eventos de trânsito têm tempo decrementado a cada ciclo
    - Primeiro evento da heap é processado, restante descartado
    - Veículos filtram mensagens por nome (ignoram se não corresponde)
    """
    
    asyncio.run(main())
