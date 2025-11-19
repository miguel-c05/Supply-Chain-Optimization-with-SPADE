"""
Interface Gráfica para Visualização em Tempo Real do Sistema Event-Driven Agent

Este módulo implementa uma GUI completa usando Tkinter e Matplotlib para monitorizar
e visualizar o fluxo de eventos, estatísticas de agentes e o grafo do mundo em tempo real.

Características:
    - Visualização do grafo do mundo com nós coloridos por tipo
    - Timeline de eventos em tempo real
    - Estatísticas de eventos processados
    - Monitorização de veículos (localização, combustível, carga)
    - Logs de sistema em tempo real
    - Gráficos de tráfego e eventos

Classes:
    EventSystemGUI: Interface principal que integra todos os componentes visuais
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import asyncio
import threading
from datetime import datetime
from typing import Dict, List, Any
import queue
import json


class EventSystemGUI:
    """
    Interface gráfica principal para visualização do sistema de eventos.
    
    Esta classe cria uma janela Tkinter com múltiplos painéis para monitorizar
    todos os aspectos do sistema: eventos, estatísticas, grafo e logs.
    
    Attributes:
        root (tk.Tk): Janela principal
        world: Instância do mundo com o grafo
        event_agent: Referência ao EventDrivenAgent
        vehicles (List): Lista de veículos monitorizados
        warehouses (List): Lista de warehouses monitorizados
        stores (List): Lista de stores monitorizadas
        suppliers (List): Lista de suppliers monitorizados
        
        # Estruturas de dados
        event_queue (queue.Queue): Fila de eventos para actualização thread-safe
        event_history (List): Histórico de eventos processados
        stats (Dict): Estatísticas em tempo real
        
        # Componentes visuais
        canvas_graph: Canvas do matplotlib para o grafo
        canvas_timeline: Canvas para timeline de eventos
        tree_events: TreeView de eventos
        text_logs: ScrolledText para logs
        labels_stats: Dicionário de labels de estatísticas
    """
    
    def __init__(self, root, world, event_agent, vehicles, warehouses, stores, suppliers):
        """
        Inicializa a interface gráfica.
        
        Args:
            root (tk.Tk): Janela raiz do Tkinter
            world: Objecto World com o grafo
            event_agent: EventDrivenAgent a monitorizar
            vehicles (List): Lista de agentes veículo
            warehouses (List): Lista de agentes warehouse
            stores (List): Lista de agentes store
            suppliers (List): Lista de agentes supplier
        """
        self.root = root
        self.world = world
        self.event_agent = event_agent
        self.vehicles = vehicles
        self.warehouses = warehouses
        self.stores = stores
        self.suppliers = suppliers
        
        # Estruturas de dados
        self.event_queue = queue.Queue()
        self.event_history = []
        self.stats = {
            'total_events': 0,
            'arrival_events': 0,
            'transit_events': 0,
            'update_simulation_events': 0,
            'events_in_heap': 0,
            'transit_events_active': 0,
            'simulation_time': 0.0,
            'last_update': datetime.now()
        }
        
        # Contadores para monitorização
        self.last_processed_count = 0
        self.last_event_count = 0
        self.monitored_events = set()
        
        # Configurar janela principal
        self.root.title("Event-Driven Agent Visualizer")
        self.root.geometry("1600x900")
        self.root.configure(bg='#2b2b2b')
        
        # Criar interface
        self.create_widgets()
        
        # Iniciar actualização periódica
        self.update_gui()
        
        # Injectar callbacks no event_agent
        self.inject_callbacks()
    
    def create_widgets(self):
        """Cria todos os widgets da interface."""
        
        # Frame principal com 3 colunas
        main_frame = tk.Frame(self.root, bg='#2b2b2b')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Coluna esquerda - Grafo do mundo
        left_frame = tk.Frame(main_frame, bg='#1e1e1e', relief=tk.RAISED, borderwidth=2)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
        
        # Coluna central - Eventos e timeline
        center_frame = tk.Frame(main_frame, bg='#1e1e1e', relief=tk.RAISED, borderwidth=2)
        center_frame.grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
        
        # Coluna direita - Estatísticas e logs
        right_frame = tk.Frame(main_frame, bg='#1e1e1e', relief=tk.RAISED, borderwidth=2)
        right_frame.grid(row=0, column=2, sticky='nsew', padx=5, pady=5)
        
        # Configurar pesos das colunas
        main_frame.columnconfigure(0, weight=2)
        main_frame.columnconfigure(1, weight=2)
        main_frame.columnconfigure(2, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # === COLUNA ESQUERDA - GRAFO ===
        self.create_graph_panel(left_frame)
        
        # === COLUNA CENTRAL - EVENTOS ===
        self.create_events_panel(center_frame)
        
        # === COLUNA DIREITA - ESTATÍSTICAS E LOGS ===
        self.create_stats_panel(right_frame)
    
    def create_graph_panel(self, parent):
        """Cria o painel do grafo do mundo."""
        
        # Título
        title_label = tk.Label(
            parent, 
            text="🗺️ Grafo do Mundo", 
            font=('Arial', 14, 'bold'),
            bg='#1e1e1e',
            fg='#ffffff'
        )
        title_label.pack(pady=10)
        
        # Frame para o grafo
        graph_frame = tk.Frame(parent, bg='#1e1e1e')
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Criar figura matplotlib
        self.fig_graph = Figure(figsize=(6, 6), facecolor='#1e1e1e')
        self.ax_graph = self.fig_graph.add_subplot(111)
        self.ax_graph.set_facecolor('#2b2b2b')
        
        # Canvas para o grafo
        self.canvas_graph = FigureCanvasTkAgg(self.fig_graph, master=graph_frame)
        self.canvas_graph.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Desenhar grafo inicial
        self.draw_graph()
        
        # Legenda
        legend_frame = tk.Frame(parent, bg='#1e1e1e')
        legend_frame.pack(pady=5)
        
        legends = [
            ("🟦 Warehouse", "#3498db"),
            ("🟩 Store", "#2ecc71"),
            ("🟧 Supplier", "#e67e22"),
            ("⚪ Normal", "#95a5a6"),
            ("🔴 Tráfego", "#e74c3c")
        ]
        
        for text, color in legends:
            lbl = tk.Label(
                legend_frame,
                text=text,
                font=('Arial', 9),
                bg='#1e1e1e',
                fg=color
            )
            lbl.pack(side=tk.LEFT, padx=5)
    
    def create_events_panel(self, parent):
        """Cria o painel de eventos e timeline."""
        
        # Título
        title_label = tk.Label(
            parent,
            text="📋 Eventos em Tempo Real",
            font=('Arial', 14, 'bold'),
            bg='#1e1e1e',
            fg='#ffffff'
        )
        title_label.pack(pady=10)
        
        # Timeline de eventos (gráfico)
        timeline_frame = tk.Frame(parent, bg='#1e1e1e')
        timeline_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.fig_timeline = Figure(figsize=(6, 3), facecolor='#1e1e1e')
        self.ax_timeline = self.fig_timeline.add_subplot(111)
        self.ax_timeline.set_facecolor('#2b2b2b')
        self.ax_timeline.set_xlabel('Tempo (s)', color='white')
        self.ax_timeline.set_ylabel('Eventos', color='white')
        self.ax_timeline.tick_params(colors='white')
        
        self.canvas_timeline = FigureCanvasTkAgg(self.fig_timeline, master=timeline_frame)
        self.canvas_timeline.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # TreeView para lista de eventos
        tree_frame = tk.Frame(parent, bg='#1e1e1e')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        tree_label = tk.Label(
            tree_frame,
            text="📜 Histórico de Eventos",
            font=('Arial', 12, 'bold'),
            bg='#1e1e1e',
            fg='#ffffff'
        )
        tree_label.pack(pady=5)
        
        # Scrollbar
        tree_scroll = tk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # TreeView
        self.tree_events = ttk.Treeview(
            tree_frame,
            columns=('Tempo', 'Tipo', 'Detalhes'),
            show='headings',
            yscrollcommand=tree_scroll.set,
            height=10
        )
        
        self.tree_events.heading('Tempo', text='Tempo (s)')
        self.tree_events.heading('Tipo', text='Tipo')
        self.tree_events.heading('Detalhes', text='Detalhes')
        
        self.tree_events.column('Tempo', width=80)
        self.tree_events.column('Tipo', width=120)
        self.tree_events.column('Detalhes', width=300)
        
        self.tree_events.pack(fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.tree_events.yview)
        
        # Estilo para TreeView
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', background='#2b2b2b', foreground='white', fieldbackground='#2b2b2b')
        style.configure('Treeview.Heading', background='#3498db', foreground='white')
    
    def create_stats_panel(self, parent):
        """Cria o painel de estatísticas e logs."""
        
        # Frame de estatísticas
        stats_frame = tk.Frame(parent, bg='#1e1e1e')
        stats_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        title_label = tk.Label(
            stats_frame,
            text="📊 Estatísticas",
            font=('Arial', 14, 'bold'),
            bg='#1e1e1e',
            fg='#ffffff'
        )
        title_label.pack(pady=10)
        
        # Labels de estatísticas
        self.labels_stats = {}
        
        stats_info = [
            ('total_events', '📦 Total de Eventos'),
            ('arrival_events', '🚚 Eventos Arrival'),
            ('transit_events', '🚦 Eventos Transit'),
            ('events_in_heap', '📋 Eventos na Heap'),
            ('transit_events_active', '⚡ Transit Ativos'),
            ('simulation_time', '⏱️ Tempo Simulado'),
        ]
        
        for key, label_text in stats_info:
            frame = tk.Frame(stats_frame, bg='#1e1e1e')
            frame.pack(fill=tk.X, pady=2)
            
            lbl_name = tk.Label(
                frame,
                text=label_text + ":",
                font=('Arial', 10),
                bg='#1e1e1e',
                fg='#95a5a6',
                anchor='w'
            )
            lbl_name.pack(side=tk.LEFT, padx=5)
            
            lbl_value = tk.Label(
                frame,
                text="0",
                font=('Arial', 10, 'bold'),
                bg='#1e1e1e',
                fg='#3498db',
                anchor='e'
            )
            lbl_value.pack(side=tk.RIGHT, padx=5)
            
            self.labels_stats[key] = lbl_value
        
        # Separador
        sep = tk.Frame(parent, height=2, bg='#3498db')
        sep.pack(fill=tk.X, padx=10, pady=10)
        
        # Frame de veículos
        vehicles_frame = tk.Frame(parent, bg='#1e1e1e')
        vehicles_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        vehicles_title = tk.Label(
            vehicles_frame,
            text="🚚 Veículos",
            font=('Arial', 12, 'bold'),
            bg='#1e1e1e',
            fg='#ffffff'
        )
        vehicles_title.pack(pady=5)
        
        # TreeView para veículos
        self.tree_vehicles = ttk.Treeview(
            vehicles_frame,
            columns=('Veículo', 'Localização', 'Combustível'),
            show='headings',
            height=4
        )
        
        self.tree_vehicles.heading('Veículo', text='Veículo')
        self.tree_vehicles.heading('Localização', text='Loc')
        self.tree_vehicles.heading('Combustível', text='Fuel')
        
        self.tree_vehicles.column('Veículo', width=100)
        self.tree_vehicles.column('Localização', width=60)
        self.tree_vehicles.column('Combustível', width=60)
        
        self.tree_vehicles.pack(fill=tk.X)
        
        # Separador
        sep2 = tk.Frame(parent, height=2, bg='#3498db')
        sep2.pack(fill=tk.X, padx=10, pady=10)
        
        # Frame de logs
        logs_frame = tk.Frame(parent, bg='#1e1e1e')
        logs_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        logs_title = tk.Label(
            logs_frame,
            text="📝 Logs do Sistema",
            font=('Arial', 12, 'bold'),
            bg='#1e1e1e',
            fg='#ffffff'
        )
        logs_title.pack(pady=5)
        
        # ScrolledText para logs
        self.text_logs = scrolledtext.ScrolledText(
            logs_frame,
            height=15,
            bg='#2b2b2b',
            fg='#ecf0f1',
            font=('Consolas', 9),
            wrap=tk.WORD
        )
        self.text_logs.pack(fill=tk.BOTH, expand=True)
    
    def draw_graph(self):
        """Desenha o grafo do mundo no canvas."""
        
        self.ax_graph.clear()
        
        # Criar layout do grafo
        G = self.world.graph
        pos = {}
        
        # Posições baseadas em grid - usar coordenadas do nó se disponíveis
        for node_id, node in G.nodes.items():
            if hasattr(node, 'x') and hasattr(node, 'y') and node.x is not None and node.y is not None:
                # Usar coordenadas reais do nó
                pos[node_id] = (node.x, -node.y)
            else:
                # Fallback para cálculo baseado em width
                x = node_id % self.world.width
                y = node_id // self.world.width
                pos[node_id] = (x, -y)
        
        # Cores dos nós baseadas no tipo
        node_colors = []
        node_ids = []
        for node_id, node in G.nodes.items():
            node_ids.append(node_id)
            if hasattr(node, 'warehouse') and node.warehouse:
                node_colors.append('#3498db')  # Azul para warehouse
            elif hasattr(node, 'store') and node.store:
                node_colors.append('#2ecc71')  # Verde para store
            elif hasattr(node, 'supplier') and node.supplier:
                node_colors.append('#e67e22')  # Laranja para supplier
            else:
                node_colors.append('#95a5a6')  # Cinzento para nós normais
        
        # Desenhar arestas primeiro (para ficarem atrás)
        for edge in G.edges:
            node1_id = edge.node1.id
            node2_id = edge.node2.id
            
            # Verificar se ambos os nós existem no pos
            if node1_id in pos and node2_id in pos:
                x1, y1 = pos[node1_id]
                x2, y2 = pos[node2_id]
                
                # Verificar se há tráfego (peso maior que inicial)
                initial_weight = edge.initial_weight if hasattr(edge, 'initial_weight') else edge.weight
                is_traffic = edge.weight > initial_weight * 1.5 if edge.weight and initial_weight else False
                
                if is_traffic:
                    color = '#e74c3c'  # Vermelho para tráfego
                    width = 2.5
                    alpha = 0.8
                else:
                    color = '#7f8c8d'  # Cinzento para normal
                    width = 1.0
                    alpha = 0.4
                
                self.ax_graph.plot([x1, x2], [y1, y2], color=color, linewidth=width, alpha=alpha, zorder=1)
        
        # Desenhar nós (círculos maiores para melhor visualização)
        for i, node_id in enumerate(node_ids):
            if node_id in pos:
                x, y = pos[node_id]
                self.ax_graph.scatter(x, y, c=node_colors[i], s=400, alpha=0.95, zorder=2, 
                                     edgecolors='white', linewidths=2)
        
        # Adicionar IDs dos nós acima de cada nó
        for node_id in node_ids:
            if node_id in pos:
                x, y = pos[node_id]
                self.ax_graph.text(x, y + 0.3, str(node_id), 
                                  color='white', 
                                  fontsize=8, 
                                  fontweight='bold',
                                  ha='center', 
                                  va='bottom',
                                  zorder=5,
                                  bbox=dict(boxstyle='round,pad=0.2', 
                                          facecolor='#1e1e1e', 
                                          edgecolor='#555555',
                                          alpha=0.9,
                                          linewidth=0.5))
        
        # Adicionar posições dos veículos (estrelas)
        vehicle_count = 0
        for vehicle in self.vehicles:
            # Verificar se o veículo tem a posição definida
            if hasattr(vehicle, 'current_location') and vehicle.current_location is not None:
                loc = vehicle.current_location
                if loc in pos:
                    x, y = pos[loc]
                    # Desenhar estrela vermelha
                    self.ax_graph.plot(x, y, 'r*', markersize=20, zorder=10, 
                                      markeredgecolor='white', markeredgewidth=1.5)
                    
                    # Adicionar nome do veículo abaixo da estrela
                    vehicle_name = str(vehicle.jid).split('@')[0] if hasattr(vehicle, 'jid') else f"V{vehicle_count}"
                    self.ax_graph.text(x, y - 0.35, vehicle_name, 
                                      color='white', 
                                      fontsize=7, 
                                      fontweight='bold',
                                      ha='center', 
                                      va='top',
                                      zorder=11,
                                      bbox=dict(boxstyle='round,pad=0.2', 
                                              facecolor='#e74c3c', 
                                              edgecolor='white',
                                              alpha=0.9,
                                              linewidth=1))
                    vehicle_count += 1
        
        # Configurar limites do eixo para garantir grid quadrado com margem
        margin = 0.8
        self.ax_graph.set_xlim(-margin, self.world.width - 1 + margin)
        self.ax_graph.set_ylim(-(self.world.height - 1 + margin), margin)
        self.ax_graph.set_aspect('equal', adjustable='box')
        
        # Grid de fundo sutil para ajudar visualização
        self.ax_graph.grid(True, alpha=0.15, linestyle='--', linewidth=0.5, color='white')
        
        self.ax_graph.set_title('Mundo da Simulação', color='white', fontsize=12, pad=10)
        self.ax_graph.set_facecolor('#2b2b2b')
        
        # Remover eixos mas manter o grid
        self.ax_graph.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
        for spine in self.ax_graph.spines.values():
            spine.set_visible(False)
        
        self.canvas_graph.draw()
    
    def update_timeline(self):
        """Actualiza o gráfico de timeline de eventos."""
        
        self.ax_timeline.clear()
        
        # Obter tempo atual de simulação
        current_sim_time = 0
        if hasattr(self.event_agent, 'time_simulated'):
            current_sim_time = self.event_agent.time_simulated
        
        if len(self.event_history) > 0:
            # Agrupar eventos por tempo
            times = []
            arrival_counts = []
            transit_counts = []
            
            time_buckets = {}
            for event in self.event_history[-50:]:  # Últimos 50 eventos
                time = event['time']
                etype = event['type']
                
                # Filtrar apenas eventos com tempo <= tempo atual de simulação
                if time <= current_sim_time:
                    if time not in time_buckets:
                        time_buckets[time] = {'arrival': 0, 'transit': 0}
                    
                    if etype == 'arrival':
                        time_buckets[time]['arrival'] += 1
                    elif etype in ['transit', 'Transit']:
                        time_buckets[time]['transit'] += 1
            
            # Ordenar por tempo
            sorted_times = sorted(time_buckets.keys())
            
            for t in sorted_times:
                times.append(t)
                arrival_counts.append(time_buckets[t]['arrival'])
                transit_counts.append(time_buckets[t]['transit'])
            
            if times:
                # Plotar barras empilhadas
                self.ax_timeline.bar(times, arrival_counts, label='Arrival', color='#3498db', alpha=0.8)
                self.ax_timeline.bar(times, transit_counts, bottom=arrival_counts, 
                                    label='Transit', color='#e67e22', alpha=0.8)
                
                # Adicionar linha vertical para tempo atual
                if current_sim_time > 0:
                    self.ax_timeline.axvline(x=current_sim_time, color='#e74c3c', 
                                            linestyle='--', linewidth=2, alpha=0.7,
                                            label=f'Tempo Atual ({current_sim_time:.1f}s)')
                
                self.ax_timeline.legend(loc='upper left', facecolor='#2b2b2b', 
                                       edgecolor='white', labelcolor='white')
        
        self.ax_timeline.set_xlabel('Tempo (s)', color='white')
        self.ax_timeline.set_ylabel('Nº Eventos', color='white')
        self.ax_timeline.set_title('Timeline de Eventos', color='white', fontsize=10)
        self.ax_timeline.tick_params(colors='white')
        self.ax_timeline.set_facecolor('#2b2b2b')
        
        self.canvas_timeline.draw()
    
    def update_stats(self):
        """Actualiza as estatísticas na interface."""
        
        # Obter tempo simulado acumulado do event_agent
        if hasattr(self.event_agent, 'time_simulated'):
            simulation_time = self.event_agent.time_simulated
        else:
            simulation_time = self.stats['simulation_time']
        
        # Actualizar labels
        self.labels_stats['total_events'].config(text=str(self.stats['total_events']))
        self.labels_stats['arrival_events'].config(text=str(self.stats['arrival_events']))
        self.labels_stats['transit_events'].config(text=str(self.stats['transit_events']))
        self.labels_stats['events_in_heap'].config(text=str(len(self.event_agent.event_heap)))
        self.labels_stats['transit_events_active'].config(text=str(len(self.event_agent.transit_events)))
        self.labels_stats['simulation_time'].config(text=f"{simulation_time:.1f}s")
        
        # Actualizar veículos
        self.tree_vehicles.delete(*self.tree_vehicles.get_children())
        
        for vehicle in self.vehicles:
            vehicle_name = str(vehicle.jid).split('@')[0] if hasattr(vehicle, 'jid') else 'Unknown'
            
            # Obter localização actual
            if hasattr(vehicle, 'current_location') and vehicle.current_location is not None:
                location = f"Nó {vehicle.current_location}"
            else:
                location = 'N/A'
            
            # Calcular combustível consumido
            if hasattr(vehicle, 'max_fuel') and hasattr(vehicle, 'current_fuel'):
                fuel_consumed = vehicle.max_fuel - vehicle.current_fuel
                fuel_str = f"{fuel_consumed:.1f}L"
            else:
                fuel_str = 'N/A'
            
            self.tree_vehicles.insert('', tk.END, values=(
                vehicle_name,
                location,
                fuel_str
            ))
    
    def add_event_to_history(self, event_data):
        """
        Adiciona evento ao histórico e actualiza a interface.
        
        Args:
            event_data (Dict): Dicionário com informações do evento
        """
        self.event_history.append(event_data)
        
        # Actualizar estatísticas
        self.stats['total_events'] += 1
        
        if event_data['type'] == 'arrival':
            self.stats['arrival_events'] += 1
        elif event_data['type'] in ['transit', 'Transit']:
            self.stats['transit_events'] += 1
        elif event_data['type'] == 'updatesimulation':
            self.stats['update_simulation_events'] += 1
        
        self.stats['simulation_time'] = event_data.get('time', 0)
        
        # Obter tempo atual de simulação
        current_sim_time = 0
        if hasattr(self.event_agent, 'time_simulated'):
            current_sim_time = self.event_agent.time_simulated
        
        # Adicionar ao TreeView apenas se tempo <= tempo atual (manter apenas últimos 100)
        event_time = event_data['time']
        if event_time <= current_sim_time or current_sim_time == 0:
            details = event_data.get('details', '')
            self.tree_events.insert('', 0, values=(
                f"{event_data['time']:.2f}",
                event_data['type'],
                details
            ))
            
            # Limitar tamanho do TreeView
            children = self.tree_events.get_children()
            if len(children) > 100:
                self.tree_events.delete(children[-1])
        
        # Adicionar log
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] {event_data['type'].upper()} @ {event_data['time']:.2f}s - {details}\n"
        self.text_logs.insert(tk.END, log_msg)
        self.text_logs.see(tk.END)
        
        # Limitar tamanho dos logs
        if int(self.text_logs.index('end-1c').split('.')[0]) > 500:
            self.text_logs.delete('1.0', '100.0')
    
    def update_gui(self):
        """Actualização periódica da GUI."""
        
        # Debug: Verificar posições dos veículos
        for vehicle in self.vehicles:
            if hasattr(vehicle, 'current_location'):
                vehicle_name = str(vehicle.jid).split('@')[0] if hasattr(vehicle, 'jid') else 'Unknown'
                # Só fazer log se a posição mudou (evitar spam)
                if not hasattr(self, '_last_vehicle_positions'):
                    self._last_vehicle_positions = {}
                
                current_pos = vehicle.current_location
                if vehicle_name not in self._last_vehicle_positions or self._last_vehicle_positions[vehicle_name] != current_pos:
                    self._last_vehicle_positions[vehicle_name] = current_pos
                    # Log silencioso - apenas actualiza internamente
        
        # Monitorizar estruturas de dados do event_agent directamente
        try:
            # Detectar novos eventos processados
            if hasattr(self.event_agent, 'processed_count'):
                if self.event_agent.processed_count > self.last_processed_count:
                    self.last_processed_count = self.event_agent.processed_count
                    self.add_log(f"✓ {self.event_agent.processed_count} eventos processados no total")
            
            # Monitorizar eventos na heap
            if hasattr(self.event_agent, 'event_heap'):
                for event in self.event_agent.event_heap:
                    event_id = id(event)
                    if event_id not in self.monitored_events:
                        self.monitored_events.add(event_id)
                        event_data = {
                            'time': event.time,
                            'type': event.event_type,
                            'details': self.format_event_details(event),
                            'sender': event.sender if event.sender else 'system'
                        }
                        self.add_event_to_history(event_data)
            
            # Monitorizar eventos de arrival
            if hasattr(self.event_agent, 'arrival_events'):
                for event in self.event_agent.arrival_events:
                    event_id = id(event)
                    if event_id not in self.monitored_events:
                        self.monitored_events.add(event_id)
                        event_data = {
                            'time': event.time,
                            'type': event.event_type,
                            'details': self.format_event_details(event),
                            'sender': event.sender if event.sender else 'system'
                        }
                        self.add_event_to_history(event_data)
            
            # Monitorizar eventos de transit
            if hasattr(self.event_agent, 'transit_events'):
                for event in self.event_agent.transit_events:
                    event_id = id(event)
                    if event_id not in self.monitored_events:
                        self.monitored_events.add(event_id)
                        event_data = {
                            'time': event.time,
                            'type': event.event_type,
                            'details': self.format_event_details(event),
                            'sender': event.sender if event.sender else 'world_agent'
                        }
                        self.add_event_to_history(event_data)
        
        except Exception as e:
            # Não interromper GUI por erros de monitorização
            pass
        
        # Processar eventos da queue (se houver callbacks injectados)
        try:
            while not self.event_queue.empty():
                event_data = self.event_queue.get_nowait()
                self.add_event_to_history(event_data)
        except queue.Empty:
            pass
        
        # Limpar eventos futuros da tabela TreeView
        self.clean_future_events()
        
        # Actualizar componentes
        self.update_stats()
        self.update_timeline()
        self.draw_graph()
        
        # Agendar próxima actualização (500ms)
        self.root.after(500, self.update_gui)
    
    def clean_future_events(self):
        """Remove eventos com tempo futuro (maior que tempo atual) da tabela."""
        
        # Obter tempo atual de simulação
        current_sim_time = 0
        if hasattr(self.event_agent, 'time_simulated'):
            current_sim_time = self.event_agent.time_simulated
        
        if current_sim_time == 0:
            return  # Não limpar se ainda não começou
        
        # Iterar pelos items da TreeView e remover os que têm tempo futuro
        items_to_delete = []
        for item in self.tree_events.get_children():
            values = self.tree_events.item(item, 'values')
            if values:
                try:
                    event_time = float(values[0])  # Primeira coluna é o tempo
                    if event_time > current_sim_time:
                        items_to_delete.append(item)
                except (ValueError, IndexError):
                    pass
        
        # Deletar items identificados
        for item in items_to_delete:
            self.tree_events.delete(item)
    
    def inject_callbacks(self):
        """
        Injeta callbacks no EventDrivenAgent para capturar eventos.
        
        Estratégia: Monitorizar directamente as estruturas de dados do event_agent
        em vez de modificar métodos (mais robusto e thread-safe).
        """
        
        # Guardar contadores anteriores para detectar mudanças
        self.last_processed_count = 0
        self.last_event_count = 0
        self.monitored_events = set()
        self._last_vehicle_positions = {}
        
        # Log inicial
        self.add_log("✅ Sistema iniciado e monitorização activa")
        self.add_log(f"📊 Veículos registados: {len(self.vehicles)}")
        self.add_log(f"📦 Warehouses registadas: {len(self.warehouses)}")
        self.add_log(f"🏪 Stores registadas: {len(self.stores)}")
        
        # Log das posições iniciais dos veículos
        for vehicle in self.vehicles:
            if hasattr(vehicle, 'current_location'):
                vehicle_name = str(vehicle.jid).split('@')[0] if hasattr(vehicle, 'jid') else 'Unknown'
                self.add_log(f"🚚 {vehicle_name} - Posição inicial: Nó {vehicle.current_location}")
    
    def format_event_details(self, event):
        """Formata os detalhes de um evento para exibição."""
        
        if event.event_type == 'arrival':
            vehicle = event.sender.split('@')[0] if event.sender else 'Unknown'
            # Extrair nó de chegada dos dados do evento
            # O veículo envia 'current_location' no campo data
            location = event.data.get('current_location') or event.data.get('location', 'desconhecido') if event.data else 'desconhecido'
            return f"Veículo {vehicle} chegou ao nó {location}"
        
        elif event.event_type in ['transit', 'Transit']:
            if event.data:
                edges = event.data.get('edges', [])
                if edges:
                    # Mostrar detalhes da primeira edge afetada
                    if len(edges) == 1:
                        edge = edges[0]
                        node1 = edge.get('node1', '?')
                        node2 = edge.get('node2', '?')
                        weight = edge.get('weight', 0)
                        return f"Trânsito na edge ({node1}→{node2}), peso: {weight:.1f}"
                    else:
                        # Múltiplas edges
                        edge_list = ', '.join([f"({e.get('node1', '?')}→{e.get('node2', '?')})" for e in edges[:3]])
                        more = f" +{len(edges)-3}" if len(edges) > 3 else ""
                        return f"Trânsito em {len(edges)} edges: {edge_list}{more}"
                return "Alteração de tráfego"
            return "Evento de trânsito"
        
        elif event.event_type == 'updatesimulation':
            return "Solicitação de nova simulação"
        
        return str(event.data) if event.data else "Sem detalhes"
    
    def add_log(self, message):
        """Adiciona mensagem aos logs."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] {message}\n"
        self.text_logs.insert(tk.END, log_msg)
        self.text_logs.see(tk.END)


def run_gui_in_thread(world, event_agent, vehicles, warehouses, stores, suppliers):
    """
    Executa a GUI numa thread separada.
    
    Args:
        world: Instância do mundo
        event_agent: EventDrivenAgent
        vehicles: Lista de veículos
        warehouses: Lista de warehouses
        stores: Lista de stores
        suppliers: Lista de suppliers
    """
    root = tk.Tk()
    gui = EventSystemGUI(root, world, event_agent, vehicles, warehouses, stores, suppliers)
    root.mainloop()


def start_gui(world, event_agent, vehicles, warehouses, stores, suppliers):
    """
    Inicia a GUI numa thread separada para não bloquear o asyncio.
    
    Args:
        world: Instância do mundo
        event_agent: EventDrivenAgent
        vehicles: Lista de veículos
        warehouses: Lista de warehouses
        stores: Lista de stores
        suppliers: Lista de suppliers
    
    Returns:
        threading.Thread: Thread da GUI
    """
    gui_thread = threading.Thread(
        target=run_gui_in_thread,
        args=(world, event_agent, vehicles, warehouses, stores, suppliers),
        daemon=True
    )
    gui_thread.start()
    return gui_thread
