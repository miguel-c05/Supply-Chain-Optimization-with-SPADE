"""
Agente Modelo - Estrutura base para agentes sincronizados com relógio

Este agente possui 4 behaviors:
1. Comunicação com o relógio (sincronização)
2. Envio de mensagens (com controle de respostas pendentes)
3. Recepção de mensagens (exceto relógio)
4. Execução de ações (apenas durante fase de ação)
"""

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template
import asyncio
import json
from clock_utils import ClockSyncMixin


class ClockCommunicationBehaviour(CyclicBehaviour):
    """
    Behavior 1: Comunicação com o relógio
    - Recebe mensagens do relógio
    - Envia confirmações
    - Atualiza os ticks
    - Gerencia o tempo dos ticks
    - Utiliza ClockSyncMixin para processar mensagens
    """
    
    async def on_start(self):
        print(f"[{self.agent.name}] ClockCommunicationBehaviour iniciado")
        self.agent.waiting_for_action_phase = False
    
    async def run(self):
        # Espera por mensagem do relógio
        msg = await self.receive(timeout=1)
        
        if msg:
            # Usa o ClockSyncMixin para processar mensagens do relógio
            msg_type, data = self.agent.handle_clock_message(msg)
            
            if msg_type == 'register_confirm':
                # Confirmação de registro recebida
                print(f"[{self.agent.name}] Registrado com sucesso no relógio")
                print(f"[{self.agent.name}] Tick atual: {data.get('current_tick', 0)}")
                
            elif msg_type == 'new_tick':
                # FASE DE COMUNICAÇÃO iniciada
                tick = data['tick']
                phase = data.get('phase', 'communication')
                print(f"[{self.agent.name}] TICK {tick} - Fase: {phase}")
                
                # Reset do estado para novo tick
                self.agent.actions_completed = False
                self.agent.communication_completed = False
                self.agent.waiting_for_action_phase = True
                
            elif msg_type == 'phase_change':
                # FASE DE AÇÃO iniciada
                tick = data['tick']
                phase = data.get('phase', 'action')
                print(f"[{self.agent.name}] Mudança para fase: {phase} (Tick {tick})")
                self.agent.waiting_for_action_phase = False
        
        await asyncio.sleep(0.1)


class SendMessagesBehaviour(CyclicBehaviour):
    """
    Behavior 2: Envio de mensagens (FASE DE COMUNICAÇÃO)
    - Envia mensagens que esperam resposta
    - Envia mensagens que não esperam resposta
    - Controla respostas pendentes
    - Só pode completar fase quando não houver respostas pendentes
    - Executa apenas durante a fase de comunicação
    """
    
    async def on_start(self):
        print(f"[{self.agent.name}] SendMessagesBehaviour iniciado")
        self.agent.pending_responses = {}  # {msg_id: {"to": jid, "content": data}}
        self.agent.messages_to_send = []  # Fila de mensagens para enviar
    
    async def run(self):
        # Só envia mensagens durante a fase de comunicação
        if self.agent.current_phase != 'communication' or not self.agent.is_registered_with_clock:
            await asyncio.sleep(0.1)
            return
        
        # Processa fila de mensagens
        if self.agent.messages_to_send:
            msg_data = self.agent.messages_to_send.pop(0)
            
            # Cria a mensagem
            msg = Message(to=msg_data["to"])
            msg.set_metadata("performative", msg_data.get("performative", "inform"))
            
            msg_id = f"{self.agent.name}_{self.agent.current_tick}_{len(self.agent.pending_responses)}"
            
            body_content = msg_data["content"]
            body_content["msg_id"] = msg_id
            body_content["sender_agent"] = self.agent.name
            
            msg.body = json.dumps(body_content)
            
            # Se espera resposta, adiciona aos pending
            if msg_data.get("expects_response", False):
                self.agent.pending_responses[msg_id] = {
                    "to": msg_data["to"],
                    "content": body_content,
                    "sent_at_tick": self.agent.current_tick
                }
                print(f"[{self.agent.name}] Enviou mensagem {msg_id} (espera resposta)")
            else:
                print(f"[{self.agent.name}] Enviou mensagem {msg_id} (não espera resposta)")
            
            await self.send(msg)
        
        # Verifica se pode completar a fase de comunicação
        if not self.agent.communication_completed and self.can_complete_phase():
            await self._notify_communication_complete()
            self.agent.communication_completed = True
        
        await asyncio.sleep(0.1)
    
    def can_complete_phase(self):
        """
        Verifica se o agente pode completar a fase de comunicação
        Retorna True se não houver respostas pendentes
        """
        return len(self.agent.pending_responses) == 0
    
    async def _notify_communication_complete(self):
        """
        Notifica o relógio que completou a fase de comunicação
        """
        await self.agent.confirm_communication_phase(
            tick=self.agent.current_tick
        )
        print(f"[{self.agent.name}] Fase de comunicação completada no tick {self.agent.current_tick}")


