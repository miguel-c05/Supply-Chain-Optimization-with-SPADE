"""
Utilidades para sincronização de agentes com o ClockAgent.

Este módulo fornece funções auxiliares para que qualquer agente
possa facilmente se registrar e interagir com o ClockAgent.
"""

from spade.message import Message
import json


async def register_with_clock(agent, clock_jid: str):
    """
    Registra o agente no ClockAgent.
    Deve ser chamado UMA VEZ no setup() do agente.
    
    Args:
        agent: Instância do agente SPADE
        clock_jid: JID do ClockAgent (ex: "clock@localhost")
    
    Exemplo:
        async def setup(self):
            await register_with_clock(self, "clock@localhost")
    """
    msg = Message(to=clock_jid)
    msg.metadata = {"type": "register"}
    msg.body = json.dumps({
        "agent_name": agent.agent.name,
        "jid": str(agent.agent.jid)
    })
    print(f'{agent.agent.name} -> {clock_jid}')
    await agent.send(msg)
    print(f"[{agent.agent.name}] Enviado pedido de registro ao relógio {clock_jid}")


async def unregister_from_clock(agent, clock_jid: str):
    """
    Remove o registro do agente no ClockAgent.
    Deve ser chamado quando o agente quer sair da simulação.
    
    Args:
        agent: Instância do agente SPADE
        clock_jid: JID do ClockAgent (ex: "clock@localhost")
    
    Exemplo:
        async def on_end(self):
            await unregister_from_clock(self, self.clock_jid)
    """
    msg = Message(to=clock_jid)
    msg.metadata = {"type": "unregister"}
    msg.body = json.dumps({
        "agent_name": agent.agent.name,
        "jid": str(agent.agent.jid)
    })
    await agent.send(msg)
    print(f"[{agent.agent.name}] Enviado pedido de desregistro ao relógio {clock_jid}")


async def confirm_communication_phase(agent, clock_jid: str, tick: int, additional_data: dict = None):
    """
    Envia confirmação ao ClockAgent de que o agente terminou a FASE DE COMUNICAÇÃO.
    Deve ser chamado após enviar e receber todas as mensagens do tick.
    
    Args:
        agent: Instância do agente SPADE
        clock_jid: JID do ClockAgent
        tick: Número do tick que foi processado
        additional_data: Dados adicionais opcionais
    
    Exemplo:
        # Fase de comunicação
        await self.send_messages()
        await self.receive_messages()
        await confirm_communication_phase(self.agent, self.agent.clock_jid, tick)
    """
    body_data = {
        "tick": tick,
        "agent_name": agent.agent.name,
        "phase": "communication",
        "status": "ready"
    }
    
    if additional_data:
        body_data.update(additional_data)
    
    msg = Message(to=clock_jid)
    msg.metadata = {"type": "communication_ready"}
    msg.body = json.dumps(body_data)
    await agent.send(msg)


async def confirm_action_phase(agent, clock_jid: str, tick: int, action_taken: bool = False, additional_data: dict = None):
    """
    Envia confirmação ao ClockAgent de que o agente terminou a FASE DE AÇÃO.
    Deve ser chamado após processar mensagens e executar ação do tick.
    
    Args:
        agent: Instância do agente SPADE
        clock_jid: JID do ClockAgent
        tick: Número do tick que foi processado
        action_taken: Se o agente executou uma ação neste tick
        additional_data: Dados adicionais opcionais
    
    Exemplo:
        # Fase de ação
        await self.process_messages()
        await self.execute_action()
        await confirm_action_phase(self.agent, self.agent.clock_jid, tick, action_taken=True)
    """
    body_data = {
        "tick": tick,
        "agent_name": agent.agent.name,
        "phase": "action",
        "action_taken": action_taken,
        "status": "ready"
    }
    
    if additional_data:
        body_data.update(additional_data)
    
    msg = Message(to=clock_jid)
    msg.metadata = {"type": "action_ready"}
    msg.body = json.dumps(body_data)
    await agent.send(msg)


