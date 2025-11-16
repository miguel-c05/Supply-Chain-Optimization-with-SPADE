"""
Agente de teste para enviar ordens aleatórias ao agente Veiculo.
Usado para debug e validação do comportamento do veículo.
Utiliza a classe World para criar um ambiente realista.
"""

import asyncio
import random
import json
import sys
import os

# Adicionar o diretório pai ao path para importar World
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from spade.agent import Agent
from spade.behaviour import PeriodicBehaviour, CyclicBehaviour, OneShotBehaviour
from spade.message import Message
from datetime import datetime
from world.world import World


class TestWarehouseAgent(Agent):
    """
    Agente simulador de warehouse que envia ordens aleatórias para testar o veículo.
    Usa World para obter localizações reais de warehouses e stores.
    """
    
    def __init__(self, jid: str, password: str, vehicle_jid: str, world: World):
        super().__init__(jid, password)
        self.vehicle_jid = vehicle_jid
        self.world = world
        self.graph = world.graph
        self.order_counter = 1
        self.pending_proposals = {}  # {orderid: order_info}
        
        # Produtos disponíveis para teste
        self.products = ["Electronics", "Food", "Clothing", "Books", "Toys", "Furniture"]
        
        # Identificar warehouses e stores no mapa
        self.warehouse_locations = []
        self.store_locations = []
        self._identify_locations()
    
    def _identify_locations(self):
        """Identifica warehouses e stores nos nós do grafo"""
        print(f"\n[{self.name}] Identificando warehouses e stores no mapa...")
        
        for node_id, node in self.graph.nodes.items():
            if hasattr(node, 'warehouse') and node.warehouse:
                self.warehouse_locations.append(node_id)
            if hasattr(node, 'store') and node.store:
                self.store_locations.append(node_id)
        
        print(f"[{self.name}] Warehouses encontrados: {self.warehouse_locations}")
        print(f"[{self.name}] Stores encontrados: {self.store_locations}")
        
        if not self.warehouse_locations or not self.store_locations:
            raise ValueError("ERRO: Não foram encontrados warehouses ou stores suficientes!")
    
    async def setup(self):
        print(f"\n[{self.name}] Warehouse de teste iniciado")
        print(f"[{self.name}] Alvo: {self.vehicle_jid}")
        print(f"[{self.name}] Mapa: {self.world.width}x{self.world.height}")
        
        # Comportamento para enviar ordens periodicamente
        send_behaviour = self.SendRandomOrdersBehaviour(period=5.0)  # A cada 5 segundos
        self.add_behaviour(send_behaviour)
        
        # Comportamento para receber propostas dos veículos
        receive_behaviour = self.ReceiveProposalsBehaviour()
        self.add_behaviour(receive_behaviour)
        
        # Comportamento para receber notificações de status
        status_behaviour = self.ReceiveStatusBehaviour()
        self.add_behaviour(status_behaviour)
    
    class SendRandomOrdersBehaviour(PeriodicBehaviour):
        """Envia ordens aleatórias para o veículo periodicamente"""
        
        async def run(self):
            # Gerar ordem aleatória usando localizações reais do mundo
            order = self.generate_random_order()
            
            # Enviar ordem ao veículo
            msg = Message(to=self.agent.vehicle_jid)
            msg.set_metadata("performative", "order-proposal")
            msg.body = json.dumps(order)
            
            await self.send(msg)
            
            # Guardar ordem pendente
            self.agent.pending_proposals[order["orderid"]] = {
                "order": order,
                "timestamp": datetime.now()
            }
            
            print(f"\n{'='*60}")
            print(f"[{self.agent.name}] ORDEM ENVIADA #{order['orderid']}")
            print(f"  Produto: {order['product']}")
            print(f"  Quantidade: {order['quantity']}")
            print(f"  De: Warehouse #{order['sender_location']} → Store #{order['receiver_location']}")
            print(f"  Ordens pendentes: {len(self.agent.pending_proposals)}")
            print(f"{'='*60}\n")
        
        def generate_random_order(self):
            """Gera uma ordem aleatória usando localizações reais de warehouses e stores"""
            orderid = self.agent.order_counter
            self.agent.order_counter += 1
            
            # Selecionar warehouse e store aleatoriamente das localizações reais
            warehouse = random.choice(self.agent.warehouse_locations)
            store = random.choice(self.agent.store_locations)
            quantity = random.randint(50, 400)
            
            # Calcular índices para nomes
            warehouse_idx = self.agent.warehouse_locations.index(warehouse) + 1
            store_idx = self.agent.store_locations.index(store) + 1
            
            return {
                "orderid": orderid,
                "product": random.choice(self.agent.products),
                "quantity": quantity,
                "sender": f"Warehouse{warehouse_idx}@localhost",
                "receiver": f"Store{store_idx}@localhost",
                "sender_location": warehouse,
                "receiver_location": store
            }
    
    class ReceiveProposalsBehaviour(CyclicBehaviour):
        """Recebe e processa propostas dos veículos"""
        
        async def run(self):
            msg = await self.receive(timeout=0.5)
            if msg:
                try:
                    # Verificar se é proposta de veículo
                    if msg.get_metadata("performative") == "vehicle-proposal":
                        data = json.loads(msg.body)
                        orderid = data.get("orderid")
                        can_fit = data.get("can_fit")
                        delivery_time = data.get("delivery_time")
                        vehicle_id = data.get("vehicle_id")
                        
                        print(f"\n{'*'*60}")
                        print(f"[{self.agent.name}] PROPOSTA RECEBIDA - Ordem #{orderid}")
                        print(f"  Veículo: {vehicle_id}")
                        print(f"  Can Fit: {can_fit}")
                        print(f"  Tempo Entrega: {delivery_time:.2f}")
                        print(f"{'*'*60}\n")
                        
                        # Decidir se aceita (80% de chance de aceitar para teste)
                        accept = random.random() < 0.8
                        
                        # Enviar confirmação
                        await self.send_confirmation(msg.sender, orderid, accept)
                        
                        # Remover da lista de pendentes
                        if orderid in self.agent.pending_proposals:
                            del self.agent.pending_proposals[orderid]
                
                except Exception as e:
                    print(f"[{self.agent.name}] Erro ao processar proposta: {e}")
        
        async def send_confirmation(self, vehicle_jid, orderid, confirmed):
            """Envia confirmação de aceitação/rejeição ao veículo"""
            msg = Message(to=vehicle_jid)
            msg.set_metadata("performative", "order-confirmation")
            
            data = {
                "orderid": orderid,
                "confirmed": confirmed
            }
            msg.body = json.dumps(data)
            await self.send(msg)
            
            status = "✓ ACEITE" if confirmed else "✗ REJEITADA"
            print(f"[{self.agent.name}] Confirmação enviada - Ordem #{orderid}: {status}")
    
    class ReceiveStatusBehaviour(CyclicBehaviour):
        """Recebe notificações de status das ordens"""
        
        async def run(self):
            msg = await self.receive(timeout=0.5)
            if msg:
                try:
                    msg_type = msg.get_metadata("type")
                    
                    if msg_type == "order-started":
                        data = json.loads(msg.body)
                        print(f"\n[{self.agent.name}] 🚚 ORDEM INICIADA #{data['orderid']}")
                        print(f"  Veículo: {data['vehicle_id']}")
                        print(f"  Localização: {data['location']}\n")
                    
                    elif msg_type == "order-completed":
                        data = json.loads(msg.body)
                        print(f"\n[{self.agent.name}] ✓ ORDEM COMPLETADA #{data['orderid']}")
                        print(f"  Veículo: {data['vehicle_id']}")
                        print(f"  Localização: {data['location']}\n")
                
                except Exception as e:
                    print(f"[{self.agent.name}] Erro ao processar status: {e}")


