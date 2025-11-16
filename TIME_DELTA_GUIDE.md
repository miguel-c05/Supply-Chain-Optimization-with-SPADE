# WorldAgent Time-Delta Simulation

## Descrição

O WorldAgent agora suporta simulação baseada em mensagens com **time-delta**. Você pode enviar uma mensagem solicitando que o mundo simule um número específico de ticks, e o agente retornará o estado de todas as arestas após a simulação.

## Funcionalidade

### Mensagem de Request (Time-Delta)

**Template**: `performative: request`

**Formato da Mensagem**:
```json
{
    "delta_time": 5
}
```

**Campos**:
- `delta_time` (int): Número de ticks a simular

### Resposta (Time-Delta Response)

**Template**: `performative: inform`

**Formato da Resposta**:
```json
{
    "type": "time_delta_response",
    "delta_time": 5,
    "final_tick": 25,
    "edges": [
        {
            "node1_id": 0,
            "node2_id": 1,
            "new_time": 1.0,
            "new_fuel_consumption": 0.098,
            "time_instant": 1731772345.123
        },
        {
            "node1_id": 1,
            "node2_id": 2,
            "new_time": 4.0,
            "new_fuel_consumption": 0.156,
            "time_instant": 1731772345.123
        }
    ]
}
```

**Campos da Resposta**:
- `type`: Tipo da mensagem ("time_delta_response")
- `delta_time`: Número de ticks simulados
- `final_tick`: Tick final após a simulação
- `edges`: Lista com informações de todas as arestas

**Campos de Cada Edge**:
- `node1_id`: ID do nó origem
- `node2_id`: ID do nó destino
- `new_time`: Novo tempo de viagem (weight) da aresta
- `new_fuel_consumption`: Novo consumo de combustível em litros
- `time_instant`: Timestamp Unix quando a simulação foi executada

## Como Usar

### 1. Iniciar o WorldAgent

```bash
python world_agent.py
```

Certifique-se de que o servidor XMPP está rodando.

### 2. Enviar Mensagem Time-Delta

De outro agente SPADE:

```python
from spade.message import Message
import json

# Criar mensagem
msg = Message(to="world@localhost")
msg.set_metadata("performative", "request")
msg.body = json.dumps({
    "delta_time": 10  # Simular 10 ticks
})

# Enviar
await self.send(msg)

# Receber resposta
response = await self.receive(timeout=30)
data = json.loads(response.body)

# Processar dados das arestas
for edge in data['edges']:
    print(f"Edge {edge['node1_id']}→{edge['node2_id']}: "
          f"time={edge['new_time']}, fuel={edge['new_fuel_consumption']}L")
```

### 3. Testar com o Cliente de Exemplo

```bash
python test_time_delta.py
```

Este script envia uma requisição de 5 ticks e exibe os resultados.

## Exemplo de Output

```
[WorldAgent] Received time-delta request: 5 ticks from test@localhost
[WorldAgent] Simulated tick 1
[WorldAgent] Simulated tick 2
[WorldAgent] Simulated tick 3
[WorldAgent] Simulated tick 4
[WorldAgent] Simulated tick 5
[WorldAgent] Sent time-delta response with 164 edge updates

[TestAgent] Received response:
  Type: time_delta_response
  Delta Time: 5
  Final Tick: 5
  Number of Edges: 164

  Sample Edge Updates (first 5):
    Edge 1: 0 -> 1
      Time: 1.0
      Fuel: 0.098 L
      Instant: 1731772345.123
    Edge 2: 1 -> 0
      Time: 1.0
      Fuel: 0.098 L
      Instant: 1731772345.123

  Edges with Traffic:
    5 -> 10: time=4.0, fuel=0.156L
    10 -> 5: time=4.0, fuel=0.156L
    12 -> 13: time=3.0, fuel=0.134L
```

## Casos de Uso

### 1. Simulação Rápida

Avançar o mundo vários ticks de uma vez para análise:

```python
msg.body = json.dumps({"delta_time": 100})
```

### 2. Análise de Tráfego

Verificar quais arestas têm tráfego após simulação:

```python
response = await self.receive(timeout=30)
data = json.loads(response.body)

traffic_edges = [e for e in data['edges'] if e['new_time'] > e.get('initial_time', 1)]
print(f"Arestas congestionadas: {len(traffic_edges)}")
```

### 3. Planejamento de Rotas

Obter estado atual da rede para calcular rotas otimizadas:

```python
# Simular 1 tick para obter estado atual
msg.body = json.dumps({"delta_time": 1})
await self.send(msg)

response = await self.receive(timeout=10)
data = json.loads(response.body)

# Usar dados das arestas para algoritmo de roteamento
edges = data['edges']
# ... aplicar Dijkstra com weights atualizados
```

### 4. Monitoramento de Combustível

Calcular consumo total de combustível na rede:

```python
response = await self.receive(timeout=30)
data = json.loads(response.body)

total_fuel = sum(e['new_fuel_consumption'] for e in data['edges'])
print(f"Consumo total da rede: {total_fuel:.2f} litros")
```

## Notas

- **Performance**: Para `delta_time` grande, a resposta pode conter muitos dados (número_de_arestas × delta_time)
- **Time Instant**: Todas as arestas em um mesmo tick têm o mesmo `time_instant`
- **Direção**: Cada aresta é bidirecional, então você receberá dados para ambas as direções (node1→node2 e node2→node1)
- **Fuel Consumption**: É calculado considerando distância, peso do veículo, e fator de tráfego atual

## Estrutura do JSON de Resposta

```
time_delta_response
├── type: "time_delta_response"
├── delta_time: número de ticks simulados
├── final_tick: tick final do mundo
└── edges: array de edge_info
    └── edge_info
        ├── node1_id: ID do nó origem
        ├── node2_id: ID do nó destino
        ├── new_time: peso/tempo da aresta
        ├── new_fuel_consumption: litros
        └── time_instant: timestamp Unix
```

## Requisitos

- SPADE instalado (`pip install spade`)
- Servidor XMPP rodando (ejabberd, Prosody, etc.)
- WorldAgent configurado e rodando
- Credenciais XMPP válidas para os agentes
