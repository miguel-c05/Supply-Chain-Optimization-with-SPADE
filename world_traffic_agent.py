"""
World Traffic Agent - Agente para simular eventos de trânsito no mundo.
Recebe mensagens do Event Agent e simula atualizações de trânsito ao longo do tempo.
"""

import asyncio
import json
from datetime import datetime
from typing import List, Dict, Any
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
from world.world import World


class WorldTrafficAgent(Agent):
    """
    Agente que simula eventos de trânsito no mundo.
    Recebe comandos do Event Agent para simular períodos de tempo.
    """
    
    def __init__(self, jid: str, password: str, world: World, event_agent_jid: str):
        """
        Inicializa o agente de trânsito.
        
        Args:
            jid: Jabber ID do agente
            password: Senha do agente
            world: Instância do mundo a ser simulado
            event_agent_jid: JID do Event Agent para comunicação
        """
        super().__init__(jid, password)
        self.world = world
        self.event_agent_jid = event_agent_jid
        self.simulation_count = 0
    
    async def setup(self):
        """Configura os behaviours do agente"""
        print(f"\n{'='*70}")
        print(f"[{self.name}] World Traffic Agent iniciado")
        print(f"[{self.name}] Event Agent: {self.event_agent_jid}")
        print(f"[{self.name}] Mundo: {self.world.width}x{self.world.height}")
        print(f"{'='*70}\n")
        
        # Template para receber mensagens do event agent
        event_template = Template()
        event_template.set_metadata("performative", "request")
        event_template.set_metadata("type", "simulate")
        
        # Behaviour para receber comandos de simulação
        receive_behaviour = self.ReceiveSimulationRequestBehaviour()
        self.add_behaviour(receive_behaviour, template=event_template)
    
    class ReceiveSimulationRequestBehaviour(CyclicBehaviour):
        """
        Behaviour cíclico que aguarda comandos do Event Agent.
        """
        
        async def run(self):
            msg = await self.receive(timeout=10)
            
            if msg:
                try:
                    data = json.loads(msg.body)
                    simulation_time = data.get("simulation_time", 50)  # Tempo em segundos a simular
                    
                    print(f"\n[{self.agent.name}] 📨 Comando de simulação recebido")
                    print(f"   Tempo a simular: {simulation_time}s")
                    print(f"   De: {msg.sender}")
                    
                    # Criar e iniciar o OneShot behaviour para simular
                    simulate_behaviour = self.agent.SimulateTrafficBehaviour(
                        simulation_time=simulation_time,
                        sender_jid=str(msg.sender)
                    )
                    self.agent.add_behaviour(simulate_behaviour)
                    
                except json.JSONDecodeError as e:
                    print(f"[{self.agent.name}] Erro ao decodificar JSON: {e}")
                except Exception as e:
                    print(f"[{self.agent.name}] Erro ao processar mensagem: {e}")
    
    class SimulateTrafficBehaviour(OneShotBehaviour):
        """
        Behaviour OneShot que simula eventos de trânsito ao longo do tempo.
        """
        
        def __init__(self, simulation_time: int, sender_jid: str):
            """
            Args:
                simulation_time: Número de segundos a simular
                sender_jid: JID de quem enviou o comando (Event Agent)
            """
            super().__init__()
            self.simulation_time = simulation_time
            self.sender_jid = sender_jid
        
        async def run(self):
            """
            Simula X segundos do mundo, coletando todas as mudanças de trânsito.
            """
            self.agent.simulation_count += 1
            sim_id = self.agent.simulation_count
            
            print(f"\n{'='*70}")
            print(f"[{self.agent.name}] 🎲 SIMULAÇÃO #{sim_id} INICIADA")
            print(f"   Tempo total: {self.simulation_time}s")
            print(f"{'='*70}\n")
            
            # Lista para armazenar todas as atualizações
            all_updates = []
            
            # Simular segundo a segundo
            remaining_time = self.simulation_time
            
            all_updates = self.collect_traffic_updates(remaining_time)
            '''#podes implementar como quiseres mas assim é assim que sugiro
            while remaining_time > 0:
                print(f"[{self.agent.name}] ⏱️  Simulando segundo {self.simulation_time - remaining_time + 1}/{self.simulation_time}")
                
                # Simular 1 segundo do mundo
                self.agent.world.simulate_step()
                
                # Coletar mudanças de trânsito neste segundo
                updates = self.collect_traffic_updates(remaining_time)
                
                if updates:
                    all_updates.extend(updates)
                
                remaining_time -= 1
                
                # Pequena pausa para não sobrecarregar (opcional)
                await asyncio.sleep(0.01)'''
            
            print(f"\n[{self.agent.name}] ✓ Simulação #{sim_id} concluída")
            print(f"   Total de atualizações: {len(all_updates)}")
            
            # Enviar todas as atualizações ao Event Agent
            if all_updates:
                await self.send_updates_to_event_agent(all_updates, sim_id)
            else:
                print(f"[{self.agent.name}] ℹ️  Nenhuma atualização de trânsito para enviar")
            
            print(f"{'='*70}\n")
        
        def collect_traffic_updates(self, time_remaining: int) -> List[Dict[str, Any]]:
            """
            Coleta as mudanças de trânsito (peso das arestas) no grafo.
            
            Args:
                time_remaining: Tempo restante na simulação (para timestamp)
            
            Returns:
                Lista de dicionários com as atualizações
            """
            updates = []
            updates = self.world.get_events(time_remaining)
            # updates = 
            # [
            #   {"node1_id": 27, "node2_id": 20, "new_time": 3.82, "new_fuel_consumption": 0.155, "instant": 0},
            #   {"node1_id": 14, "node2_id": 13, "new_time": 4.0, "new_fuel_consumption": 0.144, "instant": 3},
            #   ...
            # ]
            
            return updates
        
        async def send_updates_to_event_agent(self, updates: List[Dict[str, Any]], sim_id: int):
            """
            Envia todas as atualizações ao Event Agent.
            
            Args:
                updates: Lista de atualizações coletadas
                sim_id: ID da simulação
            """
            # Agrupar atualizações por tempo
            updates_by_time = {}
            for update in updates:
                time = update["time"]
                if time not in updates_by_time:
                    updates_by_time[time] = []
                updates_by_time[time].append({
                    "node1": update["node1"],
                    "node2": update["node2"],
                    "weight": update["weight"]
                })
            
            print(f"\n[{self.agent.name}] 📤 Enviando atualizações ao Event Agent")
            print(f"   Períodos com mudanças: {len(updates_by_time)}")
            
            # Enviar uma mensagem para cada período de tempo
            for time, edges in updates_by_time.items():
                msg = Message(to=self.agent.event_agent_jid)
                msg.set_metadata("performative", "inform")
                msg.set_metadata("type", "Transit")
                
                data = {
                    "type": "Transit",
                    "time": float(time),
                    "data": {
                        "edges": edges,
                        "simulation_id": sim_id
                    }
                }
                
                msg.body = json.dumps(data)
                await self.send(msg)
                
                print(f"[{self.agent.name}]   → Tempo {time}s: {len(edges)} arestas atualizadas")
            
            print(f"[{self.agent.name}] ✓ Todas as atualizações enviadas\n")


