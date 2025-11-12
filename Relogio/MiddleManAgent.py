from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from spade.template import Template
import asyncio
from datetime import datetime
from clock_utils import ClockSyncMixin
import random
import json


class ClockRegistrationBehaviour(OneShotBehaviour, ClockSyncMixin):
    """
    OneShotBehaviour que registra o agente no relógio.
    Este behaviour executa uma única vez e envia a mensagem de registro.
    """
    
    async def run(self):
        """
        Envia mensagem de registro ao ClockAgent.
        """
        self.setup_clock_sync(self.agent.clock_jid)
        await self.register_with_clock()
        print(f"[{self.agent.name}] Enviada solicitação de registro ao relógio")


class MiddleManAgent(Agent):
    """
    Agente de middle man para ser auxiliar de todos os agentes do universo.
    - Regista-se no relógio
    - Imprime quando recebe o tick (fase de comunicação)
    - Imprime quando recebe a fase de ação
    Ele deve receber a mensagem e deve comunicar com o relogio e o agente. 
    
    Usa ClockSyncMixin para facilitar a sincronização com o relógio.
    """

    def __init__(self, jid, password, clock_jid, agent_jid):
        super().__init__(jid, password)
        self.clock_jid = clock_jid
        self.agent_jid = agent_jid
        # Configurar sincronização com o relógio

    async def setup(self):
        
        # Template que aceita mensagens de ambas as fases (communication ou action)
        # e qualquer valor de tick
        template1 = Template()
        template1.sender = self.agent_jid
        self.add_behaviour(self.Communicate_with_clock_behaviour(), template1)

        # Adicionar behaviour de registro (OneShotBehaviour)
        self.add_behaviour(ClockRegistrationBehaviour())

        template2 = Template()
        template2.sender = self.clock_jid
        # Adicionar behaviour principal (CyclicBehaviour)
        self.add_behaviour(self.Communicate_with_agent_behaviour(), template2)

    class Communicate_with_clock_behaviour(CyclicBehaviour, ClockSyncMixin):
        async def run(self):
            msg = await self.receive(timeout=0.2)
            if msg:
                try:
                    phase = msg.metadata.get("phase")
                    tick = msg.metadata.get("tick")
                    tick_duration = msg.metadata.get("tick_duration")  
                    if phase == "communication":
                        print(f"[{self.agent.name}] Mensagem de comunicação recebida do agente (tick {tick})")
                        await self.confirm_communication_phase(tick, tick_duration)
                    elif phase == "action":
                        print(f"[{self.agent.name}] Mensagem de ação recebida do agente (tick {tick})")
                        await self.confirm_action_phase(tick, tick_duration)
                except json.JSONDecodeError:
                    print(f"[{self.agent.name}] Erro ao decodificar mensagem: {msg.body}")


                
    class Communicate_with_agent_behaviour(CyclicBehaviour, ClockSyncMixin):
        """
        Comportamento que responde às mensagens do relógio.
        Usa handle_clock_message() do ClockSyncMixin para processar mensagens.
        """

        async def run(self):
            msg = await self.receive(timeout=0.2)
            
            if msg:
                # Usar o método do mixin para processar mensagens do relógio
                msg_type, data = self.handle_clock_message(msg)
                
                # Confirmação de registro
                if msg_type == "register_confirm":
                    print(f"[{self.agent.name}] REGISTRADO NO RELÓGIO")
                    print(f"[{self.agent.name}] Tick atual: {data.get('current_tick')}")
                    print(f"[{self.agent.name}] Duração do tick: {data.get('tick_duration')}s\n")
                
                # Novo tick (FASE DE COMUNICAÇÃO)
                elif msg_type == "new_tick":
                    tick = data.get("tick")
                    phase = data.get("phase")
                    tick_duration = data.get("tick_duration")
                    print(f"\n{'─'*60}")
                    print(f"[{self.agent.name}]  NOVO TICK RECEBIDO: {tick}")
                    print(f"[{self.agent.name}]  FASE: {phase.upper()}")
                    
                    
                    # enviar a agente a mensagem de novo tick
                    await self.send_message_to_agent('communication', tick, tick_duration)
                    print(f"{'─'*60}\n")

                
                # Mudança de fase (FASE DE AÇÃO)
                elif msg_type == "phase_change":
                    tick = data.get("tick")
                    phase = data.get("phase")
                    tick_duration = data.get("tick_duration")

                    print(f"\n{'─'*60}")
                    print(f"[{self.agent.name}]  FASE DE AÇÃO RECEBIDA")
                    print(f"[{self.agent.name}]  Tick: {tick}")
                    print(f"[{self.agent.name}]  Fase: {phase.upper()}")

                    await self.send_message_to_agent('action', tick, tick_duration)
                    print(f"{'─'*60}\n")

                # Confirmação de desregistro
                elif msg_type == "unregister_confirm":
                    print(f"[{self.agent.name}] DESREGISTRADO DO RELÓGIO")

        async def send_message_to_agent(self, phase, tick, tick_duration):
            """
            Envia mensagem ao agente com a fase e o tick.
            """
            msg = Message(to=self.agent.agent_jid)
            msg.set_metadata("tick", str(tick))
            msg.set_metadata("phase", phase)
            msg.set_metadata("tick_duration", str(tick_duration))
            await self.send(msg)
            print(f"[{self.agent.name}] Mensagem enviada ao {self.agent.agent_jid} (fase: {phase}, tick: {tick}, tick_duration: {tick_duration})")

