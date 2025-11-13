"""
Script para análise dos resultados dos testes de complexidade
Gera estatísticas agregadas e visualizações
"""

import pandas as pd
import sys
import os
from pathlib import Path


def analyze_results(csv_file):
    """
    Analisa os resultados do CSV e gera estatísticas
    """
    print(f"Carregando dados de: {csv_file}")
    df = pd.read_csv(csv_file)
    
    print(f"\nTotal de testes: {len(df)}")
    print(f"Testes bem-sucedidos: {df['success'].sum()} ({(df['success'].sum()/len(df))*100:.1f}%)")
    print(f"Testes falhados: {(~df['success']).sum()} ({((~df['success']).sum()/len(df))*100:.1f}%)")
    
    # Estatísticas por configuração
    print("\n" + "="*100)
    print("ESTATÍSTICAS POR CONFIGURAÇÃO")
    print("="*100)
    
    grouped = df.groupby('config_name').agg({
        'success': ['count', 'sum', 'mean'],
        'execution_time_seconds': ['mean', 'std', 'min', 'max'],
        'nodes_created': ['mean', 'std', 'min', 'max'],
        'cache_routes': ['mean', 'std'],
        'total_fuel_consumed': ['mean', 'std'],
        'unique_trips': ['mean', 'std'],
        'capacity_utilization_percent': ['mean', 'std'],
        'fuel_utilization_percent': ['mean', 'std']
    }).round(2)
    
    print(grouped)
    
    # Salvar estatísticas agregadas
    output_file = csv_file.replace('.csv', '_summary.csv')
    grouped.to_csv(output_file)
    print(f"\nEstatísticas agregadas salvas em: {output_file}")
    
    # Análise por tamanho de mundo
    print("\n" + "="*100)
    print("ANÁLISE POR TAMANHO DE MUNDO")
    print("="*100)
    
    df['world_category'] = df['config_name'].apply(
        lambda x: 'small' if x.startswith('small') 
        else ('medium' if x.startswith('medium') else 'large')
    )
    
    world_stats = df.groupby('world_category').agg({
        'execution_time_seconds': ['mean', 'std'],
        'nodes_created': ['mean', 'std'],
        'success': 'mean'
    }).round(2)
    
    print(world_stats)
    
    # Top 10 configurações mais rápidas
    print("\n" + "="*100)
    print("TOP 10 CONFIGURAÇÕES MAIS RÁPIDAS (média)")
    print("="*100)
    
    fastest = df.groupby('config_name')['execution_time_seconds'].mean().sort_values().head(10)
    print(fastest)
    
    # Top 10 configurações mais lentas
    print("\n" + "="*100)
    print("TOP 10 CONFIGURAÇÕES MAIS LENTAS (média)")
    print("="*100)
    
    slowest = df.groupby('config_name')['execution_time_seconds'].mean().sort_values(ascending=False).head(10)
    print(slowest)
    
    # Análise de correlação
    print("\n" + "="*100)
    print("CORRELAÇÃO ENTRE VARIÁVEIS E TEMPO DE EXECUÇÃO")
    print("="*100)
    
    correlations = df[[
        'execution_time_seconds', 'world_size', 'num_orders', 'num_warehouses',
        'num_stores', 'vehicle_capacity', 'vehicle_max_fuel', 'nodes_created',
        'total_quantity'
    ]].corr()['execution_time_seconds'].sort_values(ascending=False)
    
    print(correlations)
    
    # Relatório final
    print("\n" + "="*100)
    print("RESUMO GERAL")
    print("="*100)
    print(f"Tempo médio de execução: {df['execution_time_seconds'].mean():.4f}s ± {df['execution_time_seconds'].std():.4f}s")
    print(f"Nós criados (média): {df['nodes_created'].mean():.0f} ± {df['nodes_created'].std():.0f}")
    print(f"Rotas em cache (média): {df['cache_routes'].mean():.0f} ± {df['cache_routes'].std():.0f}")
    print(f"Combustível consumido (média): {df['total_fuel_consumed'].mean():.2f}L ± {df['total_fuel_consumed'].std():.2f}L")
    print(f"Viagens únicas (média): {df['unique_trips'].mean():.1f} ± {df['unique_trips'].std():.1f}")
    print(f"Utilização de capacidade (média): {df['capacity_utilization_percent'].mean():.1f}% ± {df['capacity_utilization_percent'].std():.1f}%")
    print(f"Utilização de combustível (média): {df['fuel_utilization_percent'].mean():.1f}% ± {df['fuel_utilization_percent'].std():.1f}%")
    
    return df


