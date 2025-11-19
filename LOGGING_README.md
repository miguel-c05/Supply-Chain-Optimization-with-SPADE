# Sistema de Logging para Métricas da Simulação

Este sistema de logging foi implementado para extrair métricas detalhadas da simulação da cadeia de abastecimento. Cada execução da simulação cria um novo conjunto de ficheiros de log com timestamp único.

## Estrutura de Ficheiros

```
logs/
└── YYYYMMDD_HHMMSS/           # Diretório com timestamp
    ├── messages.csv            # Todas as mensagens entre agentes
    ├── route_calculations.csv  # Cálculos de rotas (Dijkstra/A*)
    ├── vehicle_metrics.csv     # Métricas dos veículos
    ├── inventory_changes.csv   # Mudanças de inventário
    └── order_lifecycle.csv     # Ciclo de vida das encomendas
```

## Ficheiros de Log

### 1. messages.csv

Regista **todas** as mensagens trocadas entre agentes.

**Colunas:**

- `timestamp_real`: Data/hora real
- `timestamp_sim`: Tempo de simulação (ticks)
- `sender`: JID do agente que enviou
- `receiver`: JID do agente que recebeu
- `message_type`: Tipo de mensagem (e.g., "order-proposal", "store-buy")
- `performative`: FIPA performative (e.g., "inform", "request")
- `body_preview`: Primeiros 100 caracteres do corpo da mensagem
- `metadata`: Metadados adicionais

**Métricas Extraíveis:**

- Total de mensagens por tipo
- Padrões de comunicação entre agentes
- Volume de tráfego por agente
- Fluxos de mensagens mais frequentes

### 2. route_calculations.csv

Regista cada cálculo de rota executado pelos veículos.

**Colunas:**

- `timestamp_real`: Data/hora real
- `timestamp_sim`: Tempo de simulação
- `vehicle_jid`: JID do veículo
- `algorithm`: Algoritmo usado ("dijkstra" ou "astar")
- `num_orders`: Número de encomendas no cálculo
- `computation_time_ms`: Tempo de computação em milissegundos
- `route_length`: Número de nós na rota
- `total_distance`: Distância total calculada
- `total_fuel`: Combustível total necessário
- `route_nodes`: Lista de nós da rota

**Métricas Extraíveis:**

- Quantas vezes cada algoritmo foi usado
- Tempo médio de computação por algoritmo
- Complexidade vs tempo de execução
- Performance com diferentes números de encomendas
- Comprimento médio das rotas

### 3. vehicle_metrics.csv

Regista estados dos veículos ao longo do tempo.

**Colunas:**

- `timestamp_real`: Data/hora real
- `timestamp_sim`: Tempo de simulação
- `vehicle_jid`: JID do veículo
- `current_fuel`: Combustível atual
- `current_load`: Carga atual
- `current_location`: Nó atual
- `next_node`: Próximo destino
- `num_active_orders`: Encomendas em execução
- `num_pending_orders`: Encomendas pendentes
- `status`: Estado atual

**Métricas Extraíveis:**

- Utilização média de combustível
- Taxa de ocupação de carga
- Número médio de encomendas por veículo
- Tempo em movimento vs tempo idle

### 4. inventory_changes.csv

Regista todas as mudanças de inventário em warehouses e stores.

**Colunas:**

- `timestamp_real`: Data/hora real
- `timestamp_sim`: Tempo de simulação
- `agent_jid`: JID do warehouse/store
- `agent_type`: "warehouse" ou "store"
- `product`: Identificador do produto
- `change_type`: Tipo de mudança ("purchase", "delivery", "sale", "lock", "unlock")
- `quantity`: Quantidade alterada
- `stock_before`: Nível de stock antes
- `stock_after`: Nível de stock depois

**Métricas Extraíveis:**

- Rotatividade de produtos
- Níveis médios de stock
- Frequência de reabastecimento
- Produtos mais movimentados

### 5. order_lifecycle.csv

Regista o ciclo de vida completo das encomendas.

**Colunas:**

- `timestamp_real`: Data/hora real
- `timestamp_sim`: Tempo de simulação
- `order_id`: ID único da encomenda
- `sender`: JID do remetente
- `receiver`: JID do destinatário
- `product`: Produto
- `quantity`: Quantidade
- `event_type`: Tipo de evento ("created", "proposed", "accepted", "rejected", "pickup", "in_transit", "delivered", "failed")
- `vehicle`: JID do veículo (se aplicável)
- `details`: Detalhes adicionais

**Métricas Extraíveis:**

- Taxa de sucesso de encomendas
- Tempo médio de entrega
- Encomendas rejeitadas vs aceites
- Performance por veículo

## Como Usar

### 1. Executar Simulação

```bash
python simulate.py
```

Os logs são criados automaticamente em `logs/YYYYMMDD_HHMMSS/`

### 2. Analisar Logs

