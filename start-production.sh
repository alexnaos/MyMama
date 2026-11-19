#!/bin/bash
# Скрипт запуска в production режиме
# Использование: ./start-production.sh [start|stop|restart|status]

set -e

APP_NAME="mama-literary"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="$APP_DIR/logs"
PID_FILE="$APP_DIR/$APP_NAME.pid"
PORT=5001

# Создаем директории если их нет
mkdir -p "$LOG_DIR"

case "$1" in
    start)
        echo "Запуск $APP_NAME..."
        
        # Активация виртуального окружения если есть
        if [ -f "$VENV_DIR/bin/activate" ]; then
            source "$VENV_DIR/bin/activate"
        fi
        
        # Запуск приложения в фоне
        nohup python "$APP_DIR/app.py" production > "$LOG_DIR/app.log" 2>&1 &
        echo $! > "$PID_FILE"
        
        echo "Приложение запущено на порту $PORT"
        echo "Логи: $LOG_DIR/app.log"
        ;;
        
    stop)
        echo "Остановка $APP_NAME..."
        
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                kill "$PID"
                echo "Процесс $PID остановлен"
                rm -f "$PID_FILE"
            else
                echo "Процесс не найден"
                rm -f "$PID_FILE"
            fi
        else
            echo "PID файл не найден, останавливаем все python процессы..."
            pkill -f "python.*app.py" 2>/dev/null || true
        fi
        ;;
        
    restart)
        echo "Перезапуск $APP_NAME..."
        $0 stop
        sleep 2
        $0 start
        ;;
        
    status)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "$APP_NAME запущен (PID: $PID)"
                netstat -tlnp 2>/dev/null | grep ":$PORT" || echo "Порт $PORT не слушается"
            else
                echo "$APP_NAME не запущен (старый PID файл)"
                rm -f "$PID_FILE"
            fi
        else
            echo "$APP_NAME не запущен"
        fi
        ;;
        
    *)
        echo "Использование: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0