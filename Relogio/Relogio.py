"""
Módulo ClockAgent - Sistema de Relógio para Simulação Multi-Agente

Este módulo implementa um agente relógio (ClockAgent) baseado em SPADE que coordena
a simulação através de um sistema de ticks temporais. O relógio envia periodicamente
informações de sincronização para todos os agentes registrados no sistema.

Classes:
    ClockAgent: Agente principal que gerencia o sistema de ticks da simulação.
    
Exemplo de uso:
    ```python
    from Relogio import ClockAgent
    
    # Criar agente relógio
    clock = ClockAgent(
        jid="clock@localhost",
        password="password",
        tick_duration_seconds=1.0,
        veiculos_ids=["veiculo1@localhost", "veiculo2@localhost"]
    )
    
    # Iniciar agente
    await clock.start()
    
    # Iniciar simulação
    clock.start_simulation()
    ```

Autor: Supply Chain Optimization Project
Data: 2025
"""

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.message import Message
import asyncio
import json
from datetime import datetime


class ClockAgent(Agent):
    """
    Agente Relógio para coordenação temporal de simulações multi-agente.
    
    Este agente funciona como um coordenador central que envia periodicamente
    informações de tick (pulsos temporais) para todos os agentes registrados,
    permitindo sincronização e controle do tempo de simulação.
    
    Attributes:
        tick_duration (float): Duração em segundos que cada tick representa na simulação.
        current_tick (int): Número do tick atual da simulação.
        veiculos_ids (list): Lista de JIDs dos veículos a registrar automaticamente.
        registered_agents (set): Conjunto de JIDs dos agentes registrados.
        is_running (bool): Flag indicando se a simulação está ativa.
        
    Note:
        O agente deve ter `is_running` e `registered_agents` definidos antes de iniciar.
    """

    def __init__(self, jid, password, tick_duration_seconds: float = 1.0, veiculos_ids: list = []):
        """
        Inicializa o agente relógio.
        
        Args:
            jid (str): Jabber ID do agente (ex: "clock@localhost").
            password (str): Senha para autenticação XMPP.
            tick_duration_seconds (float, optional): Duração que cada tick representa 
                na simulação em segundos. Defaults to 1.0.
            veiculos_ids (list, optional): Lista de JIDs dos veículos a registrar 
                automaticamente no setup. Defaults to [].
                
        Example:
            ```python
            clock = ClockAgent(
                jid="clock@localhost",
                password="secret",
                tick_duration_seconds=2.0,
                veiculos_ids=["vehicle1@localhost"]
            )
            ```
        """
        super().__init__(jid, password)
        self.tick_duration = tick_duration_seconds          # Duração total de cada tick
        self.current_tick = 0                               # Tick atual
        self.veiculos_ids = veiculos_ids                    # IDs dos veículos

    class TickBroadcastBehaviour(PeriodicBehaviour):
        """
        Comportamento periódico para broadcast de informações de tick.
        
        Este comportamento é executado a cada 5 segundos e envia informações
        do tick atual para todos os agentes registrados no sistema de simulação.
        
        Attributes:
            period (float): Período de execução em segundos.
            
        Note:
            Apenas executa quando `self.agent.is_running` está ativo.
            Incrementa automaticamente `self.agent.current_tick` a cada execução.
        """
        
        async def run(self):
            """
            Executa o broadcast de tick para todos os agentes registrados.
            
            Este método é chamado periodicamente (a cada 5 segundos) e realiza:
            1. Verifica se a simulação está ativa
            2. Incrementa o contador de ticks
            3. Prepara mensagem com informações do tick
            4. Envia para todos os agentes registrados
            
            Formato da mensagem enviada:
                ```json
                {
                    "type": "tick",
                    "tick_number": 123,
                    "tick_duration": 1.0,
                    "timestamp": "2025-11-12T10:30:00.123456"
                }
                ```
            
            Returns:
                None: Retorna imediatamente se a simulação não estiver ativa.
            """
            # Só envia se a simulação estiver ativa
            if not self.agent.is_running:
                return
            
            # Incrementa o tick
            self.agent.current_tick += 1
            
            print(f"[{self.agent.name}] Tick {self.agent.current_tick} - Broadcasting to {len(self.agent.registered_agents)} agents")
            
            # Prepara a mensagem com informação do tick
            tick_info = {
                "type": "tick",
                "tick_number": self.agent.current_tick,
                "tick_duration": self.agent.tick_duration,
                "timestamp": datetime.now().isoformat()
            }
            
            # Envia para todos os agentes registrados
            for agent_jid in self.agent.presence.get_contacts().keys():
                msg = Message(to=agent_jid)
                msg.set_metadata("performative", "inform")
                msg.set_metadata("ontology", "clock")
                msg.body = json.dumps(tick_info)
                
                await self.send(msg)
            
            print(f"[{self.agent.name}] Tick {self.agent.current_tick} broadcast sent to all agents")

        async def on_start(self):
            """
            Callback executado quando o comportamento é iniciado.
            
            Imprime informação sobre o início do comportamento e o período
            configurado para os broadcasts.
            """
            print(f"[{self.agent.name}] TickBroadcastBehaviour iniciado - Broadcasting a cada {self.period} segundos")

    async def setup(self):
        """
        Configura e inicializa o agente relógio.
        
        Este método é chamado automaticamente quando o agente é iniciado.
        Realiza as seguintes configurações:
        1. Aprova automaticamente todas as subscrições de presença
        2. Adiciona o comportamento de broadcast de ticks (período de 5 segundos)
        3. Registra todos os veículos especificados em `veiculos_ids`
        
        Nota:
            Este método é assíncrono e executado pelo framework SPADE.
            Não deve ser chamado diretamente pelo utilizador.
        """
        self.presence.approve_all = True
        print(f"[{self.agent.name}] Relógio inicializado. Tick duration: {self.tick_duration}s")
        self.add_behaviour(self.TickBroadcastBehaviour(period=5))
        for veiculo_id in self.veiculos_ids:
            self.presence.subscribe(veiculo_id)
        