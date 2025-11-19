"""
Script de instalação de dependências para a GUI Visualizer

Este script verifica e instala todas as dependências necessárias
para executar a interface gráfica de visualização do sistema Event-Driven Agent.
"""

import subprocess
import sys

def check_and_install_package(package_name, import_name=None):
    """
    Verifica se um pacote está instalado e instala-o se necessário.
    
    Args:
        package_name (str): Nome do pacote no pip
        import_name (str, optional): Nome para import (se diferente do package_name)
    """
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        print(f"✓ {package_name} já está instalado")
        return True
    except ImportError:
        print(f"✗ {package_name} não encontrado. Instalando...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"✓ {package_name} instalado com sucesso")
            return True
        except subprocess.CalledProcessError:
            print(f"✗ Erro ao instalar {package_name}")
            return False

def main():
    """Verifica e instala todas as dependências."""
    
    print("="*70)
    print("INSTALAÇÃO DE DEPENDÊNCIAS - GUI VISUALIZER")
    print("="*70)
    print()
    
    required_packages = [
        ("matplotlib", "matplotlib"),
        ("tkinter", "tkinter"),  # Geralmente já vem com Python
    ]
    
    all_installed = True
    
    for package_name, import_name in required_packages:
        if not check_and_install_package(package_name, import_name):
            all_installed = False
    
    print()
    print("="*70)
    
    if all_installed:
        print("✓ TODAS AS DEPENDÊNCIAS ESTÃO INSTALADAS")
        print()
        print("Pode agora executar a GUI com:")
        print("  python Eventos/event_agent.py")
    else:
        print("✗ ALGUMAS DEPENDÊNCIAS FALHARAM NA INSTALAÇÃO")
        print()
        print("Por favor, instale manualmente:")
        print("  pip install matplotlib")
        print()
        print("Para Tkinter:")
        print("  Windows: Já incluído com Python")
        print("  Linux: sudo apt-get install python3-tk")
        print("  macOS: brew install python-tk")
    
    print("="*70)

if __name__ == "__main__":
    main()
