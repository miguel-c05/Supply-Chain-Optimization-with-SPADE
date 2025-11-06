from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template
import json
import asyncio

# Importar funções utilitárias do relógio
from clock_utils import (
    register_with_clock,
    unregister_from_clock,
    confirm_tick,
    is_new_tick_message,
    parse_tick_message,
    ClockSyncMixin
)


class SynchronizedAgent(Agent, ClockSyncMixin):
    """
    Exemplo de agente que se sincroniza com o ClockAgent.
    Usa templates para separar mensagens do relógio e de outros agentes.
    Garante que só executa uma ação por tick.
    """

    def __init__(self, jid, password, clock_jid: str):
        super().__init__(jid, password)
        # Inicializar sincronização com relógio
        self.setup_clock_sync(clock_jid)
        
        # Controle de sincronização de ticks
        self.current_tick_data = None
        self.tick_ready = asyncio.Event()
        self.tick_processed = asyncio.Event()
        self.tick_processed.set()  # Inicialmente pronto
        
        # Controle de ações por tick
        self.action_taken_this_tick = False

    async def setup(self):
        print(f"[{self.name}] Iniciando e registrando no relógio...")
        
        # TEMPLATE 1: Mensagens do RELÓGIO (filtrar por sender)
        clock_template = Template()
        clock_template.sender = self.clock_jid
        self.add_behaviour(self.ClockReceiverBehaviour(), template=clock_template)
        
        # TEMPLATE 2: Mensagens de OUTROS AGENTES (filtrar por metadata type)
        agent_template = Template()
        agent_template.metadata = {"type": "agent_message"}
        self.add_behaviour(self.AgentMessageBehaviour(), template=agent_template)
        
        # Comportamento de PROCESSAMENTO de ticks
        self.add_behaviour(self.TickProcessorBehaviour())
        
        # Registrar no relógio (UMA VEZ)
        await self.register_with_clock()

    class ClockReceiverBehaviour(CyclicBehaviour):
        """
        Comportamento 1: RECEBE mensagem do relógio.
        Apenas armazena o tick e notifica o processador.
        NÃO processa diretamente.
        """
        async def run(self):
            msg = await self.receive(timeout=10)
            
            if msg:
                msg_type, data = self.agent.handle_clock_message(msg)
                
                if msg_type == 'register_confirm':
                    print(f"[{self.agent.name}] Registrado no relógio. Tick atual: {data.get('current_tick', 0)}")
                
                elif msg_type == 'new_tick':
                    tick = data['tick']
                    tick_duration = data['tick_duration']
                    
                    # Aguardar processamento anterior terminar
                    await self.agent.tick_processed.wait()
                    
                    print(f"[{self.agent.name}] Tick {tick} recebido do relógio")
                    
                    # Armazenar dados do tick
                    self.agent.current_tick_data = data
                    self.agent.current_tick = tick
                    
                    # Resetar flag de ação
                    self.agent.action_taken_this_tick = False
                    
                    # Sinalizar que tick está pronto para processar
                    self.agent.tick_processed.clear()
                    self.agent.tick_ready.set()
                
                elif msg_type == 'unregister_confirm':
                    print(f"[{self.agent.name}] Desregistrado do relógio")

    class AgentMessageBehaviour(CyclicBehaviour):
        """
        Comportamento 2: RECEBE mensagens de outros agentes.
        Só processa se ainda não executou ação neste tick.
        """
        async def run(self):
            msg = await self.receive(timeout=1)
            
            if msg:
                data = json.loads(msg.body)
                sender = data.get('from', str(msg.sender))
                message_type = data.get('message_type', 'unknown')
                content = data.get('content', '')
                
                print(f"[{self.agent.name}] Mensagem de {sender}: tipo='{message_type}', conteúdo='{content}'")
                
                # Verificar se pode executar ação neste tick
                if self.agent.action_taken_this_tick:
                    print(f"[{self.agent.name}] Já executou uma ação no tick {self.agent.current_tick}. Ignorando mensagem.")
                    return
                
                # Processar a mensagem
                await self.handle_agent_message(sender, message_type, content, msg)
                

        async def handle_agent_message(self, sender: str, message_type: str, content: str, original_msg: Message):
            """
            Processa mensagens de outros agentes.
            Marca que executou uma ação neste tick.
            """
            print(f"[{self.agent.name}] 🔄 Processando mensagem tipo '{message_type}' de {sender}")
            
            if message_type == "greeting":
                # Exemplo: responder a saudação
                print(f"[{self.agent.name}] Recebeu saudação: '{content}'")
                
                # Marcar ação executada
                self.agent.action_taken_this_tick = True
                
                # Enviar resposta
                await self.send_agent_message(
                    sender.split('@')[0] + '@localhost',  # Garantir formato correto
                    "greeting_response",
                    f"Olá de volta, {sender}!"
                )
            
            elif message_type == "request":
                print(f"[{self.agent.name}] Recebeu pedido: '{content}'")
                self.agent.action_taken_this_tick = True
                
                # Processar pedido
                await self.process_request(sender, content)
            
            elif message_type == "info":
                print(f"[{self.agent.name}] Recebeu informação: '{content}'")
                # Apenas armazenar informação (não conta como ação)
            
            else:
                print(f"[{self.agent.name}] Tipo de mensagem desconhecido: '{message_type}'")

        async def send_agent_message(self, target_jid: str, message_type: str, content: str):
            """Envia mensagem para outro agente"""
            msg = Message(to=target_jid)
            msg.metadata = {"type": "agent_message"}
            msg.body = json.dumps({
                "from": self.agent.name,
                "message_type": message_type,
                "content": content
            })
            await self.send(msg)
            print(f"[{self.agent.name}] Enviado '{message_type}' para {target_jid}")

        async def process_request(self, sender: str, request: str):
            """Processa um pedido de outro agente"""
            # Exemplo de processamento
            print(f"[{self.agent.name}] Processando pedido '{request}' de {sender}")
            # Lógica específica aqui

    class TickProcessorBehaviour(CyclicBehaviour):
        """
        Comportamento 3: PROCESSA cada tick.
        Aguarda notificação do ClockReceiverBehaviour.
        Executa a lógica do agente e confirma o tick.
        """
        async def run(self):
            # Aguardar novo tick estar pronto
            await self.agent.tick_ready.wait()
            self.agent.tick_ready.clear()
            
            tick = self.agent.current_tick
            tick_data = self.agent.current_tick_data
            tick_duration = tick_data.get('tick_duration', 1.0)
            
            print(f"[{self.agent.name}] 🔄 Processando tick {tick} (duração: {tick_duration}s)")
 
            # EXECUTAR LÓGICA DO AGENTE
            await self.process_tick(tick, tick_duration)
            
            # CONFIRMAR tick ao relógio
            await self.agent.confirm_tick(tick, {
                'action_taken': self.agent.action_taken_this_tick
            })
            
            print(f"[{self.agent.name}]- Tick {tick} concluído (ação executada: {self.agent.action_taken_this_tick})")
            self.agent.tick_processed.set()

        async def process_tick(self, tick: int, tick_duration: float):
            """
            Lógica do agente executada a cada tick.
            SUBSTITUA com sua lógica específica.
            """
            print(f"[{self.agent.name}] Executando lógica do tick {tick}...")
            
            # Exemplo 1: Enviar mensagem a cada 3 ticks
            if tick % 3 == 0 and not self.agent.action_taken_this_tick:
                print(f"[{self.agent.name}] Enviando mensagem no tick {tick}")
                await self.send_periodic_message()
                self.agent.action_taken_this_tick = True
            
            # Exemplo 2: Checkpoint a cada 5 ticks
            if tick % 5 == 0:
                print(f"[{self.agent.name}] Checkpoint no tick {tick}!")
            
            # Exemplo 3: Verificar estado
            if tick == 10:
                print(f"[{self.agent.name}] Tick 10 alcançado - metade da simulação")
            
            # Simular processamento (opcional)
            # await asyncio.sleep(0.5)

        async def send_periodic_message(self):
            """Envia mensagem periódica para outro agente"""
            # Exemplo: enviar para agent2@localhost
            msg = Message(to="agent2@localhost")
            msg.metadata = {"type": "agent_message"}
            msg.body = json.dumps({
                "from": self.agent.name,
                "message_type": "greeting",
                "content": f"Olá do tick {self.agent.current_tick}!"
            })
            await self.send(msg)
            print(f"[{self.agent.name}] 📤 Mensagem periódica enviada")