def main():
    """
    Função principal
    """
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        # Procurar pelo arquivo CSV mais recente
        csv_files = list(Path('.').glob('complexity_test_results_*.csv'))
        if not csv_files:
            print("Erro: Nenhum arquivo de resultados encontrado!")
            print("Execute primeiro: python test_complexity.py")
            return
        
        csv_file = str(max(csv_files, key=os.path.getctime))
        print(f"Usando arquivo mais recente: {csv_file}")
    
    try:
        df = analyze_results(csv_file)
        
        # Tentar gerar gráficos se matplotlib estiver disponível
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            
            print("\nGerando visualizações...")
            
            # Configurar estilo
            sns.set_style("whitegrid")
            
            # Gráfico 1: Tempo de execução por configuração
            plt.figure(figsize=(14, 6))
            df.groupby('config_name')['execution_time_seconds'].mean().sort_values().plot(kind='barh')
            plt.xlabel('Tempo médio de execução (segundos)')
            plt.title('Tempo médio de execução por configuração')
            plt.tight_layout()
            plt.savefig(csv_file.replace('.csv', '_time_by_config.png'), dpi=300)
            print(f"Gráfico salvo: {csv_file.replace('.csv', '_time_by_config.png')}")
            plt.close()
            
            # Gráfico 2: Nós criados vs Tempo de execução
            plt.figure(figsize=(10, 6))
            plt.scatter(df['nodes_created'], df['execution_time_seconds'], alpha=0.5)
            plt.xlabel('Nós criados')
            plt.ylabel('Tempo de execução (segundos)')
            plt.title('Relação entre nós criados e tempo de execução')
            plt.tight_layout()
            plt.savefig(csv_file.replace('.csv', '_nodes_vs_time.png'), dpi=300)
            print(f"Gráfico salvo: {csv_file.replace('.csv', '_nodes_vs_time.png')}")
            plt.close()
            
            # Gráfico 3: Boxplot de tempo por categoria de mundo
            df['world_category'] = df['config_name'].apply(
                lambda x: 'Small' if x.startswith('small') 
                else ('Medium' if x.startswith('medium') else 'Large')
            )
            plt.figure(figsize=(10, 6))
            df.boxplot(column='execution_time_seconds', by='world_category')
            plt.ylabel('Tempo de execução (segundos)')
            plt.xlabel('Categoria de mundo')
            plt.title('Distribuição de tempo de execução por tamanho de mundo')
            plt.suptitle('')  # Remove título padrão do pandas
            plt.tight_layout()
            plt.savefig(csv_file.replace('.csv', '_time_by_world_size.png'), dpi=300)
            print(f"Gráfico salvo: {csv_file.replace('.csv', '_time_by_world_size.png')}")
            plt.close()
            
            # Gráfico 4: Heatmap de correlação
            plt.figure(figsize=(12, 10))
            corr_matrix = df[[
                'execution_time_seconds', 'world_size', 'num_orders', 'num_warehouses',
                'num_stores', 'vehicle_capacity', 'vehicle_max_fuel', 'nodes_created',
                'total_quantity', 'capacity_utilization_percent', 'fuel_utilization_percent'
            ]].corr()
            sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='coolwarm', center=0)
            plt.title('Matriz de correlação entre variáveis')
            plt.tight_layout()
            plt.savefig(csv_file.replace('.csv', '_correlation_heatmap.png'), dpi=300)
            print(f"Gráfico salvo: {csv_file.replace('.csv', '_correlation_heatmap.png')}")
            plt.close()
            
            print("\nVisualizações geradas com sucesso!")
            
        except ImportError:
            print("\nNota: matplotlib/seaborn não disponível. Pulando geração de gráficos.")
            print("Para gerar gráficos, instale: pip install matplotlib seaborn")
    
    except Exception as e:
        print(f"Erro ao analisar resultados: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
