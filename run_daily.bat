@echo off
REM Lancé chaque matin par le Planificateur de tâches Windows
cd /d C:\Projects\Job-Radar
set PYTHONPATH=src
.venv\Scripts\python.exe -m jobradar.daily >> data\daily.log 2>&1
