#!/bin/bash

# Скрипт для деплоя логистического бота на удаленный сервер
# Автор: Claude Code
# Версия: 1.0

set -e  # Остановить выполнение при первой ошибке

# Конфигурация
PROJECT_NAME="logistics-bot"
APP_DIR="/opt/logistics-bot"
COMPOSE_PROJECT_NAME="logistics-bot"
BACKUP_DIR="/opt/logistics-bot/backups"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для логирования
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Функция для проверки требований
check_requirements() {
    log "Проверка системных требований..."
    
    # Проверка Docker
    if ! command -v docker &> /dev/null; then
        error "Docker не установлен. Установите Docker и попробуйте снова."
        exit 1
    fi
    
    # Проверка Docker Compose (v1 или v2)
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose не установлен. Установите Docker Compose и попробуйте снова."
        exit 1
    fi
    
    # Определяем версию Docker Compose
    if docker compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker compose"
    else
        DOCKER_COMPOSE_CMD="docker-compose"
    fi
    
    # Проверка git (если деплой через git)
    if ! command -v git &> /dev/null; then
        warn "Git не установлен. Убедитесь, что исходный код доступен другим способом."
    fi
    
    log "Системные требования выполнены ✓"
}

# Функция создания директорий
create_directories() {
    log "Создание необходимых директорий..."
    
    sudo mkdir -p "$APP_DIR"
    sudo mkdir -p "$BACKUP_DIR"
    sudo mkdir -p "$APP_DIR/photos"
    sudo mkdir -p "$APP_DIR/reports" 
    sudo mkdir -p "$APP_DIR/user_logs"
    
    # Устанавливаем права
    sudo chown -R $USER:$USER "$APP_DIR"
    chmod 755 "$APP_DIR"
    
    log "Директории созданы ✓"
}

# Функция создания backup
create_backup() {
    if [ -f "$APP_DIR/docker-compose.yml" ]; then
        log "Создание backup текущей конфигурации..."
        
        BACKUP_NAME="logistics-bot-backup-$(date +%Y%m%d_%H%M%S)"
        BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"
        
        mkdir -p "$BACKUP_PATH"
        
        # Останавливаем контейнеры для безопасного backup
        cd "$APP_DIR"
        $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" down
        
        # Создаем backup базы данных если контейнер существует
        if docker volume ls | grep -q logistics_bot_postgres_data; then
            log "Создание backup базы данных..."
            docker run --rm \
                -v logistics_bot_postgres_data:/backup-data \
                -v "$BACKUP_PATH":/backup \
                alpine tar czf /backup/postgres_data.tar.gz -C /backup-data .
        fi
        
        # Копируем конфигурационные файлы
        cp -r settings.json photos reports user_logs "$BACKUP_PATH/" 2>/dev/null || true
        
        log "Backup создан: $BACKUP_PATH ✓"
    fi
}

# Функция деплоя
deploy() {
    log "Начало деплоя $PROJECT_NAME..."
    
    # Переходим в рабочую директорию
    cd "$APP_DIR"
    
    # Проверяем наличие .env файла
    if [ ! -f ".env" ]; then
        error "Файл .env не найден. Создайте файл .env на основе .env.example"
        exit 1
    fi
    
    # Билдим и запускаем контейнеры
    log "Сборка и запуск контейнеров..."
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" build --no-cache
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" up -d
    
    # Ждем запуска базы данных
    log "Ожидание запуска базы данных..."
    sleep 10
    
    # Проверяем здоровье контейнеров
    log "Проверка статуса контейнеров..."
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" ps
    
    # Инициализация базы данных (если нужно)
    if [ "$1" = "--init-db" ]; then
        log "Инициализация базы данных..."
        $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" exec -T logistics-bot-app python setup_projects.py
    fi
    
    log "Деплой завершен успешно! ✓"
}

# Функция для проверки статуса
check_status() {
    log "Проверка статуса сервисов..."
    
    cd "$APP_DIR"
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" ps
    
    # Проверяем логи последних 10 строк
    echo -e "\n${BLUE}Последние логи приложения:${NC}"
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" logs --tail=10 logistics-bot-app
    
    echo -e "\n${BLUE}Последние логи базы данных:${NC}"
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" logs --tail=10 logistics-bot-db
}

# Функция для обновления
update() {
    log "Обновление приложения..."
    
    cd "$APP_DIR"
    
    # Создаем backup перед обновлением
    create_backup
    
    # Загружаем новый код (если используется git)
    if [ -d ".git" ]; then
        log "Загрузка обновлений из Git..."
        git pull origin master
    else
        warn "Git репозиторий не найден. Убедитесь, что новый код скопирован в $APP_DIR"
    fi
    
    # Перезапускаем с новым кодом
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" build --no-cache
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" up -d
    
    log "Обновление завершено ✓"
}

# Функция для остановки сервисов
stop() {
    log "Остановка сервисов..."
    cd "$APP_DIR"
    $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" down
    log "Сервисы остановлены ✓"
}

# Функция для показа логов
show_logs() {
    cd "$APP_DIR"
    if [ "$1" = "app" ]; then
        $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" logs -f logistics-bot-app
    elif [ "$1" = "db" ]; then
        $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" logs -f logistics-bot-db
    else
        $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" logs -f
    fi
}

# Функция очистки старых образов
cleanup() {
    log "Очистка неиспользуемых Docker образов..."
    docker system prune -f
    docker volume prune -f
    log "Очистка завершена ✓"
}

# Главная функция
main() {
    case "$1" in
        "deploy")
            check_requirements
            create_directories
            create_backup
            deploy "$2"
            ;;
        "status")
            check_status
            ;;
        "update")
            update
            ;;
        "stop")
            stop
            ;;
        "start")
            cd "$APP_DIR"
            $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" up -d
            log "Сервисы запущены ✓"
            ;;
        "restart")
            stop
            sleep 2
            cd "$APP_DIR"
            $DOCKER_COMPOSE_CMD -p "$COMPOSE_PROJECT_NAME" up -d
            log "Сервисы перезапущены ✓"
            ;;
        "logs")
            show_logs "$2"
            ;;
        "backup")
            create_backup
            ;;
        "cleanup")
            cleanup
            ;;
        *)
            echo "Использование: $0 {deploy|status|update|stop|start|restart|logs|backup|cleanup}"
            echo ""
            echo "Команды:"
            echo "  deploy [--init-db]  Первоначальный деплой (с опциональной инициализацией БД)"
            echo "  status              Показать статус контейнеров"
            echo "  update              Обновить приложение"
            echo "  stop                Остановить все сервисы"
            echo "  start               Запустить все сервисы" 
            echo "  restart             Перезапустить все сервисы"
            echo "  logs [app|db]       Показать логи (все или конкретного сервиса)"
            echo "  backup              Создать backup"
            echo "  cleanup             Очистить неиспользуемые Docker данные"
            echo ""
            echo "Примеры:"
            echo "  $0 deploy --init-db     # Первый деплой с инициализацией БД"
            echo "  $0 logs app             # Показать логи приложения"
            echo "  $0 status               # Проверить статус"
            exit 1
            ;;
    esac
}

# Запуск основной функции
main "$@"