```bash
# Analisar logs mais recentes
python analyze_logs.py

# Analisar logs específicos
python analyze_logs.py logs/20241119_153045
```

### 3. Análise Manual com Pandas

```python
import pandas as pd

# Carregar logs
messages = pd.read_csv('logs/20241119_153045/messages.csv')
routes = pd.read_csv('logs/20241119_153045/route_calculations.csv')

# Análise personalizada
print("Mensagens por tipo:")
print(messages['message_type'].value_counts())

print("\nCálculos por algoritmo:")
print(routes['algorithm'].value_counts())

print("\nTempo médio A*:")
astar = routes[routes['algorithm'] == 'astar']
print(f"{astar['computation_time_ms'].mean():.2f} ms")
```

### 4. Visualização com Excel

Todos os ficheiros CSV podem ser abertos diretamente no Excel para análise visual e criação de gráficos.

## Integração no Código

### Logging de Mensagens

Adicionar após cada `await self.send(message)`:

```python
from logger_utils import MessageLogger

await self.send(message)

# Log message
try:
    msg_logger = MessageLogger.get_instance()
    msg_logger.log_message(
        sender=str(self.agent.jid),
        receiver=str(message.to),
        message_type="order-proposal",
        performative="propose",
        body=message.body
    )
except Exception:
    pass  # Don't crash on logging errors
```

### Logging de Cálculos de Rota

Adicionar antes e depois de `A_star_task_algorithm`:

```python
from logger_utils import RouteCalculationLogger
import time

# Before calculation
start_time = time.time()

route, total_time, _ = A_star_task_algorithm(...)

# After calculation
computation_time = (time.time() - start_time) * 1000
try:
    route_logger = RouteCalculationLogger.get_instance()
    route_logger.log_calculation(
        vehicle_jid=str(self.agent.jid),
        algorithm="astar",
        num_orders=len(orders),
        computation_time_ms=computation_time,
        route_length=len(route),
        total_distance=total_time
    )
except Exception:
    pass
```

### Logging de Inventário

Adicionar quando o stock muda:

```python
from logger_utils import InventoryLogger

# Before stock change
stock_before = self.agent.stock.get(product, 0)

# Change stock
self.agent.stock[product] += quantity

# After stock change
try:
    inventory_logger = InventoryLogger.get_instance()
    inventory_logger.log_inventory_change(
        agent_jid=str(self.agent.jid),
        agent_type="warehouse",
        product=product,
        change_type="delivery",
        quantity=quantity,
        stock_before=stock_before,
        stock_after=self.agent.stock[product]
    )
except Exception:
    pass
```

## Métricas Principais

### Performance de Algoritmos

```python
routes = pd.read_csv('logs/.../route_calculations.csv')

# Comparar Dijkstra vs A*
for algo in routes['algorithm'].unique():
    algo_df = routes[routes['algorithm'] == algo]
    print(f"{algo}:")
    print(f"  Calls: {len(algo_df)}")
    print(f"  Avg time: {algo_df['computation_time_ms'].mean():.2f} ms")
    print(f"  Max time: {algo_df['computation_time_ms'].max():.2f} ms")
```

### Comunicação entre Agentes

```python
messages = pd.read_csv('logs/.../messages.csv')

# Top 10 pares de comunicação
flow = messages.groupby(['sender', 'receiver']).size()
print(flow.sort_values(ascending=False).head(10))

# Mensagens por tipo
print(messages['message_type'].value_counts())
```

### Eficiência de Veículos

```python
vehicles = pd.read_csv('logs/.../vehicle_metrics.csv')

# Utilização média
print(f"Carga média: {vehicles['current_load'].mean():.2f}")
print(f"Combustível médio: {vehicles['current_fuel'].mean():.2f}")
print(f"Encomendas ativas: {vehicles['num_active_orders'].mean():.2f}")
```

## Guia de Integração Completo

Ver ficheiro `LOGGING_INTEGRATION_GUIDE.md` para instruções detalhadas sobre onde adicionar logging em cada ficheiro de agente.

## Notas Importantes

1. **Thread-Safe**: Todos os loggers usam locks para escrita segura
2. **Não-Bloqueante**: Erros de logging não param a simulação
3. **Timestamp Único**: Cada simulação cria um diretório novo
4. **CSV Format**: Facilita análise com Excel, pandas, R, etc.
5. **Singleton Pattern**: Uma instância de logger por toda a simulação

## Troubleshooting

### Logs vazios ou incompletos

- Verificar se `initialize_loggers()` foi chamado em `simulate.py`
- Verificar permissões de escrita na pasta `logs/`

### Erros de import

- Verificar se `logger_utils.py` está no diretório raiz
- Verificar se todos os ficheiros têm os imports corretos

### Performance Impact

- O logging tem impacto mínimo (<1% overhead)
- Em caso de problemas, comentar código de logging temporariamente
