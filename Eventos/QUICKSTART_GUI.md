# 🚀 Quick Start - GUI Visualizer

## Passos Rápidos

### 1. Testar Dependências
```bash
python Eventos/test_gui.py
```

Este comando:
- ✅ Verifica se todas as bibliotecas estão instaladas
- ✅ Abre uma janela de teste com gráfico
- ✅ Confirma que Tkinter está funcional

### 2. Executar Sistema Completo com GUI
```bash
python Eventos/event_agent.py
```

### 3. O Que Esperar

Ao executar, verá:

**Terminal:**
```
======================================================================
TESTE DO EVENT-DRIVEN AGENT COM WORLD AGENT E GUI
======================================================================

🌍 Criando o mundo...
✓ Mundo criado: 5x5
✓ Nós no grafo: 25
✓ Arestas no grafo: 40

🚚 Criando veículo...
⚙️ Criando Event Agent...
🌍 Criando World Agent...
📦 Criando Warehouse...
🖥️ Iniciando GUI Visualizer...
✓ GUI iniciada em thread separada

[SISTEMA] ✓ Sistema iniciado!
[SISTEMA] 🖥️ GUI disponível para visualização
```

**GUI (Janela Separada):**
```
┌─────────────────────────────────────────────────────────┐
│         Event-Driven Agent Visualizer                   │
├────────────┬──────────────────┬──────────────────────────┤
│   GRAFO    │   EVENTOS        │   STATS & LOGS           │
│   🗺️      │   📊             │   📈                     │
└────────────┴──────────────────┴──────────────────────────┘
```

### 4. Interagir com a GUI

A interface actualiza automaticamente a cada **500ms**:

- **Grafo**: Mostra posições de veículos (⭐) e tráfego (🔴)
- **Timeline**: Gráfico de barras com eventos recentes
- **Eventos**: Tabela com histórico completo
- **Stats**: Contadores em tempo real
- **Veículos**: Localização e combustível
- **Logs**: Console de mensagens do sistema

### 5. Parar a Simulação

Pressione `Ctrl+C` no terminal

## 🐛 Problemas Comuns

### Erro: "No module named 'tkinter'"

**Windows:**
- Tkinter vem com Python (reinstalar se necessário)

**Linux:**
```bash
sudo apt-get install python3-tk
```

**macOS:**
```bash
brew install python-tk
```

### Erro: "No module named 'matplotlib'"

```bash
pip install matplotlib
```

Ou usando conda:
```bash
conda install matplotlib
```



### GUI não aparece

1. Verificar que não há erros no terminal
2. Executar teste standalone: `python Eventos/test_gui.py`
3. Verificar se thread da GUI iniciou correctamente

### GUI congela

- A GUI executa numa thread separada
- Se o terminal mostrar erros, a thread pode ter crashado
- Reiniciar a simulação

## 📊 Interpretar os Dados

### Cores do Grafo
- 🟦 **Azul**: Warehouse (ponto de partida de encomendas)
- 🟩 **Verde**: Store (destino de entregas)
- 🟧 **Laranja**: Supplier (fornecedores)
- ⚪ **Cinzento**: Nós normais (estradas)
- 🔴 **Vermelho**: Tráfego (arestas congestionadas)
- ⭐ **Estrela Vermelha**: Veículo

### Tipos de Eventos
- **arrival**: Veículo chegou a um nó
- **transit**: Alteração nas condições de tráfego
- **updatesimulation**: Pedido de nova simulação

### Estatísticas
- **Total de Eventos**: Tudo o que aconteceu desde o início
- **Eventos Arrival**: Chegadas de veículos
- **Eventos Transit**: Alterações de tráfego
- **Eventos na Heap**: Pendentes de processamento
- **Transit Ativos**: Tráfego actual
- **Tempo Simulado**: Tempo virtual (não real)

## 🎯 Próximos Passos

1. ✅ Verificar que GUI funciona: `python Eventos/test_gui.py`
2. ✅ Executar sistema completo: `python Eventos/event_agent.py`
3. ✅ Observar eventos em tempo real na interface
4. ✅ Experimentar diferentes configurações no código
5. ✅ Consultar README_GUI.md para personalização

## 📖 Documentação Completa

- [README_GUI.md](README_GUI.md) - Documentação completa da GUI
- [event_agent.py](event_agent.py) - Código do sistema de eventos
- [gui_visualizer.py](gui_visualizer.py) - Código da interface gráfica

## 💡 Dicas

1. **Performance**: Para mundos grandes (>10x10), a GUI pode ficar lenta
2. **Zoom**: Não há zoom no grafo (limitação actual)
3. **Filtros**: Não há filtros de eventos (implementar se necessário)
4. **Persistência**: Dados não são salvos (implementar exportação se necessário)

---

**🎉 Pronto para começar!**

Execute: `python Eventos/test_gui.py`
