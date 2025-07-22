"""
Менеджер логирования активности пользователей по физическим дням
"""

import os
import logging
from datetime import datetime, date
from typing import Dict, Any, Optional, List
from models import User

logger = logging.getLogger(__name__)

class UserActivityLogger:
    def __init__(self, log_directory: str = "user_logs"):
        self.log_directory = log_directory
        self._ensure_log_directory()
    
    def _ensure_log_directory(self):
        """Создать директорию для логов если её нет"""
        if not os.path.exists(self.log_directory):
            os.makedirs(self.log_directory)
            logger.info(f"Создана директория для логов: {self.log_directory}")
    
    def _get_log_file_path(self, user_id: int, log_date: date) -> str:
        """Получить путь к файлу лога для пользователя и даты"""
        date_str = log_date.strftime('%Y%m%d')
        return os.path.join(self.log_directory, f"user_{user_id}_{date_str}.log")
    
    def _write_log_entry(self, user_id: int, log_date: date, entry: str, timestamp: Optional[datetime] = None):
        """Записать строку в лог файл"""
        if timestamp is None:
            timestamp = datetime.now()
        
        log_file = self._get_log_file_path(user_id, log_date)
        
        # Проверяем, нужно ли создать заголовок файла
        is_new_file = not os.path.exists(log_file)
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                if is_new_file:
                    # Заголовок файла
                    f.write(f"{'='*80}\n")
                    f.write(f"ЛОГ АКТИВНОСТИ ПОЛЬЗОВАТЕЛЯ {user_id}\n")
                    f.write(f"ДАТА: {log_date.strftime('%d.%m.%Y (%A)')}\n")
                    f.write(f"{'='*80}\n\n")
                
                # Записываем запись с timestamp
                time_str = timestamp.strftime('%H:%M:%S')
                f.write(f"[{time_str}] {entry}\n")
                
        except Exception as e:
            logger.error(f"Ошибка записи в лог {log_file}: {e}")
    
    def _write_section_header(self, user_id: int, log_date: date, section_title: str):
        """Записать заголовок секции"""
        log_file = self._get_log_file_path(user_id, log_date)
        
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{'-'*40}\n")
                f.write(f"{section_title.upper()}\n")
                f.write(f"{'-'*40}\n")
        except Exception as e:
            logger.error(f"Ошибка записи заголовка в лог {log_file}: {e}")
    
    def log_action(self, user_id: int, action_type: str, action_data: Dict[str, Any], 
                   timestamp: Optional[datetime] = None):
        """Записать действие пользователя в лог"""
        if timestamp is None:
            timestamp = datetime.now()
        
        log_date = timestamp.date()
        
        # Формируем читаемую строку в зависимости от типа действия
        if action_type == "bot_command":
            command = action_data.get("command", "unknown")
            success = action_data.get("success", True)
            error_msg = action_data.get("error_message", "")
            
            if success:
                entry = f"🤖 КОМАНДА: /{command}"
                if action_data.get("args"):
                    args_str = str(action_data["args"])
                    entry += f" {args_str}"
            else:
                entry = f"❌ ОШИБКА КОМАНДЫ: /{command} - {error_msg}"
        
        elif action_type == "work_session":
            session_type = action_data.get("session_type", "unknown")
            vehicle = action_data.get("vehicle", "")
            work_day_id = action_data.get("work_day_id", "")
            
            if session_type == "start":
                entry = f"🚗 НАЧАЛО РЕЙСА: {vehicle} (ID: {work_day_id})"
            elif session_type == "end":
                distance = action_data.get("total_distance", 0)
                duration = action_data.get("duration_minutes", 0)
                entry = f"🏁 КОНЕЦ РЕЙСА: {distance:.1f} км, {duration:.0f} мин (ID: {work_day_id})"
        
        elif action_type == "trip":
            start_loc = action_data.get("start_location", "")
            end_loc = action_data.get("end_location", "")
            distance = action_data.get("distance_km", 0)
            project_name = action_data.get("project_name", "")
            
            entry = f"🚙 ПОЕЗДКА: {start_loc} → {end_loc} ({distance} км)"
            if project_name:
                entry += f" | Проект: {project_name}"
        
        elif action_type == "activity":
            activity_type = action_data.get("activity_type", "")
            project_name = action_data.get("project_name", "")
            duration = action_data.get("duration_minutes", 0)
            
            activity_emoji = "🔨" if activity_type == "working" else "🛒"
            activity_name = "РАБОТА" if activity_type == "working" else "ЗАКУПКА"
            entry = f"{activity_emoji} {activity_name}: {project_name} ({duration:.0f} мин)"
        
        else:
            entry = f"📝 {action_type.upper()}: {str(action_data)}"
        
        # Записываем в файл
        self._write_log_entry(user_id, log_date, entry, timestamp)
    
    def log_bot_command(self, user_id: int, command: str, args: Optional[Dict] = None,
                        success: bool = True, error_message: Optional[str] = None):
        """Записать команду бота"""
        action_data = {
            "command": command,
            "args": args or {},
            "success": success,
            "error_message": error_message
        }
        
        self.log_action(user_id, "bot_command", action_data)
    
    def log_work_session_start(self, user_id: int, vehicle: str, work_day_id: int):
        """Записать начало рабочей сессии"""
        action_data = {
            "work_day_id": work_day_id,
            "vehicle": vehicle,
            "session_type": "start"
        }
        
        self.log_action(user_id, "work_session", action_data)
    
    def log_work_session_end(self, user_id: int, work_day_id: int, 
                            total_distance: float = 0.0, duration_minutes: float = 0.0):
        """Записать окончание рабочей сессии"""
        action_data = {
            "work_day_id": work_day_id,
            "total_distance": total_distance,
            "duration_minutes": duration_minutes,
            "session_type": "end"
        }
        
        self.log_action(user_id, "work_session", action_data)
    
    def log_trip(self, user_id: int, work_day_id: int, trip_id: int, 
                 start_location: str, end_location: str, distance_km: float,
                 project_id: Optional[int] = None, project_name: Optional[str] = None):
        """Записать поездку"""
        action_data = {
            "work_day_id": work_day_id,
            "trip_id": trip_id,
            "start_location": start_location,
            "end_location": end_location,
            "distance_km": distance_km,
            "project_id": project_id,
            "project_name": project_name
        }
        
        self.log_action(user_id, "trip", action_data)
    
    def log_activity(self, user_id: int, work_day_id: int, activity_id: int,
                     activity_type: str, project_id: int, project_name: str,
                     duration_minutes: float):
        """Записать активность (работа/закупка)"""
        action_data = {
            "work_day_id": work_day_id,
            "activity_id": activity_id,
            "activity_type": activity_type,
            "project_id": project_id,
            "project_name": project_name,
            "duration_minutes": duration_minutes
        }
        
        self.log_action(user_id, "activity", action_data)
    
    def get_user_day_log(self, user_id: int, log_date: date) -> Dict[str, Any]:
        """Получить основную информацию из лога пользователя за день"""
        log_file = self._get_log_file_path(user_id, log_date)
        
        if not os.path.exists(log_file):
            return {
                "user_id": user_id,
                "date": log_date.isoformat(),
                "total_actions": 0,
                "commands_used": [],
                "work_sessions": 0,
                "trips": 0,
                "activities": 0,
                "has_errors": False
            }
        
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            # Базовый анализ лога
            total_actions = len([line for line in lines if line.startswith('[')])
            commands_used = []
            work_sessions = 0
            trips = 0
            activities = 0
            has_errors = False
            
            for line in lines:
                if '🤖 КОМАНДА:' in line:
                    # Извлекаем команду
                    try:
                        command = line.split('🤖 КОМАНДА: /')[1].split()[0]
                        if command not in commands_used:
                            commands_used.append(command)
                    except:
                        pass
                elif '🚗 НАЧАЛО РЕЙСА:' in line:
                    work_sessions += 1
                elif '🚙 ПОЕЗДКА:' in line:
                    trips += 1
                elif '🔨 РАБОТА:' in line or '🛒 ЗАКУПКА:' in line:
                    activities += 1
                elif '❌ ОШИБКА КОМАНДЫ:' in line:
                    has_errors = True
            
            return {
                "user_id": user_id,
                "date": log_date.isoformat(),
                "total_actions": total_actions,
                "commands_used": commands_used,
                "work_sessions": work_sessions,
                "trips": trips,
                "activities": activities,
                "has_errors": has_errors,
                "log_file_path": log_file
            }
            
        except Exception as e:
            logger.error(f"Ошибка чтения лога {log_file}: {e}")
            return {
                "user_id": user_id,
                "date": log_date.isoformat(),
                "total_actions": 0,
                "commands_used": [],
                "work_sessions": 0,
                "trips": 0,
                "activities": 0,
                "has_errors": False,
                "error": str(e)
            }
    
    def get_user_logs_summary(self, user_id: int, start_date: date, end_date: date) -> Dict[str, Any]:
        """Получить сводку логов пользователя за период"""
        summary = {
            "user_id": user_id,
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "total_days": 0,
            "total_actions": 0,
            "total_work_sessions": 0,
            "total_trips": 0,
            "total_activities": 0,
            "commands_used": set(),
            "daily_summaries": []
        }
        
        from datetime import timedelta
        current_date = start_date
        while current_date <= end_date:
            day_log = self.get_user_day_log(user_id, current_date)
            
            if day_log["total_actions"] > 0:
                summary["total_days"] += 1
                summary["total_actions"] += day_log["total_actions"]
                summary["total_work_sessions"] += day_log["work_sessions"]
                summary["total_trips"] += day_log["trips"]
                summary["total_activities"] += day_log["activities"]
                summary["commands_used"].update(day_log["commands_used"])
                
                summary["daily_summaries"].append({
                    "date": current_date.isoformat(),
                    "actions": day_log["total_actions"],
                    "work_sessions": day_log["work_sessions"],
                    "trips": day_log["trips"],
                    "activities": day_log["activities"],
                    "has_errors": day_log["has_errors"]
                })
            
            current_date += timedelta(days=1)
        
        # Конвертировать sets в lists
        summary["commands_used"] = list(summary["commands_used"])
        
        return summary

# Глобальный экземпляр логгера
_activity_logger_instance = None

def get_activity_logger() -> UserActivityLogger:
    """Получить экземпляр логгера активности"""
    global _activity_logger_instance
    if _activity_logger_instance is None:
        _activity_logger_instance = UserActivityLogger()
    return _activity_logger_instance