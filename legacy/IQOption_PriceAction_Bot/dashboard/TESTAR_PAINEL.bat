@echo off
title Enviar Dados de Teste ao Painel
cd /d "%~dp0"
echo ============================================================
echo 📊 ENVIANDO DADOS DE TESTE AO PAINEL
echo ============================================================
echo.
python update_example.py
echo.
echo ============================================================
echo ✅ Dados enviados! Verifique o painel no navegador.
echo ============================================================
echo.
pause