async def confirm_tick(agent, clock_jid: str, tick: int, additional_data: dict = None):
    """
    [DEPRECATED] Use confirm_communication_phase() e confirm_action_phase() separadamente.
    
    Envia confirmação ao ClockAgent de que o agente processou o tick.
    Mantido para compatibilidade com código antigo.
    """
    await confirm_action_phase(agent, clock_jid, tick, additional_data=additional_data)


def is_phase_change_message(msg: Message) -> bool:
    """
    Verifica se a mensagem recebida é uma mudança de fase do relógio.
    
    Args:
        msg: Mensagem SPADE recebida
    
    Returns:
        True se for mensagem de mudança de fase, False caso contrário
    
    Exemplo:
        msg = await self.receive(timeout=10)
        if msg and is_phase_change_message(msg):
            # Processar mudança de fase
    """
    if not msg or not msg.metadata:
        return False
    return msg.metadata.get("type") == "phase_change"


def is_new_tick_message(msg: Message) -> bool:
    """
    Verifica se a mensagem recebida é um novo tick do relógio.
    
    Args:
        msg: Mensagem SPADE recebida
    
    Returns:
        True se for mensagem de novo tick, False caso contrário
    
    Exemplo:
        msg = await self.receive(timeout=10)
        if msg and is_new_tick_message(msg):
            # Processar tick
    """
    if not msg or not msg.metadata:
        return False
    return msg.metadata.get("type") == "new_tick"


def is_register_confirm_message(msg: Message) -> bool:
    """
    Verifica se a mensagem recebida é uma confirmação de registro.
    
    Args:
        msg: Mensagem SPADE recebida
    
    Returns:
        True se for confirmação de registro, False caso contrário
    """
    if not msg or not msg.metadata:
        return False
    return msg.metadata.get("type") == "register_confirm"


def is_unregister_confirm_message(msg: Message) -> bool:
    """
    Verifica se a mensagem recebida é uma confirmação de desregistro.
    
    Args:
        msg: Mensagem SPADE recebida
    
    Returns:
        True se for confirmação de desregistro, False caso contrário
    """
    if not msg or not msg.metadata:
        return False
    return msg.metadata.get("type") == "unregister_confirm"


def parse_tick_message(msg: Message) -> dict:
    """
    Extrai os dados de uma mensagem de tick.
    
    Args:
        msg: Mensagem de tick do ClockAgent
    
    Returns:
        Dicionário com 'tick', 'phase', 'phase_duration', 'tick_duration' e 'timestamp'
        Retorna None se a mensagem for inválida
    
    Exemplo:
        if is_new_tick_message(msg):
            data = parse_tick_message(msg)
            tick = data['tick']
            phase = data['phase']  # 'communication' ou 'action'
            phase_duration = data['phase_duration']
    """
    try:
        return json.loads(msg.body)
    except (json.JSONDecodeError, AttributeError):
        return None


def parse_phase_change_message(msg: Message) -> dict:
    """
    Extrai os dados de uma mensagem de mudança de fase.
    
    Args:
        msg: Mensagem de mudança de fase do ClockAgent
    
    Returns:
        Dicionário com 'tick', 'phase', 'phase_duration' e 'timestamp'
        Retorna None se a mensagem for inválida
    
    Exemplo:
        if is_phase_change_message(msg):
            data = parse_phase_change_message(msg)
            phase = data['phase']  # Sempre 'action'
    """
    try:
        return json.loads(msg.body)
    except (json.JSONDecodeError, AttributeError):
        return None


def parse_register_confirm_message(msg: Message) -> dict:
    """
    Extrai os dados de uma mensagem de confirmação de registro.
    
    Args:
        msg: Mensagem de confirmação do ClockAgent
    
    Returns:
        Dicionário com 'status', 'current_tick' e 'tick_duration'
        Retorna None se a mensagem for inválida
    
    Exemplo:
        if is_register_confirm_message(msg):
            data = parse_register_confirm_message(msg)
            current_tick = data['current_tick']
    """
    try:
        return json.loads(msg.body)
    except (json.JSONDecodeError, AttributeError):
        return None