# Exemplo de uso completo
async def example_simulation():
    """
    Exemplo de simulação com relógio e múltiplos agentes sincronizados.
    """
    import asyncio
    import sys
    sys.path.append('..')
    from Relogio import ClockAgent
    
    # Criar relógio
    clock = ClockAgent("clock@localhost", "password", tick_duration_seconds=1.0)
    await clock.start()
    
    # Criar agentes sincronizados
    agent1 = SynchronizedAgent("agent1@localhost", "password", "clock@localhost")
    agent2 = SynchronizedAgent("agent2@localhost", "password", "clock@localhost")
    agent3 = SynchronizedAgent("agent3@localhost", "password", "clock@localhost")
    
    await agent1.start()
    await agent2.start()
    await agent3.start()
    
    # Aguardar registros
    print("\n⏳ Aguardando registros dos agentes...\n")
    await asyncio.sleep(2)
    
    # Iniciar simulação
    print("\n" + "="*50)
    print("🚀 INICIANDO SIMULAÇÃO")
    print("="*50 + "\n")
    clock.start_simulation()
    
    # Aguardar alguns ticks
    await asyncio.sleep(3)
    
    # Exemplo: agent1 envia mensagem para agent2
    print("\n📤 Agent1 enviando mensagem para Agent2...\n")
    msg = Message(to="agent2@localhost")
    msg.metadata = {"type": "agent_message"}
    msg.body = json.dumps({
        "from": "agent1",
        "message_type": "greeting",
        "content": "Olá Agent2, como vai?"
    })
    await agent1.send(msg)
    
    # Continuar simulação
    await asyncio.sleep(7)
    
    # Parar simulação
    print("\n" + "="*50)
    print("⏹️  PARANDO SIMULAÇÃO")
    print("="*50 + "\n")
    clock.stop_simulation()
    
    # Limpar
    await asyncio.sleep(1)
    await agent1.stop()
    await agent2.stop()
    await agent3.stop()
    await clock.stop()
    
    print("\n✅ Simulação concluída!")


if __name__ == "__main__":
    import asyncio
    asyncio.run(example_simulation())

