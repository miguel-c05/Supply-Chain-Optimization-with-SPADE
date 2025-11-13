from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, OneShotBehaviour
from spade.message import Message
import asyncio
from datetime import datetime
from clock_utils import ClockSyncMixin
import random
import json
from MiddleManAgent import MiddleManAgent

class SimpleTestAgent(Agent):
    """
    Agente simples para testar o Relógio.
    - Regista-se no relógio
    - Imprime quando recebe o tick (fase de comunicação)
    - Imprime quando recebe a fase de ação
    - Espera 1 segundo por cada ação
    
    Usa ClockSyncMixin para facilitar a sincronização com o relógio.
    """

    def __init__(self, jid, password, clock_jid):
        super().__init__(jid, password)
        self.clock_jid = clock_jid
        
        self.communication_phase = False
        self.action_phase = False

    async def setup(self):
        print(f"[{self.name}] Agente de teste inicializado")
        self.middleman = MiddleManAgent(f"middleman_{self.jid}", "password", self.clock_jid, self.jid)
        await self.middleman.start()
        self.add_behaviour(self.CommunicationPhaseBehaviour())
        self.add_behaviour(self.ActionPhaseBehaviour())

    class CommunicationPhaseBehaviour(CyclicBehaviour):
        """
        Comportamento que responde às mensagens do relógio.
        Usa handle_clock_message() do ClockSyncMixin para processar mensagens.
        ......"""

        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                # Verificar se está na fase de comunicação OU se a mensagem é do middleman com phase "communication"
                if msg.sender == str(self.agent.middleman.jid) and msg.metadata.get("phase") == "communication":
                    self.agent.communication_phase = True
                
                if self.agent.communication_phase:
                    tick = msg.metadata.get("tick")
                    print(f"[{self.agent.name}]  Executar comunicação")
                    print (f"tick duration: {msg.metadata.get('tick_duration')}")

                    await asyncio.sleep(1)  # Simula o tempo de processamento da comunicação
                    mensagem = Message(to=str(self.agent.middleman.jid))
                    mensagem.metadata = {
                        "phase": "communication",
                        "tick": tick
                    }
                    await self.send(mensagem)
                    # TODO: Alterar funçao com as logisticas
                    self.agent.communication_phase = False


    class ActionPhaseBehaviour(CyclicBehaviour):
        """
        Comportamento que responde às mensagens do relógio.
        Usa handle_clock_message() do ClockSyncMixin para processar mensagens.
        """

        async def run(self):
            msg = await self.receive(timeout=1)

            if msg:
                # Verificar se está na fase de ação OU se a mensagem é do middleman com phase "action"
                if msg.sender == str(self.agent.middleman.jid) and msg.metadata.get("phase") == "action":
                    self.agent.action_phase = True

                if self.agent.action_phase:
                    tick = msg.metadata.get("tick")
                    print(f"[{self.agent.name}]  Executar ação")
                    print (f"tick duration: {msg.metadata.get('tick_duration')}")

                    await asyncio.sleep(1)  # Simula o tempo de processamento da ação
                    mensagem = Message(to=str(self.agent.middleman.jid))
                    mensagem.metadata = {
                        "phase": "action",
                        "tick": tick
                    }
                    await self.send(mensagem)
                    # TODO: Alterar funçao com as logisticas
                    self.agent.action_phase = False
            


async def main():
    """
    Exemplo de execução do agente de teste com o relógio.
    """
    from Relogio import ClockAgent
    
    # Criar relógio
    clock = ClockAgent("clock@localhost", "password", tick_duration_seconds=2.0)
    await clock.start()
    print("Relógio iniciado\n")
    
    # Criar agente de teste
    test_agent = SimpleTestAgent("testagent@localhost", "password", "clock@localhost")
    test_agent2 = SimpleTestAgent("testagent2@localhost", "password", "clock@localhost")

    await test_agent2.start()
    await test_agent.start()

    print("Iniciando simulação...\n")
    clock.start_simulation()
    
    # Deixar rodar por 10 segundos
    await asyncio.sleep(10)
    
    # Parar simulação
    print("\n Parando simulação...")
    clock.stop_simulation()
    
    # Aguardar um pouco antes de desligar
    await asyncio.sleep(2)
    
    # Parar agentes
    await test_agent.stop()
    await test_agent.middleman.stop()
    await test_agent2.stop()
    await test_agent2.middleman.stop()
    await clock.stop()
    
    print("\n Teste concluído!")


if __name__ == "__main__":
    asyncio.run(main())
