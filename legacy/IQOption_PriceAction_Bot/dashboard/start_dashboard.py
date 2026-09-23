#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de inicialização do painel IQ Option
Inicia o servidor Flask automaticamente em background
"""

import subprocess
import sys
import os
import time
from pathlib import Path

def main():
    print("=" * 60)
    print("🚀 INICIANDO PAINEL IQ OPTION")
    print("=" * 60)
    
    # Caminho do dashboard
    dashboard_dir = Path(__file__).resolve().parent
    app_path = dashboard_dir / "app.py"
    
    if not app_path.exists():
        print(f"❌ Erro: app.py não encontrado em {dashboard_dir}")
        return
    
    print(f"📂 Diretório: {dashboard_dir}")
    print(f"🔧 Iniciando servidor Flask...")
    
    # Inicia o servidor
    try:
        if sys.platform == "win32":
            # Windows: usa pythonw para não mostrar console
            subprocess.Popen(
                [sys.executable, str(app_path)],
                cwd=str(dashboard_dir),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            # Linux/Mac: usa nohup
            subprocess.Popen(
                [sys.executable, str(app_path)],
                cwd=str(dashboard_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        
        print("✅ Servidor iniciado com sucesso!")
        print("=" * 60)
        print("📊 Dashboard: http://127.0.0.1:5001")
        print("🔌 API Estado: http://127.0.0.1:5001/state")
        print("📈 API Histórico: http://127.0.0.1:5001/history")
        print("=" * 60)
        print("\n💡 O painel está rodando em background.")
        print("💡 Abra http://127.0.0.1:5001 no navegador.")
        print("\n⚠️  Para parar o servidor, feche o terminal ou use:")
        print("   taskkill /F /IM python.exe  (Windows)")
        print("   pkill -f app.py  (Linux/Mac)")
        print("=" * 60)
        
        # Aguarda 2 segundos para garantir que iniciou
        time.sleep(2)
        
        # Tenta abrir o navegador
        try:
            import webbrowser
            print("\n🌐 Abrindo navegador...")
            webbrowser.open("http://127.0.0.1:5001")
        except Exception:
            pass
        
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor: {e}")
        return

if __name__ == "__main__":
    main()
