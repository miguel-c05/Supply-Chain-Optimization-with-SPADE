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
        print(f"[{self.name}] Agente de teste inicializado")
        
        # Template que aceita mensagens de ambas as fases (communication ou action)
        # e qualquer valor de tick
        template1 = Template()
        template1.to = self.clock_jid
        template1.sender = self.agent_jid
        template1.metadata = {"phase": "communication"}
        template1.metadata = {"phase": "action"}
        template1.metadata = {"tick": "*"}
        self.add_behaviour(self.Communicate_with_agent_behaviour(), template1)

        # Adicionar behaviour de registro (OneShotBehaviour)
        self.add_behaviour(ClockRegistrationBehaviour())

        template2 = Template()
        template2.to = self.agent_jid
        template2.sender = self.jid
        # Adicionar behaviour principal (CyclicBehaviour)
        self.add_behaviour(self.TestBehaviour())

    class Communicate_with_agent_behaviour(CyclicBehaviour, ClockSyncMixin):
        async def run(self):
            msg = await self.receive(timeout=1)
            if msg:
                try:
                    msg_body = json.loads(msg.body)
                    phase = msg_body.get("phase")
                    tick = msg_body.get("tick")  # Obter tick da mensagem, default 0
                    
                    if phase == "communication":
                        print(f"[{self.agent.name}] Mensagem de comunicação recebida do agente (tick {tick}): {msg.body}")
                        await self.confirm_communication_phase(tick)
                    elif phase == "action":
                        print(f"[{self.agent.name}] Mensagem de ação recebida do agente (tick {tick}): {msg.body}")
                        await self.confirm_action_phase(tick)
                except json.JSONDecodeError:
                    print(f"[{self.agent.name}] Erro ao decodificar mensagem: {msg.body}")


                
    class TestBehaviour(CyclicBehaviour, ClockSyncMixin):
        """
        Comportamento que responde às mensagens do relógio.
        Usa handle_clock_message() do ClockSyncMixin para processar mensagens.
        """

        async def run(self):
            msg = await self.receive(timeout=1)
            
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
                    
                    print(f"\n{'─'*60}")
                    print(f"[{self.agent.name}]  NOVO TICK RECEBIDO: {tick}")
                    print(f"[{self.agent.name}]  FASE: {phase.upper()}")
                    print(f"{'─'*60}")
                    
                    # enviar a agente a mensagem de novo tick
                    await self.send_message_to_agent(phase, tick)

                
                # Mudança de fase (FASE DE AÇÃO)
                elif msg_type == "phase_change":
                    tick = data.get("tick")
                    phase = data.get("phase")
                    
                    print(f"\n{'─'*60}")
                    print(f"[{self.agent.name}]  FASE DE AÇÃO RECEBIDA")
                    print(f"[{self.agent.name}]  Tick: {tick}")
                    print(f"[{self.agent.name}]  Fase: {phase.upper()}")
                    print(f"[{self.agent.name}]  Executando ação... (aguardando 1 segundo)")
                    print(f"{'─'*60}")

                    await self.send_message_to_agent(phase, tick)
                
                # Confirmação de desregistro
                elif msg_type == "unregister_confirm":
                    print(f"[{self.agent.name}] DESREGISTRADO DO RELÓGIO")

        async def send_message_to_agent(self, phase, tick):
            """
            Envia mensagem ao agente com a fase e o tick.
            """
            msg = Message(to=self.agent.agent_jid)
            msg.set_metadata("tick", str(tick))
            msg.set_metadata("phase", phase)
            await self.send(msg)
            print(f"[{self.agent.name}] Mensagem enviada ao agente (fase: {phase}, tick: {tick})")
            


async def main():
    """
    Exemplo de execução do agente de teste com o relógio.
    """
    from Relogio import ClockAgent
    
    # Criar relógio
    clock = ClockAgent("clock@localhost", "password", tick_duration_seconds=2.0)
    await clock.start()
    print("Relógio iniciado\n")
    
    # Aguardar setup do relógio
    await asyncio.sleep(0.1)
    
    # Criar agente de teste
    test_agent = SimpleTestAgent("testagent@localhost", "password", "clock@localhost")
    test_agent2 = SimpleTestAgent("testagent2@localhost", "password", "clock@localhost")

    await test_agent2.start()
    print("Agente de teste 2 iniciado\n")
    await test_agent.start()
    print("Agente de teste iniciado\n")
    
    # Aguardar registro
    await asyncio.sleep(0.1)
    
    # Iniciar simulação do relógio
    print("Iniciando simulação...\n")
    clock.start_simulation()
    
    # Deixar rodar por 10 segundos (aprox. 5 ticks com duração de 2s cada)
    await asyncio.sleep(100)
    
    # Parar simulação
    print("\n Parando simulação...")
    clock.stop_simulation()
    
    # Aguardar um pouco antes de desligar
    await asyncio.sleep(2)
    
    # Parar agentes
    await test_agent.stop()
    await test_agent2.stop()
    await clock.stop()
    
    print("\n Teste concluído!")


if __name__ == "__main__":
    asyncio.run(main())
