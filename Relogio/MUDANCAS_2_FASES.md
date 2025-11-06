# Sistema de 2 Fases - ClockAgent

## 🎯 O que mudou?

O **ClockAgent** agora divide cada tick em **2 FASES**:

### ⏱️ Estrutura de um Tick:

```
TICK N
├─ FASE 1: COMUNICAÇÃO (50% do tempo)
│  ├─ ClockAgent envia "new_tick" com phase="communication"
│  ├─ Agentes ENVIAM mensagens para outros agentes
│  ├─ Agentes RECEBEM mensagens de outros agentes
│  ├─ Agentes armazenam mensagens recebidas
│  └─ Agentes confirmam: "communication_ready"
│
└─ FASE 2: AÇÃO (50% do tempo)
   ├─ ClockAgent envia "phase_change" com phase="action"
   ├─ Agentes PROCESSAM todas as mensagens recebidas
   ├─ Agentes DECIDEM e EXECUTAM ação (apenas uma!)
   ├─ Agentes preparam mensagens para próximo tick
   └─ Agentes confirmam: "action_ready"
```

---

## 📦 Arquivos Modificados:

### 1. **`Relogio.py`** - ClockAgent

#### Novos parâmetros:

```python
ClockAgent(
    jid="clock@localhost",
    password="password",
    tick_duration_seconds=1.0,      # Duração total do tick
    communication_ratio=0.5          # % para comunicação (0.5 = 50%)
)
```

#### Novos atributos:

```python
self.current_phase                   # 'communication' ou 'action'
self.agents_communication_ready      # Set de agentes que confirmaram comunicação
self.agents_action_ready             # Set de agentes que confirmaram ação
```

#### Mensagens enviadas pelo ClockAgent:

**FASE 1 - Início do Tick (Comunicação):**

```python
{
    "metadata": {"type": "new_tick"},
    "body": {
        "tick": 5,
        "phase": "communication",
        "phase_duration": 0.5,      # Tempo desta fase
        "tick_duration": 1.0,       # Tempo total do tick
        "timestamp": "..."
    }
}
```

**FASE 2 - Mudança de Fase (Ação):**

```python
{
    "metadata": {"type": "phase_change"},
    "body": {
        "tick": 5,
        "phase": "action",
        "phase_duration": 0.5,
        "timestamp": "..."
    }
}
```

#### Confirmações esperadas:

**FASE 1:**

```python
{
    "metadata": {"type": "communication_ready"},
    "body": {
        "tick": 5,
        "agent_name": "vehicle1",
        "phase": "communication",
        "status": "ready"
    }
}
```

**FASE 2:**

```python
{
    "metadata": {"type": "action_ready"},
    "body": {
        "tick": 5,
        "agent_name": "vehicle1",
        "phase": "action",
        "action_taken": true,
        "status": "ready"
    }
}
```

---

### 2. **`clock_utils.py`** - Funções Utilitárias

#### Novas funções:

```python
# Confirmar fase de comunicação
await confirm_communication_phase(agent, clock_jid, tick, additional_data)

# Confirmar fase de ação
await confirm_action_phase(agent, clock_jid, tick, action_taken=True, additional_data)

# Verificar mudança de fase
if is_phase_change_message(msg):
    data = parse_phase_change_message(msg)

# Parse de mensagens com fase
data = parse_tick_message(msg)
# Retorna: {'tick': 5, 'phase': 'communication', 'phase_duration': 0.5, ...}
```

#### ClockSyncMixin atualizado:

```python
class MeuAgente(Agent, ClockSyncMixin):
    async def setup(self):
        await self.register_with_clock()

    async def handle_tick(self):
        msg = await self.receive(timeout=10)
        msg_type, data = self.handle_clock_message(msg)

        if msg_type == 'new_tick':
            # FASE DE COMUNICAÇÃO
            await self.communication_phase(data['tick'])
            await self.confirm_communication_phase(data['tick'])

        elif msg_type == 'phase_change':
            # FASE DE AÇÃO
            await self.action_phase(data['tick'])
            await self.confirm_action_phase(data['tick'], action_taken=True)
```

---

## 🔄 Fluxo Completo de um Tick:

