@echo off
setlocal
cd /d "%~dp0\.."
streamlit run app.py
endlocal
