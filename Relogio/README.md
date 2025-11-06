# Agente Relógio (ClockAgent)

Sistema de sincronização por ticks para simulações multi-agente em SPADE.

## Como Funciona

O `ClockAgent` coordena a simulação através de **ticks**. Cada tick representa uma unidade de tempo e o relógio só avança quando **todos os agentes registrados** confirmam que processaram o tick atual.

### Fluxo de Execução

```
1. ClockAgent envia "new_tick" para todos os agentes
2. Cada agente processa sua lógica
3. Cada agente envia "tick_confirm" de volta
4. ClockAgent aguarda confirmação de TODOS
5. ClockAgent avança para o próximo tick
6. Repete o processo
```

## Estrutura de Mensagens

### Registro de Agente

**Enviar para o ClockAgent:**

```json
{
  "metadata": { "type": "register" },
  "body": { "agent_name": "nome_do_agente" }
}
```

**Confirmação recebida:**

```json
{
  "metadata": { "type": "register_confirm" },
  "body": {
    "status": "registered",
    "current_tick": 0,
    "tick_duration": 1.0
  }
}
```

### Novo Tick

**Recebida do ClockAgent:**

```json
{
  "metadata": { "type": "new_tick" },
  "body": {
    "tick": 5,
    "tick_duration": 1.0,
    "timestamp": "2025-11-04T10:30:00.000000"
  }
}
```

### Confirmação de Tick

**Enviar para o ClockAgent:**

```json
{
  "metadata": { "type": "tick_confirm" },
  "body": {
    "tick": 5,
    "agent_name": "nome_do_agente",
    "status": "processed"
  }
}
```

## Exemplo de Uso

### 1. Criar o ClockAgent

```python
from Relogio.Relogio import ClockAgent

clock = ClockAgent(
    jid="clock@localhost",
    password="password",
    tick_duration_seconds=1.0  # Cada tick = 1 segundo (conceitual)
)
await clock.start()
```

### 2. Criar Agentes Sincronizados

```python
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
import json

class MeuAgente(Agent):
    def __init__(self, jid, password, clock_jid):
        super().__init__(jid, password)
        self.clock_jid = clock_jid
        self.current_tick = 0

    async def setup(self):
        self.add_behaviour(self.TickBehaviour())
        await self.register_with_clock()

    async def register_with_clock(self):
        msg = Message(to=self.clock_jid)
        msg.metadata = {"type": "register"}
        msg.body = json.dumps({"agent_name": self.name})
        await self.send(msg)

    class TickBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)

            if msg and msg.metadata.get("type") == "new_tick":
                data = json.loads(msg.body)
                tick = data["tick"]

                # SUA LÓGICA AQUI
                await self.minha_logica(tick)

                # Confirmar tick
                reply = Message(to=self.agent.clock_jid)
                reply.metadata = {"type": "tick_confirm"}
                reply.body = json.dumps({"tick": tick})
                await self.send(reply)

        async def minha_logica(self, tick):
            print(f"Processando tick {tick}")
            # Sua lógica de negócio aqui
```

### 3. Iniciar Simulação

```python
# Iniciar relógio
clock.start_simulation()

# Aguardar ticks
await asyncio.sleep(10)

# Parar
clock.stop_simulation()
```

## Características

### ✅ Vantagens

- **Sincronização garantida**: Todos os agentes processam o mesmo tick antes de avançar
- **Timeout configurável**: Evita deadlocks se algum agente falhar
- **Registro dinâmico**: Agentes podem entrar/sair durante a simulação
- **Rastreamento**: Logs detalhados de cada tick

### ⚙️ Configuração

- `tick_duration_seconds`: Duração conceitual de cada tick (não afeta velocidade real)
- Timeout de confirmação: 30 segundos (configurável em `wait_for_confirmations`)

### 🔧 Métodos Úteis

**ClockAgent:**

- `start_simulation()`: Inicia a contagem de ticks
- `stop_simulation()`: Para a simulação
- `register_agent(jid)`: Registra manualmente um agente
- `unregister_agent(jid)`: Remove um agente

## Integração com VehicleAgent

Para integrar com o `VehicleAgent`, adicione o comportamento de sincronização:

```python
class VehicleAgent(Agent):
    def __init__(self, jid, password, graph, capacity, fuel, clock_jid):
        super().__init__(jid, password)
        # ... atributos existentes ...
        self.clock_jid = clock_jid
        self.current_tick = 0

    async def setup(self):
        # Comportamentos existentes
        self.add_behaviour(self.VehicleBehaviour())

        # Adicionar sincronização com relógio
        self.add_behaviour(self.ClockSyncBehaviour())

        # Registrar no relógio
        await self.register_with_clock()

    class ClockSyncBehaviour(CyclicBehaviour):
        async def run(self):
            msg = await self.receive(timeout=10)

            if msg and msg.metadata.get("type") == "new_tick":
                data = json.loads(msg.body)
                tick = data["tick"]
                self.agent.current_tick = tick

                # Processar movimento, entregas, etc.
                await self.process_tick(tick)

                # Confirmar
                reply = Message(to=self.agent.clock_jid)
                reply.metadata = {"type": "tick_confirm"}
                reply.body = json.dumps({"tick": tick})
                await self.send(reply)

        async def process_tick(self, tick):
            # Lógica do veículo por tick
            if self.agent.is_moving:
                await self.agent.move_one_step()
            # etc.
```

## Notas Importantes

1. **Todos os agentes devem confirmar**: O relógio só avança quando TODOS confirmam
2. **Timeout**: Se um agente não responder em 30s, o tick avança mesmo assim (configurável)
3. **Registro obrigatório**: Agentes precisam se registrar antes de receber ticks
4. **Comportamento Cíclico**: Use `CyclicBehaviour` e aguarde mensagens do tipo `new_tick`

## Troubleshooting

**Relógio não avança:**

- Verifique se todos os agentes estão registrados
- Confirme que todos enviam `tick_confirm`
- Verifique os logs para ver quais agentes não respondem

**Agente não recebe ticks:**

- Confirme que o agente se registrou (`register` message)
- Verifique se o JID do relógio está correto
- Certifique-se que o comportamento está escutando mensagens