```
CLOCK                          AGENT1                         AGENT2
  |                               |                              |
  |--- new_tick (comm) --------->|                              |
  |--- new_tick (comm) -------------------------------->|
  |                               |                              |
  |                               |--- msg: "pedido" ----------->|
  |                               |<-- msg: "resposta" ----------|
  |                               |                              |
  |<-- communication_ready ------|                              |
  |<-- communication_ready ------------------------------|
  |                               |                              |
  | (aguarda TODOS)               |                              |
  |                               |                              |
  |--- phase_change (action) --->|                              |
  |--- phase_change (action) --------------------------->|
  |                               |                              |
  |                    (processa msg "resposta")                |
  |                    (executa ação: mover)                    |
  |                               |                    (processa msg "pedido")
  |                               |                    (executa ação: atender)
  |                               |                              |
  |<-- action_ready -------------|                              |
  |<-- action_ready -------------------------------------|
  |                               |                              |
  | (aguarda TODOS)               |                              |
  |                               |                              |
  |=== TICK 6 inicia ============|============================|
```

---

## 📝 Como Adaptar Agentes Existentes:

### Antes (1 fase):

```python
class VehicleBehaviour(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=10)

        if msg and is_new_tick_message(msg):
            data = parse_tick_message(msg)
            tick = data['tick']

            # Processar tudo junto
            await self.process_tick(tick)
            await self.confirm_tick(tick)
```

### Depois (2 fases):

```python
class VehicleBehaviour(CyclicBehaviour):
    async def run(self):
        msg = await self.receive(timeout=10)
        msg_type, data = self.agent.handle_clock_message(msg)

        if msg_type == 'new_tick':
            # FASE 1: COMUNICAÇÃO
            tick = data['tick']
            phase_duration = data['phase_duration']

            print(f"[{self.agent.name}] FASE COMUNICAÇÃO - Tick {tick}")

            # Enviar mensagens para outros agentes
            await self.send_messages_to_others()

            # Receber e armazenar mensagens
            await self.receive_and_store_messages(phase_duration)

            # Confirmar fase de comunicação
            await self.agent.confirm_communication_phase(tick, {
                'messages_sent': self.agent.messages_sent_count,
                'messages_received': len(self.agent.received_messages)
            })

        elif msg_type == 'phase_change':
            # FASE 2: AÇÃO
            tick = data['tick']

            print(f"[{self.agent.name}] FASE AÇÃO - Tick {tick}")

            # Processar mensagens recebidas na fase anterior
            await self.process_received_messages()

            # Decidir e executar ação (APENAS UMA!)
            action_taken = await self.decide_and_execute_action()

            # Confirmar fase de ação
            await self.agent.confirm_action_phase(tick, action_taken=action_taken, {
                'action_type': self.agent.last_action_type,
                'position': self.agent.current_position
            })
```

---

## ✅ Vantagens do Sistema de 2 Fases:

1. **✅ Garante recepção de todas as mensagens**: Todos os agentes terminam de comunicar antes de agir
2. **✅ Decisões baseadas em informação completa**: Agentes conhecem TODAS as mensagens antes de decidir
3. **✅ Uma ação por tick garantida**: Fase de ação é separada da comunicação
4. **✅ Sincronização clara**: Não há ambiguidade sobre quando comunicar vs. quando agir
5. **✅ Simulação determinística**: Ordem de eventos é previsível

---

## 🎓 Exemplo Prático:

```python
# Inicializar relógio com 2 fases
clock = ClockAgent(
    "clock@localhost",
    "password",
    tick_duration_seconds=2.0,      # 2 segundos por tick
    communication_ratio=0.5         # 1s comunicação + 1s ação
)

# Agente que usa 2 fases
class MyAgent(Agent, ClockSyncMixin):
    def __init__(self, jid, password, clock_jid):
        super().__init__(jid, password)
        self.setup_clock_sync(clock_jid)
        self.received_messages = []
        self.action_taken_this_tick = False

    async def communication_phase(self, tick):
        """FASE 1: Enviar e receber mensagens"""
        # Enviar mensagens
        if tick % 3 == 0:
            await self.send_greeting("agent2@localhost")

        # Receber mensagens (já são armazenadas automaticamente)
        print(f"Mensagens recebidas: {len(self.received_messages)}")

    async def action_phase(self, tick):
        """FASE 2: Processar e agir"""
        # Processar mensagens
        for msg in self.received_messages:
            if msg['type'] == 'greeting':
                print(f"Recebi saudação de {msg['sender']}")

        # Executar ação
        if not self.action_taken_this_tick:
            await self.move_vehicle()
            self.action_taken_this_tick = True

        # Limpar para próximo tick
        self.received_messages = []
        self.action_taken_this_tick = False
```

---

## 🚀 Próximos Passos:

1. Atualizar `exemplo_agente_sincronizado.py` para usar 2 fases
2. Atualizar `VehicleAgent` em `veiculos/veiculos.py`
3. Testar com múltiplos agentes
4. Ajustar `communication_ratio` conforme necessário

O sistema está pronto para uso! 🎉
