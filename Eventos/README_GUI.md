# 🖥️ GUI Visualizer - Event-Driven Agent System

## Descrição

Interface gráfica em tempo real para visualização e monitorização do sistema Event-Driven Agent. Permite acompanhar o fluxo de eventos, estatísticas, posições de veículos e o estado do grafo do mundo durante a execução da simulação.

## 🎯 Funcionalidades

### 1. **Visualização do Grafo do Mundo** 🗺️
- Exibe o grafo completo do mundo da simulação
- Cores diferenciadas por tipo de nó:
  - 🟦 **Azul**: Warehouses
  - 🟩 **Verde**: Stores
  - 🟧 **Laranja**: Suppliers
  - ⚪ **Cinzento**: Nós normais
- Indicação visual de tráfego:
  - 🔴 **Vermelho**: Arestas com tráfego (peso > 2)
  - ⚪ **Cinzento**: Arestas normais
- Posições dos veículos em tempo real (estrelas vermelhas ⭐)

### 2. **Timeline de Eventos** 📊
- Gráfico de barras temporais dos eventos
- Separação por tipo:
  - 🔵 **Arrival**: Eventos de chegada de veículos
  - 🟠 **Transit**: Eventos de alteração de tráfego
- Visualização dos últimos 50 eventos
- Actualização automática a cada 500ms

### 3. **Histórico de Eventos** 📜
- Tabela com lista detalhada de eventos
- Informações:
  - **Tempo**: Momento temporal do evento (em segundos)
  - **Tipo**: Categoria do evento (arrival, transit, updatesimulation)
  - **Detalhes**: Descrição específica do evento
- Mantém histórico dos últimos 100 eventos
- Auto-scroll para eventos mais recentes

### 4. **Estatísticas em Tempo Real** 📊
- **📦 Total de Eventos**: Contador global de eventos processados
- **🚚 Eventos Arrival**: Número de chegadas de veículos
- **🚦 Eventos Transit**: Número de alterações de tráfego
- **📋 Eventos na Heap**: Eventos pendentes na heap principal
- **⚡ Transit Ativos**: Eventos de trânsito activos
- **⏱️ Tempo Simulado**: Tempo total de simulação decorrido

### 5. **Monitorização de Veículos** 🚚
- Tabela com estado de cada veículo:
  - **Veículo**: Nome do agente
  - **Localização**: Nó actual no grafo
  - **Combustível**: Nível de combustível actual
- Actualização automática

### 6. **Logs do Sistema** 📝
- Console de logs em tempo real
- Registo com timestamp de todos os eventos
- Auto-scroll para mensagens mais recentes
- Limite de 500 linhas (limpeza automática)

## 🚀 Como Usar

### Pré-requisitos

```bash
# Instalar dependências
pip install matplotlib

# Tkinter geralmente já vem com Python
# Se não, instalar conforme o SO:
# Windows: já incluído
# Linux: sudo apt-get install python3-tk
# macOS: brew install python-tk
```

### Executar com GUI

1. **Iniciar o servidor XMPP** (Openfire/Prosody)

2. **Executar o script principal**:
```bash
cd Eventos
python event_agent.py
```

3. A GUI será aberta automaticamente numa janela separada

4. A simulação inicia e a GUI actualiza em tempo real

### Estrutura da Interface

```
┌─────────────────────────────────────────────────────────────────┐
│                Event-Driven Agent Visualizer                    │
├──────────────┬──────────────────────┬────────────────────────────┤
│   GRAFO      │   EVENTOS            │   ESTATÍSTICAS             │
│   DO MUNDO   │   E TIMELINE         │   E LOGS                   │
│              │                      │                            │
│  [Grafo      │  [Gráfico Timeline]  │  📊 Estatísticas           │
│   NetworkX]  │                      │  ├─ Total: 45              │
│              │  [Tabela Eventos]    │  ├─ Arrival: 12            │
│              │  ├─ 10.5s | arrival  │  ├─ Transit: 30            │
│  [Legenda]   │  ├─ 12.0s | transit  │  └─ Heap: 5                │
│  🟦 Warehouse│  └─ 15.0s | arrival  │                            │
│  🟩 Store    │                      │  🚚 Veículos               │
│  🟧 Supplier │                      │  ├─ vehicle1 | 42 | 85L    │
│  ⚪ Normal   │                      │  └─ vehicle2 | 58 | 92L    │
│  🔴 Tráfego  │                      │                            │
│              │                      │  📝 Logs                   │
│              │                      │  [12:30:15] ARRIVAL...     │
│              │                      │  [12:30:20] TRANSIT...     │
└──────────────┴──────────────────────┴────────────────────────────┘
```

## 🔧 Configuração

### Personalizar Cores

Editar em `gui_visualizer.py`:

```python
# Cores dos nós
node_colors = {
    'warehouse': '#3498db',  # Azul
    'store': '#2ecc71',      # Verde
    'supplier': '#e67e22',   # Laranja
    'normal': '#95a5a6'      # Cinzento
}

# Cores das arestas
edge_colors = {
    'traffic': '#e74c3c',    # Vermelho
    'normal': '#7f8c8d'      # Cinzento
}
```

### Ajustar Intervalo de Actualização

```python
# Alterar em EventSystemGUI.update_gui()
self.root.after(500, self.update_gui)  # 500ms (padrão)
```

### Limitar Histórico

```python
# Em EventSystemGUI.add_event_to_history()
if len(children) > 100:  # Manter últimos 100 eventos
    self.tree_events.delete(children[-1])
```

## 📊 Interpretação dos Dados

### Eventos de Arrival
- Indicam chegada de veículos a nós específicos
- Detalhes: Nome do veículo que chegou
- Tempo: Momento exacto da chegada

### Eventos de Transit
- Representam alterações nas condições de tráfego
- Detalhes: Número de arestas afectadas
- Tempo: Quando a alteração ocorre

### Eventos de UpdateSimulation
- Pedidos de nova simulação de tráfego
- Enviados automaticamente pelo Event Agent
- Mantêm dados de tráfego actualizados

### Estatísticas
- **Eventos na Heap**: Quantos eventos aguardam processamento
- **Transit Ativos**: Eventos de trânsito que ainda não foram processados
- **Tempo Simulado**: Avanço temporal da simulação (não tempo real)

## 🐛 Troubleshooting

### GUI não abre
```bash
# Verificar se Tkinter está instalado
python -c "import tkinter"

# Se erro, instalar:
# Windows: vem por padrão
# Linux: sudo apt-get install python3-tk
# macOS: brew install python-tk
```

### Grafo não aparece
- Verificar se matplotlib está instalado: `pip install matplotlib`
- Verificar se o mundo foi criado correctamente

### GUI congela
- A GUI executa numa thread separada
- Se a thread principal bloquear, a GUI pode congelar
- Solução: Garantir que asyncio não bloqueia

### Eventos não aparecem
- Verificar se callbacks foram injectados correctamente
- Verificar logs do sistema para erros
- Confirmar que Event Agent está a processar eventos

## 🎨 Personalização Avançada

### Adicionar Novos Painéis

```python
def create_custom_panel(self, parent):
    """Adiciona painel personalizado."""
    custom_frame = tk.Frame(parent, bg='#1e1e1e')
    custom_frame.pack(fill=tk.BOTH, expand=True)
    
    # Adicionar widgets personalizados
    # ...
```

### Novos Tipos de Gráficos

```python
# Adicionar gráfico de pizza
self.fig_pie = Figure(figsize=(4, 4))
self.ax_pie = self.fig_pie.add_subplot(111)

# Exemplo: Distribuição de eventos por tipo
labels = ['Arrival', 'Transit', 'Update']
sizes = [stats['arrival'], stats['transit'], stats['update']]
self.ax_pie.pie(sizes, labels=labels, autopct='%1.1f%%')
```

### Exportar Dados

```python
def export_stats_to_csv(self):
    """Exporta estatísticas para CSV."""
    import csv
    with open('stats.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'Total', 'Arrival', 'Transit'])
        # Escrever dados...
```

## 📖 Referências

- **Tkinter**: https://docs.python.org/3/library/tkinter.html
- **Matplotlib**: https://matplotlib.org/
- **Threading**: https://docs.python.org/3/library/threading.html
- **SPADE**: https://spade-mas.readthedocs.io/

## 🤝 Contribuir

Para adicionar novas funcionalidades à GUI:

1. Criar método em `EventSystemGUI`
2. Adicionar widget no método apropriado (`create_*_panel`)
3. Actualizar em `update_gui()` se necessário
4. Documentar mudanças neste README

## 📝 Notas

- A GUI é **thread-safe** usando `queue.Queue`
- Actualização a cada **500ms** (configurável)
- Histórico limitado para evitar uso excessivo de memória
- Todos os dados são **em tempo real** (não simulados)

## ⚠️ Limitações

- Performance pode degradar com muitos eventos simultâneos
- Grafo pode ficar confuso com mundos muito grandes (>15x15)
- Apenas monitoriza o que o Event Agent processa
- Não persiste dados entre execuções

## 🔮 Melhorias Futuras

- [ ] Filtros de eventos por tipo
- [ ] Zoom e pan no grafo
- [ ] Exportação de relatórios
- [ ] Replay de simulações
- [ ] Gráficos de performance
- [ ] Alertas visuais para eventos críticos
- [ ] Modo escuro/claro
- [ ] Configuração via interface

---

**Desenvolvido para Supply Chain Optimization with SPADE**