class ReceiveMessagesBehaviour(CyclicBehaviour):
    """
    Behavior 3: Recepção de mensagens
    - Recebe mensagens de outros agentes (exceto relógio)
    - Remove respostas da lista de pending quando recebidas
    - Processa diferentes tipos de mensagens
    """
    
    async def on_start(self):
        print(f"[{self.agent.name}] ReceiveMessagesBehaviour iniciado")
        self.agent.received_messages = []  # Buffer de mensagens recebidas
    
    async def run(self):
        msg = await self.receive(timeout=1)
        
        if msg:
            try:
                content = json.loads(msg.body)
                msg_id = content.get("msg_id")
                msg_type = content.get("type")
                
                print(f"[{self.agent.name}] Recebeu mensagem tipo '{msg_type}' de {msg.sender}")
                
                # Verifica se é resposta a uma mensagem enviada
                response_to = content.get("response_to")
                if response_to and response_to in self.agent.pending_responses:
                    # Remove da lista de respostas pendentes
                    del self.agent.pending_responses[response_to]
                    print(f"[{self.agent.name}] Resposta recebida para {response_to}, respostas pendentes: {len(self.agent.pending_responses)}")
                
                # Armazena a mensagem para processamento
                self.agent.received_messages.append({
                    "sender": str(msg.sender),
                    "content": content,
                    "metadata": msg.metadata
                })
                
                # TODO: Implementar lógica específica para diferentes tipos de mensagens
                # self._process_message(content, msg.sender)
                
            except json.JSONDecodeError:
                print(f"[{self.agent.name}] Erro ao decodificar mensagem: {msg.body}")
        
        await asyncio.sleep(0.1)
    
    def _process_message(self, content, sender):
        """
        Processa mensagens recebidas (para ser implementado)
        """
        # TODO: Implementar processamento específico de mensagens
        pass


class ActionBehaviour(CyclicBehaviour):
    """
    Behavior 4: Execução de ações (FASE DE AÇÃO)
    - Só executa durante a fase de ação
    - Executa ações específicas do agente
    - Comunica ao relógio quando termina as ações
    - Aguarda novo tick
    """
    
    async def on_start(self):
        print(f"[{self.agent.name}] ActionBehaviour iniciado")
        self.agent.actions_completed = False
    
    async def run(self):
        # Só executa ações durante a fase de ação
        if self.agent.current_phase != 'action' or self.agent.waiting_for_action_phase:
            await asyncio.sleep(0.1)
            return
        
        # Se já completou as ações deste tick, não faz nada
        if self.agent.actions_completed:
            await asyncio.sleep(0.1)
            return
        
        print(f"[{self.agent.name}] Executando ações no tick {self.agent.current_tick}")
        
        # TODO: Implementar ações específicas do agente
        await self._execute_actions()
        
        # Sempre completa a fase de ação após executar
        # (diferente da fase de comunicação que depende de respostas)
        await self._notify_action_complete()
        self.agent.actions_completed = True
        print(f"[{self.agent.name}] Fase de ação completada no tick {self.agent.current_tick}")
        
        await asyncio.sleep(0.1)
    
    async def _execute_actions(self):
        """
        Executa as ações específicas do agente (para ser implementado)
        """
        # TODO: Implementar ações específicas
        # Exemplo:
        # - Processar dados recebidos na fase de comunicação
        # - Tomar decisões
        # - Atualizar estado interno
        # - Preparar mensagens para o próximo tick
        
        # Simula algum processamento
        await asyncio.sleep(0.05)
        
        # Exemplo de adicionar mensagem à fila para o próximo tick (descomentar quando necessário)
        # self.agent.messages_to_send.append({
        #     "to": "outro_agente@localhost",
        #     "content": {"type": "EXEMPLO", "data": "teste"},
        #     "expects_response": True,
        #     "performative": "request"
        # })
    
    async def _notify_action_complete(self):
        """
        Notifica o relógio que completou a fase de ação
        """
        await self.agent.confirm_action_phase(
            tick=self.agent.current_tick,
            action_taken=True,  # Pode ser parametrizado se necessário
            additional_data={}
        )
        print(f"[{self.agent.name}] Notificou relógio da conclusão da fase de ação {self.agent.current_tick}")


