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
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
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
        return {
            "type": self.event_type,
            "time": self.time,
            "data": self.data,
            "timestamp": self.timestamp
        }


class EventDrivenAgent(Agent):
    """
    Agente que gerencia eventos usando min heap.
    Recebe eventos continuamente e processa a cada 5 segundos.
    """
    
    def __init__(self, jid: str, password: str, simulation_interval: float = 5.0):
        super().__init__(jid, password)
        self.event_heap = []  # Min heap de eventos (não-trânsito)
        self.transit_events = []  # Lista separada para eventos de trânsito
        self.simulation_interval = simulation_interval  # Intervalo de simulação (5s)
        self.registered_vehicles = []  # Veículos registrados
        self.registered_warehouses = []  # Warehouses registrados
        self.registered_stores = []  # Stores registrados
        self.world_agent = None  # Agente do mundo
        self.event_count = 0  # Contador de eventos recebidos
        self.processed_count = 0  # Contador de eventos processados
        self.last_simulation_time = 0.0  # Tempo da última simulação
        self.time_simulated = 0.0  # Tempo total simulado
        
    async def setup(self):
        print(f"\n{'='*70}")
        print(f"[{self.name}] Event-Driven Agent iniciado")
        print(f"[{self.name}] Intervalo de simulação: {self.simulation_interval}s")
        print(f"{'='*70}\n")
        self.presence.approve_all=True
        all_agents = [self.registered_vehicles, self.registered_warehouses, self.registered_stores] 
        for agent_list in all_agents:
            self.presence.subscribe(self.clock_jid)
        self.presence.set_presence(PresenceType.AVAILABLE, PresenceShow.CHAT)
    
        
        # Behaviour para receber eventos continuamente
        receive_behaviour = self.ReceiveEventsBehaviour()
        self.add_behaviour(receive_behaviour)
        
        # Behaviour periódico para processar eventos (a cada 5 segundos)
        process_behaviour = self.ProcessEventsBehaviour(period=self.simulation_interval)
        self.add_behaviour(process_behaviour)
        
        # Behaviour para registrar veículos
    
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
    Função principal para testar o Event-Driven Agent.
    """
    EVENT_AGENT_JID = "event_agent@localhost"
    EVENT_AGENT_PASSWORD = "event123"
    
    print("="*70)
    print("EVENT-DRIVEN AGENT - TESTE")
    print("="*70)
    
    # Criar e iniciar o agente de eventos
    event_agent = EventDrivenAgent(
        jid=EVENT_AGENT_JID,
        password=EVENT_AGENT_PASSWORD,
        simulation_interval=5.0  # Processar a cada 5 segundos
    )
    
    await event_agent.start()
    print(f"✓ Event Agent iniciado: {EVENT_AGENT_JID}\n")
    
    # Simular envio de alguns eventos para teste
    print("📤 Enviando eventos de teste...\n")
    
    # Evento de arrival
    arrival_msg = Message(to=EVENT_AGENT_JID)
    arrival_msg.body = json.dumps({
        "type": "arrival",
        "time": 3.5,
        "data": {"vehicle": "vehicle1", "location": 5}
    })
    await event_agent.send(arrival_msg)
    
    # Evento de trânsito
    transit_msg = Message(to=EVENT_AGENT_JID)
    transit_msg.body = json.dumps({
        "type": "Transit",
        "time": 8.0,
        "data": {
            "edges": [
                {"node1": 3, "node2": 7, "weight": 12.5}
            ]
        }
    })
    await event_agent.send(transit_msg)
    
    print(f"[SISTEMA] ⌨️  Pressione Ctrl+C para parar\n")
    
    try:
        # Manter o agente rodando
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[SISTEMA] Parando agente...")
    finally:
        await event_agent.stop()
        print("[SISTEMA] ✓ Agente parado!")


if __name__ == "__main__":
    """
    EVENT-DRIVEN AGENT
    ==================
    
    Este agente gerencia eventos usando uma min heap e processa periodicamente.
    
    CARACTERÍSTICAS:
    ----------------
    - Recebe eventos continuamente (CyclicBehaviour)
    - Processa eventos a cada 5 segundos (PeriodicBehaviour)
    - Usa min heap para ordenar eventos por tempo
    - Eventos de trânsito têm tempo decrementado e são recolocados na heap
    - Outros eventos são notificados imediatamente
    - Suporta registro de veículos para notificações
    
    TIPOS DE EVENTOS:
    -----------------
    - "arrival": Chegada de veículo a um destino
    - "Transit"/"transit": Mudança de trânsito em arestas
    - Outros eventos personalizados
    
    FORMATO DE MENSAGEM:
    --------------------
    {
        "type": "arrival" ou "Transit",
        "time": 5.0,
        "data": {...},
        "timestamp": "2025-11-17T14:30:00"
    }
    
    REGISTRO DE VEÍCULOS:
    ---------------------
    Enviar mensagem com metadata "performative": "subscribe"
    """
    
    asyncio.run(main())
