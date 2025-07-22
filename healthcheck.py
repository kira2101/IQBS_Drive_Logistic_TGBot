#!/usr/bin/env python3
"""
Скрипт для проверки здоровья приложения
Используется для Docker healthcheck и мониторинга
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from database import get_db_session, create_tables
    from models import User, WorkingDay
    from settings import get_settings
except ImportError as e:
    print(f"ERROR: Не удалось импортировать модули: {e}")
    sys.exit(1)

def check_database_connection():
    """Проверка подключения к базе данных"""
    try:
        db = get_db_session()
        # Простой запрос для проверки соединения
        db.execute("SELECT 1")
        db.close()
        return True
    except Exception as e:
        print(f"DATABASE ERROR: {e}")
        return False

def check_settings():
    """Проверка загрузки настроек"""
    try:
        settings = get_settings()
        if not settings.get('vehicles'):
            print("SETTINGS ERROR: Нет настроек транспортных средств")
            return False
        return True
    except Exception as e:
        print(f"SETTINGS ERROR: {e}")
        return False

def check_recent_activity():
    """Проверка недавней активности (опционально)"""
    try:
        db = get_db_session()
        # Проверяем активность за последние 24 часа
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_activity = db.query(WorkingDay).filter(
            WorkingDay.start_time >= yesterday
        ).count()
        db.close()
        
        # Это информационная проверка, не критичная для здоровья
        print(f"INFO: Активность за последние 24 часа: {recent_activity} рабочих дней")
        return True
    except Exception as e:
        print(f"ACTIVITY WARNING: {e}")
        return True  # Не критично для работы приложения

def main():
    """Основная функция проверки здоровья"""
    print(f"Healthcheck started at {datetime.utcnow()}")
    
    checks = [
        ("Database Connection", check_database_connection),
        ("Settings Loading", check_settings),
        ("Recent Activity", check_recent_activity),
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        try:
            result = check_func()
            status = "PASS" if result else "FAIL"
            print(f"{check_name}: {status}")
            
            if not result and check_name != "Recent Activity":
                all_passed = False
                
        except Exception as e:
            print(f"{check_name}: ERROR - {e}")
            all_passed = False
    
    if all_passed:
        print("Overall health: HEALTHY")
        sys.exit(0)
    else:
        print("Overall health: UNHEALTHY")
        sys.exit(1)

if __name__ == "__main__":
    main()