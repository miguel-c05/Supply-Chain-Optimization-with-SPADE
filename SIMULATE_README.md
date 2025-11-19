# Simulação da Cadeia de Abastecimento - Guia de Utilização

## Descrição

O ficheiro `simulate.py` é o ponto de entrada principal para a simulação do sistema de cadeia de abastecimento. Este script cria e inicializa todos os agentes necessários utilizando as configurações definidas no ficheiro `config.py`.

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

## Pré-requisitos

### 1. Servidor XMPP

É necessário um servidor XMPP em execução (recomendado: Openfire, Prosody ou ejabberd).

**Instalação do Openfire (Windows):**

1. Download: https://www.igniterealtime.org/projects/openfire/
2. Instalar e iniciar o serviço
3. Aceder à interface admin: http://localhost:9090
4. Configurar domínio: `localhost`

**Instalação do Prosody (Linux):**

```bash
sudo apt-get install prosody
sudo systemctl start prosody
```

### 2. Contas XMPP

Criar as seguintes contas no servidor XMPP:

| JID                       | Password     |
| ------------------------- | ------------ |
| event_agent@localhost     | event123     |
| world@localhost           | password     |
| warehouse1_test@localhost | warehouse123 |
| warehouse2_test@localhost | warehouse234 |
| store1_test@localhost     | store123     |
| store2_test@localhost     | store234     |
| supplier1_test@localhost  | supplier123  |
| supplier2_test@localhost  | supplier234  |
| vehicle1@localhost        | vehicle123   |
| vehicle2@localhost        | vehicle234   |
| vehicle3@localhost        | vehicle345   |

**Criação via Openfire Admin:**

1. Aceder a http://localhost:9090
2. Ir a "Utilizadores/Grupos" → "Criar Novo Utilizador"
3. Preencher nome de utilizador e palavra-passe
4. Repetir para todas as contas

### 3. Dependências Python

```bash
# Ativar ambiente conda (se aplicável)
conda activate SPADE

# Verificar instalação de dependências
pip install spade aiohttp aiohttp-jinja2 numpy matplotlib
```

## Como Executar

### 1. Verificar Servidor XMPP

```bash
# Windows (Openfire)
# Verificar se o serviço está em execução no Gestor de Tarefas

# Linux (Prosody)
sudo systemctl status prosody
```

### 2. Executar a Simulação

```bash
# Navegar até o diretório do projeto
cd d:\aulas\LAB_iacd\Supply-Chain-Optimization-with-SPADE

# Executar o script de simulação
python simulate.py
```

### 3. Monitorizar Execução

A simulação exibirá logs no terminal indicando:

- Criação do mundo
- Criação de todos os agentes
- Inicialização dos agentes
- Processamento de eventos
- Comunicações entre agentes

### 4. Parar a Simulação

Pressionar `Ctrl+C` para parar a simulação de forma limpa. Todos os agentes serão encerrados corretamente.

## Ordem de Inicialização

Os agentes são iniciados na seguinte ordem (importante para evitar erros):

1. **World Agent** - Primeiro, para estar pronto a responder a pedidos
2. **Veículos** (vehicle1, vehicle2, vehicle3)
3. **Warehouses** (warehouse1, warehouse2)
4. **Suppliers** (supplier1, supplier2)
5. **Stores** (store1, store2)
6. **Event Agent** - Por último, para coordenar todos os outros

## Fluxo de Comunicação

```
┌─────────────┐
│ Event Agent │ ◄──── Coordena todos os eventos
└──────┬──────┘
       │
       ├──────► World Agent (pede simulações de tráfego)
       │
       ├──────► Veículos (envia eventos de arrival/transit)
       │
       └──────► Warehouses/Stores/Suppliers (notifica eventos)

Store ──► Warehouse ──► Vehicle ──► Supplier
 │           │            │            │
 └───────────┴────────────┴────────────┘
             (Comunicação via XMPP)
```

## Troubleshooting

### Erro: "Connection refused"

**Causa:** Servidor XMPP não está em execução.
**Solução:** Iniciar o servidor XMPP antes de executar a simulação.

### Erro: "Authentication failed"

**Causa:** Contas XMPP não foram criadas ou credenciais incorretas.
**Solução:** Verificar se todas as contas foram criadas com as passwords corretas.

### Erro: "Não foram encontrados stores/warehouses/suppliers"

**Causa:** Configuração do mundo não gerou as instalações necessárias.
**Solução:** Ajustar os parâmetros em `config.py`:

```python
WORLD_WAREHOUSES = 2  # Aumentar para garantir múltiplas localizações
WORLD_SUPPLIERS = 2
WORLD_STORES = 2
```

### Erro: "Module not found"

**Causa:** Dependências não instaladas ou ambiente Python incorreto.
**Solução:**

```bash
conda activate SPADE
pip install -r requirements.txt  # Se existir
```

## Diferenças em Relação ao event_agent.py

O ficheiro `simulate.py` difere do main em `event_agent.py` nos seguintes aspetos:

1. **Configurações centralizadas**: Todas as configurações vêm do `config.py`
2. **Mais agentes**: Cria 2 warehouses, 2 stores, 2 suppliers (vs 1 de cada no original)
3. **Estrutura modular**: Separado em secções claras e bem documentadas
4. **Tratamento de erros**: Verifica se existem localizações suficientes antes de criar agentes

## Ficheiros Relacionados

- `simulate.py` - Script principal de simulação
- `config.py` - Configurações centralizadas
- `Eventos/event_agent.py` - Event Agent (referência original)
- `world_agent.py` - World Agent
- `warehouse.py` - Agente Warehouse
- `supplier.py` - Agente Supplier
- `store.py` - Agente Store
- `veiculos/veiculos.py` - Agente Veículo
- `world/world.py` - Classe World

## Autores

Equipa de Desenvolvimento Supply Chain Optimization

## Licença

Consultar ficheiro LICENSE na raiz do projeto.
