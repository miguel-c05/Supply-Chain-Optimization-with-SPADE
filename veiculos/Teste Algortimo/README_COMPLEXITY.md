# Testes de Complexidade Temporal do Algoritmo A\*

Este diretório contém scripts para testar e analisar a complexidade temporal do algoritmo A\* de roteamento.

## Arquivos

- **`test_complexity.py`**: Script principal que executa os testes
- **`analyze_complexity.py`**: Script para análise dos resultados e geração de gráficos
- **`README_COMPLEXITY.md`**: Este arquivo

## Como Usar

### 1. Executar os Testes

Execute o script de testes (isso pode demorar alguns minutos):

```bash
python -m veiculos.test_complexity
```

Ou se estiver no diretório do projeto:

```bash
cd veiculos
python test_complexity.py
```

**Nota:** Este script executará 2000 testes (20 configurações × 100 repetições cada).
O progresso será mostrado na tela.

### 2. Analisar os Resultados

Após executar os testes, um arquivo CSV será gerado com nome no formato:
`complexity_test_results_YYYYMMDD_HHMMSS.csv`

Para analisar os resultados:

```bash
python -m veiculos.analyze_complexity
```

Ou especificando um arquivo CSV específico:

```bash
python -m veiculos.analyze_complexity complexity_test_results_20251111_153045.csv
```

## Configurações Testadas

Os testes cobrem 20 configurações diferentes organizadas em 3 categorias:

### Mundos Pequenos (5×5 = 25 nós)

1. **small_balanced**: Configuração balanceada
2. **small_many_orders**: Muitas ordens
3. **small_low_capacity**: Pouca capacidade do veículo
4. **small_low_fuel**: Pouco combustível

### Mundos Médios (7×7 = 49 nós)

5. **medium_balanced**: Configuração balanceada
6. **medium_many_warehouses**: Muitos warehouses, poucas lojas
7. **medium_many_stores**: Poucos warehouses, muitas lojas
8. **medium_high_capacity**: Muita capacidade
9. **medium_high_fuel**: Muito combustível
10. **medium_high_quantity**: Ordens com muita quantidade
11. **medium_low_quantity**: Ordens com pouca quantidade

### Mundos Grandes (10×10 = 100 nós)

12. **large_balanced**: Configuração balanceada
13. **large_many_orders**: Muitas ordens
14. **large_few_orders**: Poucas ordens
15. **large_many_warehouses**: Muitos warehouses, poucas lojas
16. **large_many_stores**: Poucos warehouses, muitas lojas
17. **large_low_capacity**: Pouca capacidade
18. **large_high_capacity**: Muita capacidade
19. **large_low_fuel**: Pouco combustível
20. **large_high_fuel**: Muito combustível

## Métricas Coletadas

Para cada teste, as seguintes métricas são coletadas:

### Métricas de Configuração

- Tamanho do mundo (width × height)
- Número de warehouses e stores
- Número de ordens
- Capacidade e combustível do veículo
- Range de quantidade por ordem

### Métricas de Desempenho

- **execution_time_seconds**: Tempo de execução do algoritmo
- **nodes_created**: Número total de nós criados na árvore de busca
- **cache_routes**: Número de rotas armazenadas em cache
- **success**: Se o algoritmo encontrou uma solução

### Métricas de Solução

- **path_length**: Comprimento do caminho encontrado
- **unique_trips**: Número de viagens únicas (transições entre locais diferentes)
- **total_cost**: Custo total da solução (tempo)
- **total_fuel_consumed**: Combustível total consumido
- **capacity_utilization_percent**: % de utilização da capacidade
- **fuel_utilization_percent**: % de utilização do combustível
- **cost_per_order**: Custo médio por ordem
- **fuel_per_order**: Combustível médio por ordem

## Saídas Geradas

### Arquivos CSV

1. **`complexity_test_results_*.csv`**: Dados brutos de todos os testes
2. **`complexity_test_results_*_summary.csv`**: Estatísticas agregadas por configuração

### Gráficos (requer matplotlib e seaborn)

1. **`*_time_by_config.png`**: Tempo médio de execução por configuração
2. **`*_nodes_vs_time.png`**: Scatter plot de nós criados vs tempo
3. **`*_time_by_world_size.png`**: Boxplot de tempo por tamanho de mundo
4. **`*_correlation_heatmap.png`**: Heatmap de correlação entre variáveis

## Análise dos Resultados

O script de análise fornece:

- Estatísticas descritivas por configuração
- Análise por tamanho de mundo (pequeno/médio/grande)
- Top 10 configurações mais rápidas/lentas
- Correlação entre variáveis e tempo de execução
- Resumo geral com médias e desvios padrão

## Requisitos

### Obrigatórios

- Python 3.7+
- pandas

### Opcionais (para gráficos)

- matplotlib
- seaborn

Instalar dependências:

```bash
pip install pandas matplotlib seaborn
```

## Interpretação dos Resultados

### Complexidade Temporal

- **Nós criados**: Indicador direto da complexidade do espaço de busca
- **Tempo de execução**: Tempo real para encontrar a solução
- **Cache hits**: Eficiência do cache de rotas Dijkstra

### Eficiência da Solução

- **Unique trips**: Menor é melhor (menos viagens desnecessárias)
- **Fuel/Cost per order**: Menor é melhor (mais eficiente)
- **Utilization %**: Maior é melhor (melhor aproveitamento dos recursos)

### Fatores que Afetam o Desempenho

1. **Número de ordens**: Cresce exponencialmente (2^n)
2. **Tamanho do mundo**: Afeta cálculos de rota
3. **Restrições**: Capacidade e combustível podem reduzir espaço de busca
4. **Distribuição**: Warehouses vs stores afeta número de opções

## Exemplo de Uso Completo

```bash
# 1. Executar testes (demora ~30-60 minutos)
python -m veiculos.test_complexity

# 2. Analisar resultados
python -m veiculos.analyze_complexity

# 3. Abrir CSV no Excel/LibreOffice para análise detalhada
# complexity_test_results_*.csv
```

## Notas

- Cada configuração é testada 100 vezes para obter médias confiáveis
- Seeds diferentes são usadas para cada repetição (seed base + run_number)
- O progresso é mostrado em tempo real
- Dados são salvos incrementalmente (não se perde progresso se interromper)
