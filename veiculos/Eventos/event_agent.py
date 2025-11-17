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
        self.event_heap = []  # Min heap de eventos
        self.simulation_interval = simulation_interval  # Intervalo de simulação (5s)
        self.registered_vehicles = set()  # Veículos registrados
        self.event_count = 0  # Contador de eventos recebidos
        self.processed_count = 0  # Contador de eventos processados
        self.last_simulation_time = 0.0  # Tempo da última simulação
    
    async def setup(self):
        print(f"\n{'='*70}")
        print(f"[{self.name}] Event-Driven Agent iniciado")
        print(f"[{self.name}] Intervalo de simulação: {self.simulation_interval}s")
        print(f"{'='*70}\n")
        
        # Behaviour para receber eventos continuamente
        receive_behaviour = self.ReceiveEventsBehaviour()
        self.add_behaviour(receive_behaviour)
        
        # Behaviour periódico para processar eventos (a cada 5 segundos)
        process_behaviour = self.ProcessEventsBehaviour(period=self.simulation_interval)
        self.add_behaviour(process_behaviour)
        
        # Behaviour para registrar veículos
        register_behaviour = self.RegisterVehiclesBehaviour()
        self.add_behaviour(register_behaviour)
    
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
                    
                    # Adicionar à heap
                    heapq.heappush(self.agent.event_heap, event)
                    self.agent.event_count += 1
                    
                    print(f"[{self.agent.name}] 📩 Evento recebido: {event}")
                    print(f"   Eventos na heap: {len(self.agent.event_heap)}")
                
                except Exception as e:
                    print(f"[{self.agent.name}] ❌ Erro ao processar mensagem: {e}")
    
    class ProcessEventsBehaviour(PeriodicBehaviour):
        """
        Behaviour periódico que processa eventos da heap a cada 5 segundos.
        """
        
        async def run(self):
            print(f"\n{'='*70}")
            print(f"[{self.agent.name}] 🔄 PROCESSANDO EVENTOS")
            print(f"[{self.agent.name}] Tempo de simulação: {self.agent.simulation_interval}s")
            print(f"[{self.agent.name}] Eventos na heap: {len(self.agent.event_heap)}")
            print(f"{'='*70}\n")
            
            if not self.agent.event_heap:
                print(f"[{self.agent.name}] ℹ️  Nenhum evento para processar\n")
                return
            
            # Processar todos os eventos da heap
            transit_events = []  # Eventos de trânsito para reprocessar
            events_to_notify = []  # Eventos a notificar
            
            while self.agent.event_heap:
                event = heapq.heappop(self.agent.event_heap)
                
                if event.event_type == "transit" or event.event_type == "Transit":
                    # Eventos de trânsito: reduzir tempo e recolocar na heap
                    event.time -= self.agent.simulation_interval
                    
                    if event.time > 0:
                        # Ainda tem tempo restante - recolocar na heap
                        transit_events.append(event)
                        print(f"[{self.agent.name}] 🔄 Trânsito mantido: {event} (tempo restante: {event.time:.2f}s)")
                    else:
                        # Tempo esgotado - notificar
                        events_to_notify.append(event)
                        print(f"[{self.agent.name}] ✅ Trânsito finalizado: {event}")
                else:
                    # Outros eventos: notificar imediatamente
                    events_to_notify.append(event)
                    print(f"[{self.agent.name}] 📤 Evento para notificar: {event}")
            
            # Recolocar eventos de trânsito com tempo restante na heap
            for event in transit_events:
                heapq.heappush(self.agent.event_heap, event)
            
            # Notificar todos os veículos sobre os eventos
            if events_to_notify:
                await self.notify_events(events_to_notify)
            
            self.agent.processed_count += len(events_to_notify)
            
            print(f"\n[{self.agent.name}] 📊 Estatísticas:")
            print(f"   Eventos notificados: {len(events_to_notify)}")
            print(f"   Trânsitos mantidos: {len(transit_events)}")
            print(f"   Eventos restantes na heap: {len(self.agent.event_heap)}")
            print(f"   Total recebido: {self.agent.event_count}")
            print(f"   Total processado: {self.agent.processed_count}")
            print(f"{'='*70}\n")
        
        async def notify_events(self, events: List[Event]):
            """
            Notifica todos os veículos registrados sobre os eventos.
            """
            print(f"\n[{self.agent.name}] 📢 Notificando {len(self.agent.registered_vehicles)} veículos sobre {len(events)} eventos")
            
            for vehicle_jid in self.agent.registered_vehicles:
                for event in events:
                    msg = Message(to=vehicle_jid)
                    msg.set_metadata("performative", "inform")
                    msg.set_metadata("event_type", event.event_type)
                    msg.body = json.dumps(event.to_dict())
                    
                    await self.send(msg)
                    print(f"[{self.agent.name}]   → {vehicle_jid.split('@')[0]}: {event.event_type}")
    
    class RegisterVehiclesBehaviour(CyclicBehaviour):
        """
        Behaviour para registrar veículos que querem receber notificações de eventos.
        """
        
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg and msg.get_metadata("performative") == "subscribe":
                vehicle_jid = str(msg.sender)
                
                if vehicle_jid not in self.agent.registered_vehicles:
                    self.agent.registered_vehicles.add(vehicle_jid)
                    print(f"\n[{self.agent.name}] ✅ Veículo registrado: {vehicle_jid}")
                    print(f"[{self.agent.name}] Total de veículos: {len(self.agent.registered_vehicles)}\n")
                    
                    # Enviar confirmação
                    reply = msg.make_reply()
                    reply.set_metadata("performative", "inform")
                    reply.body = json.dumps({
                        "status": "registered",
                        "simulation_interval": self.agent.simulation_interval
                    })
                    await self.send(reply)
                
            elif msg and msg.get_metadata("performative") == "unsubscribe":
                vehicle_jid = str(msg.sender)
                
                if vehicle_jid in self.agent.registered_vehicles:
                    self.agent.registered_vehicles.remove(vehicle_jid)
                    print(f"\n[{self.agent.name}] ❌ Veículo removido: {vehicle_jid}")
                    print(f"[{self.agent.name}] Total de veículos: {len(self.agent.registered_vehicles)}\n")


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