async def main():
    """
    Função principal para executar o teste.
    Cria um mundo com a classe World, um veículo e inicia o agente de teste.
    """
    from veiculos import Veiculo
    
    # Configurações dos agentes
    WAREHOUSE_JID = "warehouse_test@localhost"
    WAREHOUSE_PASSWORD = "warehouse123"
    VEHICLE_JID = "vehicle1@localhost"
    VEHICLE_PASSWORD = "vehicle123"
    
    print("="*70)
    print("AGENTE DE TESTE - WAREHOUSE SIMULATOR COM WORLD + VEÍCULO")
    print("="*70)
    
    # Criar o mundo
    print("\n🌍 Criando o mundo...")
    world = World(
        width=8,
        height=8,
        mode="different", 
        max_cost=4, 
        gas_stations=2, 
        warehouses=5,
        suppliers=2, 
        stores=6, 
        highway=True,
        traffic_probability=0.3,
        traffic_spread_probability=0.7,
        traffic_interval=3,
        untraffic_probability=0.4
    )
    
    print(f"✓ Mundo criado: {world.width}x{world.height}")
    print(f"✓ Nós no grafo: {len(world.graph.nodes)}")
    print(f"✓ Arestas no grafo: {len(world.graph.edges)}")
    
    # Identificar uma localização inicial para o veículo (primeiro store)
    store_locations = []
    for node_id, node in world.graph.nodes.items():
        if hasattr(node, 'store') and node.store:
            store_locations.append(node_id)
    
    if not store_locations:
        print("❌ ERRO: Não foram encontrados stores para localização inicial do veículo!")
        return
    
    initial_location = store_locations[0]
    
    print(f"\n🚚 Criando veículo...")
    print(f"   Localização inicial: {initial_location}")
    print(f"   Capacidade: 1000 kg")
    print(f"   Combustível máximo: 100 L")
    
    # Criar o veículo
    vehicle = Veiculo(
        jid=VEHICLE_JID,
        password=VEHICLE_PASSWORD,
        max_fuel=100,
        capacity=1000,
        max_orders=10,
        map=world.graph,
        weight=1500,  # peso do veículo em kg
        current_location=initial_location
    )
    
    print("\n" + "="*70)
    print(f"Warehouse JID: {WAREHOUSE_JID}")
    print(f"Vehicle JID: {VEHICLE_JID}")
    print("="*70)
    
    # Criar e iniciar o agente warehouse de teste
    try:
        warehouse = TestWarehouseAgent(
            jid=WAREHOUSE_JID,
            password=WAREHOUSE_PASSWORD,
            vehicle_jid=VEHICLE_JID,
            world=world
        )
    except ValueError as e:
        print(f"\n❌ ERRO: {e}")
        print("Certifique-se de que o mundo tem warehouses e stores suficientes!")
        return
    
    # Iniciar ambos os agentes
    print("\n🚀 Iniciando agentes...")
    await vehicle.start()
    print(f"✓ Veículo iniciado: {VEHICLE_JID}")
    
    await warehouse.start()
    print(f"✓ Warehouse de teste iniciado: {WAREHOUSE_JID}")
    
    print(f"\n[SISTEMA] ✓ Sistema de teste iniciado!")
    print(f"[SISTEMA] 📦 Enviando ordens aleatórias a cada 5 segundos...")
    print(f"[SISTEMA] 🗺️  Usando {len(warehouse.warehouse_locations)} warehouses e {len(warehouse.store_locations)} stores")
    print(f"[SISTEMA] 🚚 Veículo em localização {initial_location}")
    print(f"[SISTEMA] ⌨️  Pressione Ctrl+C para parar\n")
    
    try:
        # Manter os agentes rodando
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[SISTEMA] Parando agentes...")
    finally:
        await warehouse.stop()
        await vehicle.stop()
        print("[SISTEMA] ✓ Agentes parados!")