class ModelAgent(Agent, ClockSyncMixin):
    """
    Agente Modelo com 4 behaviors sincronizados (2 FASES)
    Utiliza ClockSyncMixin para integração com o relógio
    
    Args:
        jid: JID do agente
        password: Senha do agente
        clock_jid: JID do relógio para sincronização
        tick_duration: Duração de cada tick em segundos (argumento do agente)
    """
    
    def __init__(self, jid, password, clock_jid, tick_duration=1.0):
        super().__init__(jid, password)
        
        # Inicializa o ClockSyncMixin
        self.setup_clock_sync(clock_jid)
        
        self.tick_duration = tick_duration
        self.name = jid.split("@")[0]
        
        # Variáveis de controle de fase
        self.waiting_for_action_phase = False
        self.actions_completed = False
        self.communication_completed = False
        
        # Controle de mensagens
        self.pending_responses = {}
        self.messages_to_send = []
        self.received_messages = []
        
        print(f"[{self.name}] Agente criado com tick_duration={tick_duration}s")
    
    async def setup(self):
        print(f"[{self.name}] Setup iniciado")
        
        # Registra no relógio
        await self.register_with_clock()
        
        # Behavior 1: Comunicação com relógio
        clock_template = Template()
        clock_template.sender = self.clock_jid
        clock_behaviour = ClockCommunicationBehaviour()
        self.add_behaviour(clock_behaviour, clock_template)
        
        # Behavior 2: Envio de mensagens (fase de comunicação)
        send_behaviour = SendMessagesBehaviour()
        self.add_behaviour(send_behaviour)
        
        # Behavior 3: Recepção de mensagens (exceto relógio)
        # Template com regex para excluir mensagens do relógio
        receive_template = Template()
        # Aceita mensagens de qualquer sender exceto o relógio
        receive_behaviour = ReceiveMessagesBehaviour()
        self.add_behaviour(receive_behaviour, receive_template)
        
        # Behavior 4: Execução de ações (fase de ação)
        action_behaviour = ActionBehaviour()
        self.add_behaviour(action_behaviour)
        
        print(f"[{self.name}] Todos os behaviours adicionados")
        print(f"[{self.name}] Aguardando sincronização com relógio {self.clock_jid}")


# Exemplo de uso
if __name__ == "__main__":
    import time
    
    # Configurações
    AGENT_JID = "modelo_agent@localhost"
    AGENT_PASSWORD = "password"
    CLOCK_JID = "clock@localhost"
    TICK_DURATION = 2.0  # segundos (argumento do agente)
    
    # Cria e inicia o agente
    agent = ModelAgent(AGENT_JID, AGENT_PASSWORD, CLOCK_JID, TICK_DURATION)
    
    future = agent.start()
    future.result()
    
    print(f"\n{'='*60}")
    print(f"Agente Modelo iniciado: {AGENT_JID}")
    print(f"Conectado ao relógio: {CLOCK_JID}")
    print(f"Duração do tick: {TICK_DURATION}s")
    print(f"Usando ClockSyncMixin para sincronização em 2 FASES")
    print(f"  - Fase 1: COMUNICAÇÃO (envio/recepção de mensagens)")
    print(f"  - Fase 2: AÇÃO (processamento e execução)")
    print(f"{'='*60}\n")
    
    try:
        while agent.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nParando agente...")
        agent.stop()
    
    print("Agente finalizado")
