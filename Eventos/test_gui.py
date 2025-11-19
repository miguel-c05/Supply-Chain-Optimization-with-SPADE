"""
Teste standalone da GUI Visualizer

Este script testa a GUI sem executar o sistema completo de agentes.
Útil para verificar se todas as dependências estão correctas e a interface funciona.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

# Adicionar diretório pai ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Testa se todas as bibliotecas necessárias estão disponíveis."""
    
    missing_libs = []
    
    try:
        import matplotlib
        print("✓ matplotlib instalado:", matplotlib.__version__)
    except ImportError:
        print("✗ matplotlib não encontrado")
        missing_libs.append("matplotlib")
    
    try:
        import tkinter
        print("✓ tkinter disponível")
    except ImportError:
        print("✗ tkinter não encontrado")
        missing_libs.append("tkinter")
    
    return missing_libs

def create_test_gui():
    """Cria uma GUI de teste simples."""
    
    root = tk.Tk()
    root.title("Teste GUI Visualizer")
    root.geometry("800x600")
    root.configure(bg='#2b2b2b')
    
    # Frame principal
    main_frame = tk.Frame(root, bg='#2b2b2b')
    main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    # Título
    title_label = tk.Label(
        main_frame,
        text="🖥️ Teste GUI Visualizer",
        font=('Arial', 20, 'bold'),
        bg='#2b2b2b',
        fg='#ffffff'
    )
    title_label.pack(pady=20)
    
    # Mensagem de sucesso
    success_label = tk.Label(
        main_frame,
        text="✓ Todas as bibliotecas estão correctamente instaladas!",
        font=('Arial', 14),
        bg='#2b2b2b',
        fg='#2ecc71'
    )
    success_label.pack(pady=10)
    
    # Informações
    info_frame = tk.Frame(main_frame, bg='#1e1e1e', relief=tk.RAISED, borderwidth=2)
    info_frame.pack(fill=tk.BOTH, expand=True, pady=20, padx=50)
    
    info_text = """
    A GUI Visualizer está pronta para uso!
    
    Funcionalidades disponíveis:
    
    📊 Visualização do Grafo do Mundo
    📈 Timeline de Eventos em Tempo Real
    📋 Histórico de Eventos
    📊 Estatísticas de Simulação
    🚚 Monitorização de Veículos
    📝 Logs do Sistema
    
    Para executar com o sistema completo:
    python Eventos/event_agent.py
    """
    
    info_label = tk.Label(
        info_frame,
        text=info_text,
        font=('Arial', 11),
        bg='#1e1e1e',
        fg='#ecf0f1',
        justify=tk.LEFT
    )
    info_label.pack(pady=20, padx=20)
    
    # Frame de teste matplotlib
    test_frame = tk.Frame(main_frame, bg='#1e1e1e', relief=tk.RAISED, borderwidth=2)
    test_frame.pack(fill=tk.BOTH, expand=True, pady=10, padx=50)
    
    test_title = tk.Label(
        test_frame,
        text="🧪 Teste de Matplotlib",
        font=('Arial', 12, 'bold'),
        bg='#1e1e1e',
        fg='#ffffff'
    )
    test_title.pack(pady=10)
    
    try:
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure
        import numpy as np
        
        # Criar figura de teste
        fig = Figure(figsize=(6, 3), facecolor='#1e1e1e')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#2b2b2b')
        
        # Plotar gráfico simples
        x = np.linspace(0, 10, 100)
        y = np.sin(x)
        ax.plot(x, y, color='#3498db', linewidth=2)
        ax.set_title('Gráfico de Teste', color='white')
        ax.tick_params(colors='white')
        ax.set_xlabel('X', color='white')
        ax.set_ylabel('Y', color='white')
        
        # Canvas
        canvas = FigureCanvasTkAgg(fig, master=test_frame)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        canvas.draw()
        
        test_status = tk.Label(
            test_frame,
            text="✓ Matplotlib funciona correctamente",
            font=('Arial', 10),
            bg='#1e1e1e',
            fg='#2ecc71'
        )
        test_status.pack(pady=5)
        
    except Exception as e:
        error_label = tk.Label(
            test_frame,
            text=f"✗ Erro ao testar matplotlib: {str(e)}",
            font=('Arial', 10),
            bg='#1e1e1e',
            fg='#e74c3c'
        )
        error_label.pack(pady=5)
    
    # Botão de fechar
    close_button = tk.Button(
        main_frame,
        text="Fechar",
        font=('Arial', 12),
        bg='#3498db',
        fg='white',
        command=root.quit,
        padx=20,
        pady=10
    )
    close_button.pack(pady=20)
    
    return root

def main():
    """Função principal de teste."""
    
    print("="*70)
    print("TESTE DA GUI VISUALIZER")
    print("="*70)
    print()
    
    print("Verificando bibliotecas...")
    missing_libs = test_imports()
    
    print()
    
    if missing_libs:
        print("="*70)
        print("✗ BIBLIOTECAS EM FALTA:")
        for lib in missing_libs:
            print(f"  - {lib}")
        print()
        print("Por favor, instale as bibliotecas em falta:")
        print("  pip install " + " ".join(missing_libs))
        print("="*70)
        return
    
    print("="*70)
    print("✓ TODAS AS BIBLIOTECAS ESTÃO INSTALADAS")
    print("="*70)
    print()
    print("A abrir GUI de teste...")
    print()
    
    try:
        root = create_test_gui()
        root.mainloop()
        print("\n✓ Teste concluído com sucesso!")
    except Exception as e:
        print(f"\n✗ Erro ao criar GUI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
