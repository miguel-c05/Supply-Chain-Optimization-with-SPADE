# Simulação da Cadeia de Abastecimento - Guia de Utilização

## Descrição

O ficheiro `simulate.py` é o ponto de entrada principal para a simulação do sistema de cadeia de abastecimento. Este script cria e inicializa todos os agentes necessários utilizando as configurações definidas no ficheiro `config.py`  ou parser.

## Agentes Criados

A simulação cria os seguintes agentes:

### 1. **World Agent** (`world@localhost`)

- Gere o estado do mundo e a simulação de tráfego
- Responde a pedidos de simulação do Event Agent
- Gera eventos de alteração de trânsito

### 2. **Event Agent** (`event_agent@localhost`)

- Coordenador central de todos os eventos temporais
- Gere uma heap de eventos ordenados por tempo
- Distribui notificações aos agentes relevantes
- Solicita simulações de tráfego ao World Agent

### 3. **Veículos** (3 instâncias)

- `vehicle1@localhost`
- `vehicle2@localhost`
- `vehicle3@localhost`

Responsabilidades:

- Recebem e processam ordens de entrega
- Calculam rotas otimizadas usando A\*
- Comunicam com warehouses, stores e suppliers
- Enviam eventos de chegada ao Event Agent

### 4. **Warehouses** (2 instâncias)

- `warehouse1_test@localhost`
- `warehouse2_test@localhost`

Responsabilidades:

- Gerem stock de produtos
- Recebem pedidos de stores
- Coordenam entregas com veículos
- Encomendam produtos aos suppliers

### 5. **Stores** (2 instâncias)

- `store1_test@localhost`
- `store2_test@localhost`

Responsabilidades:

- Compram produtos dos warehouses
- Mantêm inventário local
- Registam estatísticas de compras

### 6. **Suppliers** (2 instâncias)

- `supplier1_test@localhost`
- `supplier2_test@localhost`

Responsabilidades:

- Fornecem stock ilimitado de produtos
- Respondem a pedidos de warehouses
- Coordenam entregas com veículos

## Configuração

Todas as configurações são definidas no ficheiro `config.py`. Os parâmetros principais incluem:

### Mundo

```python
WORLD_WIDTH = 5                          # Largura do grafo
WORLD_HEIGHT = 5                         # Altura do grafo
WORLD_MODE = "different"                 # Modo de custos ("uniform" ou "different")
WORLD_MAX_COST = 4                       # Custo máximo das arestas
WORLD_WAREHOUSES = 1                     # Número de warehouses
WORLD_SUPPLIERS = 1                      # Número de suppliers
WORLD_STORES = 1                         # Número de stores
WORLD_HIGHWAY = True                     # Adicionar rodovia de alta capacidade
WORLD_TRAFFIC_PROBABILITY = 0.5          # Probabilidade de trânsito
WORLD_TRAFFIC_SPREAD_PROBABILITY = 0.8   # Probabilidade de propagação
WORLD_TRAFFIC_INTERVAL = 2               # Intervalo de tráfego (ticks)
WORLD_UNTRAFFIC_PROBABILITY = 0.4        # Probabilidade de destrânsito
```

### Veículos

```python
VEHICLE_CAPACITY = 50          # Capacidade de carga
VEHICLE_MAX_FUEL = 100         # Capacidade do tanque
VEHICLE_MAX_ORDERS = 10        # Máximo de ordens simultâneas
VEHICLE_WEIGHT = 1500          # Peso do veículo
```

### Event Agent

```python
EVENT_AGENT_SIMULATION_INTERVAL = 10.0      # Intervalo de processamento (s)
EVENT_AGENT_WORLD_SIMULATION_TIME = 10.0    # Tempo de simulação de tráfego (s)
```

### Produtos e Limites

```python
PRODUCTS = ["A", "B", "C", "D"]
WAREHOUSE_MAX_PRODUCT_CAPACITY = 100
WAREHOUSE_RESUPPLY_THRESHOLD = 20
STORE_MAX_BUY_QUANTITY = 20
STORE_BUY_FREQUENCY = 5
STORE_BUY_PROBABILITY = 0.6
```