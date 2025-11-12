from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import asyncio
import json
from datetime import datetime

class ClockAgent(Agent):
    """
    Agente relógio que coordena a simulação por ticks com 2 fases:
    FASE 1 - COMUNICAÇÃO: Agentes enviam e recebem mensagens entre si
    FASE 2 - AÇÃO: Agentes processam mensagens e executam ações
    
    Cada tick só avança quando todos os agentes confirmam ambas as fases.
    """

    def __init__(self, jid, password, tick_duration_seconds: float = 1.0):
        super().__init__(jid, password)
        self.tick_duration = tick_duration_seconds          # Duração total de cada tick
        self.current_tick = 0                               # Tick atual
        self.current_phase = None                           # 'communication' ou 'action'
        self.registered_agents = set()                      # JIDs dos agentes registrados
        self.agents_communication_ready = set()             # Agentes que confirmaram fase de comunicação
        self.agents_action_ready = set()                    # Agentes que confirmaram fase de ação
        self.is_running = False                             # Flag de simulação ativa
        self.start_time = None                              # Timestamp de início
        
    async def setup(self):
        print(f"[{self.name}] Relógio inicializado. Tick duration: {self.tick_duration}s")
        self.add_behaviour(self.ClockBehaviour())
        self.add_behaviour(self.RegistrationBehaviour())

    def register_agent(self, agent_jid: str):
        """
        Registra um agente para receber notificações de tick.
        """
        self.registered_agents.add(agent_jid)
        print(f"[{self.name}] Agente registrado: {agent_jid}. Total: {len(self.registered_agents)}")

    def unregister_agent(self, agent_jid: str):
        """
        Remove um agente da lista de notificações.
        """
        if agent_jid in self.registered_agents:
            self.registered_agents.remove(agent_jid)
            print(f"[{self.name}] Agente removido: {agent_jid}. Total: {len(self.registered_agents)}")

    def start_simulation(self):
        """
        Inicia a simulação do relógio.
        """
        self.is_running = True
        self.current_tick = 0
        self.start_time = datetime.now()
        print(f"[{self.name}] Simulação iniciada no tick {self.current_tick}")

    def stop_simulation(self):
        """
        Para a simulação do relógio.
        """
        self.is_running = False
        
        print(f"[{self.name}] Simulação parada no tick {self.current_tick}")
        

    class RegistrationBehaviour(CyclicBehaviour):
        """
        Comportamento que escuta pedidos de registro/desregistro de agentes.
        """

        async def run(self):
            msg = await self.receive(timeout=0.1)
            if msg:
                msg_type = msg.metadata.get("type") if msg.metadata else None
                
                if msg_type == "register":
                    self.agent.register_agent(str(msg.sender))
                    
                elif msg_type == "unregister":
                    self.agent.unregister_agent(str(msg.sender))

    class ClockBehaviour(CyclicBehaviour):
        """
        Comportamento principal do relógio com 2 FASES por tick:
        
        FASE 1 - COMUNICAÇÃO:
        1. Envia "new_tick" + "phase: communication" para todos
        2. Aguarda "communication_ready" de todos
        
        FASE 2 - AÇÃO:
        3. Envia "phase_change" + "phase: action" para todos
        4. Aguarda "action_ready" de todos
        5. Avança para próximo tick
        """

        async def run(self):
            # Só executa se a simulação estiver ativa
            if not self.agent.is_running:
                await asyncio.sleep(0.5)
                return

            # Se não há agentes registrados, aguarda
            if not self.agent.registered_agents:
                print(f"[{self.agent.name}] Aguardando agentes se registrarem...")
                await asyncio.sleep(2)
                return

            print(f"\n{'='*70}")
            print(f"[{self.agent.name}] TICK {self.agent.current_tick}")
            print(f"{'='*70}\n")

            # ========================================
            # FASE 1: COMUNICAÇÃO
            # ========================================
            self.agent.current_phase = 'communication'
            await self.broadcast_phase_start('communication')
            await self.wait_for_communication_confirmations()

            # ========================================
            # FASE 2: AÇÃO
            # ========================================
            self.agent.current_phase = 'action'
            await self.broadcast_phase_start('action')
            await self.wait_for_action_confirmations()

            # ========================================
            # Avançar para o próximo tick
            # ========================================
            self.agent.current_tick += 1

        async def broadcast_phase_start(self, phase: str):
            """
            Envia mensagem de início de fase para todos os agentes.
            
            Args:
                phase: 'communication' ou 'action'
            """
            print(f"\n{'='*60}")
            print(f"[{self.agent.name}] FASE: {phase.upper()}")
            print(f"[{self.agent.name}] Notificando {len(self.agent.registered_agents)} agentes...")
            print(f"{'='*60}\n")

            # Limpar confirmações da fase anterior
            if phase == 'communication':
                self.agent.agents_communication_ready.clear()
            else:
                self.agent.agents_action_ready.clear()
            
            # Enviar mensagem para cada agente
            for agent_jid in self.agent.registered_agents:
                msg = Message(to=agent_jid)
                
                if phase == 'communication':
                    msg.metadata = {"type": "new_tick"}
                else:  # action
                    msg.metadata = {"type": "phase_change"}

                msg.body = json.dumps({
                        "tick": self.agent.current_tick,
                        "phase": phase,
                        "tick_duration": self.agent.tick_duration,
                    })
                
                await self.send(msg)

        async def wait_for_communication_confirmations(self):
            """
            Aguarda confirmação da FASE DE COMUNICAÇÃO de todos os agentes.
            Se demorar mais de 1 minuto, para o sistema com erro.
            """
            timeout = 60  # Timeout de 1 minuto (60 segundos)
            start_wait = asyncio.get_event_loop().time()
            
            while len(self.agent.agents_communication_ready) < len(self.agent.registered_agents):
                # Verificar timeout
                elapsed = asyncio.get_event_loop().time() - start_wait
                if elapsed > timeout:
                    await self.print_error_confirmation_timeout('communication', elapsed, timeout, self.agent.registered_agents - self.agent.agents_communication_ready)
                    
                    # PARAR A SIMULAÇÃO
                    self.agent.stop_simulation()
                    print(f"[{self.agent.name}] Simulação PARADA devido a timeout!")
                    return
                
                # Receber mensagens de confirmação
                msg = await self.receive(timeout=0.1)
                if msg and msg.metadata and msg.metadata.get("type") == "communication_ready":
                    sender = str(msg.sender)
                    if sender in self.agent.registered_agents:
                        self.agent.agents_communication_ready.add(sender)
                        
                        try:
                            body = json.loads(msg.body)
                            confirmed_tick = body.get("tick", "?")
                            print(f"[{self.agent.name}] Comunicação confirmada: {sender.split('@')[0]} (tick {confirmed_tick})")
                        except:
                            print(f"[{self.agent.name}] Comunicação confirmada: {sender.split('@')[0]}")
                
                await asyncio.sleep(0.1)
            
            ready_count = len(self.agent.agents_communication_ready)
            total_count = len(self.agent.registered_agents)
            print(f"[{self.agent.name}] Fase de comunicação: {ready_count}/{total_count} agentes prontos\n")

        async def wait_for_action_confirmations(self):
            """
            Aguarda confirmação da FASE DE AÇÃO de todos os agentes.
            Se demorar mais de 1 minuto, para o sistema com erro.
            """
            timeout = 60  # Timeout de 1 minuto (60 segundos)
            start_wait = asyncio.get_event_loop().time()
            
            while len(self.agent.agents_action_ready) < len(self.agent.registered_agents):
                # Verificar timeout
                elapsed = asyncio.get_event_loop().time() - start_wait
                if elapsed > timeout:
                    await self.print_error_confirmation_timeout('action', elapsed, timeout, self.agent.registered_agents - self.agent.agents_action_ready)
                    
                    # PARAR A SIMULAÇÃO
                    self.agent.stop_simulation()
                    print(f"[{self.agent.name}] Simulação PARADA devido a timeout!")
                    return
                
                # Receber mensagens de confirmação
                msg = await self.receive(timeout=0.1)
                if msg and msg.metadata and msg.metadata.get("type") == "action_ready":
                    sender = str(msg.sender)
                    if sender in self.agent.registered_agents:
                        self.agent.agents_action_ready.add(sender)
                        
                        try:
                            body = json.loads(msg.body)
                            confirmed_tick = body.get("tick", "?")
                            action_taken = body.get("action_taken", False)
                            print(f"[{self.agent.name}] Ação confirmada: {sender.split('@')[0]} (tick {confirmed_tick}, ação: {action_taken})")
                        except:
                            print(f"[{self.agent.name}] Ação confirmada: {sender.split('@')[0]}")
                
                await asyncio.sleep(0.1)
            
            ready_count = len(self.agent.agents_action_ready)
            total_count = len(self.agent.registered_agents)
            print(f"[{self.agent.name}] Fase de ação: {ready_count}/{total_count} agentes prontos")
            print(f"[{self.agent.name}] TICK {self.agent.current_tick} COMPLETO\n")


        async def print_error_confirmation_timeout(self, phase: str, elapsed: float, timeout: float, missing: set):
            print(f"\n{'='*70}")
            print(f"[{self.agent.name}] ERRO DE SISTEMA - TIMEOUT NA FASE DE {phase.upper()}")
            print(f"{'='*70}")
            print(f"[{self.agent.name}] Tempo decorrido: {elapsed:.2f}s (limite: {timeout}s)")
            print(f"[{self.agent.name}] Agentes que NÃO confirmaram:")
            for agent_jid in missing:
                print(f"   - {agent_jid}")
            print(f"{'='*70}\n")