if __name__ == "__main__":
    """
    AGENTE DE TESTE PARA VEÍCULO - USANDO WORLD
    ============================================
    
    Este script cria um ambiente de teste realista usando a classe World
    e envia ordens aleatórias para testar o agente Veiculo.
    
    COMO EXECUTAR:
    --------------
    1. Certifique-se de que o servidor XMPP está rodando
    2. Inicie o agente Veiculo primeiro (com mapa compartilhado)
    3. Execute: python veiculos/test_vehicle_agent.py
    4. Observe as ordens sendo enviadas e processadas
    
    O QUE FAZ:
    ----------
    - Cria um mundo 8x8 com 5 warehouses e 6 stores
    - Identifica localizações reais de warehouses/stores no grafo
    - Envia ordens aleatórias a cada 5 segundos
    - Aceita automaticamente 80% das propostas dos veículos
    - Mostra notificações de início e conclusão de entregas
    
    CONFIGURAÇÕES (função main):
    ----------------------------
    - VEHICLE_JID: JID do veículo alvo (linha 221)
    - World parameters: width, height, warehouses, stores, etc. (linhas 227-241)
    - Período de envio: SendRandomOrdersBehaviour period (linha 74)
    - Taxa de aceitação: linha 162 (padrão: 80%)
    - Range de quantidades: linha 115 (50-800)
    
    WORLD PARAMETERS:
    -----------------
    - width/height: Dimensões do mapa (8x8)
    - warehouses: 5 (origem das ordens)
    - stores: 6 (destino das ordens)
    - gas_stations: 2 (reabastecimento)
    - highway: True (rotas mais rápidas)
    - traffic_probability: 0.3 (30% chance de trânsito)
    """
    
    asyncio.run(main())

