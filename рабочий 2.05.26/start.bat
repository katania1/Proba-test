@echo off
title VibeCoder Launcher
echo Запуск VibeCoder...

:: Активируем виртуальное окружение
call venv\Scripts\activate

:: Запускаем программу
python main.py

:: Ставим на паузу, если произойдет ошибка
pause