class ClockSyncMixin:
    """
    Mixin para adicionar funcionalidades de sincronização com o relógio (2 FASES).
    
    Uso:
        class MeuAgente(Agent, ClockSyncMixin):
            def __init__(self, jid, password, clock_jid):
                super().__init__(jid, password)
                self.setup_clock_sync(clock_jid)
            
            async def setup(self):
                await self.register_with_clock()
    """
    
    def setup_clock_sync(self, clock_jid: str):
        """
        Inicializa os atributos necessários para sincronização.
        Deve ser chamado no __init__ do agente.
        
        Args:
            clock_jid: JID do ClockAgent
        """
        self.clock_jid = clock_jid
        self.current_tick = 0
        self.current_phase = None  # 'communication' ou 'action'
        self.is_registered_with_clock = False
    
    async def register_with_clock(self):
        """Registra o agente no relógio (chamado UMA VEZ)"""
        await register_with_clock(self, self.clock_jid)
    
    async def unregister_from_clock(self):
        """Remove o registro do agente no relógio"""
        await unregister_from_clock(self, self.clock_jid)
    
    async def confirm_communication_phase(self, tick: int, additional_data: dict = None):
        """Confirma o processamento da fase de comunicação"""
        await confirm_communication_phase(self, self.agent.clock_jid, tick, additional_data)
    
    async def confirm_action_phase(self, tick: int, action_taken: bool = False, additional_data: dict = None):
        """Confirma o processamento da fase de ação"""
        await confirm_action_phase(self, self.agent.clock_jid, tick, action_taken, additional_data)
    
    async def confirm_tick(self, tick: int, additional_data: dict = None):
        """[DEPRECATED] Use confirm_communication_phase() e confirm_action_phase()"""
        await confirm_tick(self, self.agent.clock_jid, tick, additional_data)

    def handle_clock_message(self, msg: Message) -> tuple:
        """
        Processa mensagens do relógio (2 FASES).
        
        Args:
            msg: Mensagem recebida
        
        Returns:
            Tupla (tipo_mensagem, dados) onde:
            - tipo_mensagem: 'new_tick', 'phase_change', 'register_confirm', 'unregister_confirm' ou None
            - dados: Dicionário com os dados da mensagem ou None
        
        Exemplo:
            msg = await self.receive(timeout=10)
            msg_type, data = self.handle_clock_message(msg)
            
            if msg_type == 'new_tick':
                # FASE DE COMUNICAÇÃO iniciada
                tick = data['tick']
                phase = data['phase']  # 'communication'
                await self.communication_phase(tick)
                await self.confirm_communication_phase(tick)
            
            elif msg_type == 'phase_change':
                # FASE DE AÇÃO iniciada
                tick = data['tick']
                phase = data['phase']  # 'action'
                await self.action_phase(tick)
                await self.confirm_action_phase(tick)
        """
        if not msg:
            return None, None
        
        if is_new_tick_message(msg):
            data = parse_tick_message(msg)
            if data:
                self.current_tick = data['tick']
                self.current_phase = data.get('phase', 'communication')
            return 'new_tick', data
        
        elif is_phase_change_message(msg):
            data = parse_phase_change_message(msg)
            if data:
                self.current_phase = data.get('phase', 'action')
            return 'phase_change', data
        
        elif is_register_confirm_message(msg):
            data = parse_register_confirm_message(msg)
            if data:
                self.is_registered_with_clock = True
                self.current_tick = data.get('current_tick', 0)
            return 'register_confirm', data
        
        elif is_unregister_confirm_message(msg):
            self.is_registered_with_clock = False
            try:
                data = json.loads(msg.body)
            except:
                data = {}
            return 'unregister_confirm', data
        
        return None, None
