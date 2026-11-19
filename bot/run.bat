@echo off
cd /d "%~dp0"
if exist D:\tools\tg\chat_id.txt set /p ADMIN_ID=<D:\tools\tg\chat_id.txt
python bot.py
pause
