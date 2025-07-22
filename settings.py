"""
Settings module for logistics bot
Loads configuration from JSON file
"""

import json
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class Settings:
    def __init__(self, settings_file: str = "settings.json"):
        self.settings_file = settings_file
        self._settings = {}
        self.load_settings()
    
    def load_settings(self):
        """Load settings from JSON file"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    self._settings = json.load(f)
                logger.info(f"Settings loaded from {self.settings_file}")
            else:
                # Create default settings file if it doesn't exist
                self.create_default_settings()
                logger.info(f"Created default settings file: {self.settings_file}")
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            self.create_default_settings()
    
    def create_default_settings(self):
        """Create default settings file"""
        default_settings = {
            "vehicles": {
                "Машина А": {
                    "fuel_consumption_per_100km": 8.5,
                    "tank_capacity": 60.0,
                    "current_fuel_level": 45.0,
                    "total_fuel_cost_in_tank": 2250.0,  # Стоимость топлива в баке
                    "current_mileage": 150000,
                    "last_updated": datetime.now().isoformat()
                },
                "Машина Б": {
                    "fuel_consumption_per_100km": 9.2,
                    "tank_capacity": 55.0,
                    "current_fuel_level": 40.0,
                    "total_fuel_cost_in_tank": 2000.0,
                    "current_mileage": 89000,
                    "last_updated": datetime.now().isoformat()
                },
                "Машина В": {
                    "fuel_consumption_per_100km": 7.8,
                    "tank_capacity": 65.0,
                    "current_fuel_level": 50.0,
                    "total_fuel_cost_in_tank": 2500.0,
                    "current_mileage": 200000,
                    "last_updated": datetime.now().isoformat()
                }
            },
            "admin_users": [
                924447690,
                7402502266
            ],
            "fuel_control": {
                "low_fuel_warning_threshold_percent": 15.0,  # Warning when fuel < 15% of tank
                "critical_fuel_threshold_percent": 5.0,      # Critical when fuel < 5% of tank
                "enable_fuel_tracking": True,
                "auto_update_fuel_on_refuel": True,
                "show_detailed_fuel_info": False  # Show detailed cost info to users
            },
            "general": {
                "default_fuel_efficiency_tolerance": 1.2  # 20% tolerance for fuel consumption
            },
            "crm_filters": {
                "target_status_names": ["В роботі", "Срочный ремонт", "Реконструкция"],
                "target_status_id": 2974853,
                "enable_status_name_filter": True,
                "enable_status_id_filter": True
            },
            "cache_settings": {
                "daily_objects_ttl_hours": 4,
                "all_objects_ttl_hours": 2,
                "enable_cache_warnings": True,
                "cache_warning_age_hours": 2,
                "auto_refresh_on_stale": False,
                "max_cache_entries_per_user": 10
            },
            "cache_settings": {
                "daily_objects_ttl_hours": 4,
                "all_objects_ttl_hours": 2,
                "enable_cache_warnings": True,
                "cache_warning_age_hours": 2,
                "auto_refresh_on_stale": False,
                "max_cache_entries_per_user": 10
            }
        }
        
        self._settings = default_settings
        self.save_settings()
    
    def save_settings(self):
        """Save current settings to file"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            logger.info(f"Settings saved to {self.settings_file}")
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
    
    def get_vehicles(self) -> Dict[str, Dict]:
        """Get all vehicle configurations"""
        return self._settings.get("vehicles", {})
    
    def get_vehicle_names(self) -> List[str]:
        """Get list of vehicle names"""
        return list(self.get_vehicles().keys())
    
    def get_vehicle_config(self, vehicle_name: str) -> Optional[Dict]:
        """Get configuration for specific vehicle"""
        return self.get_vehicles().get(vehicle_name)
    
    def get_admin_users(self) -> List[int]:
        """Get list of admin user IDs"""
        return self._settings.get("admin_users", [])
    
    def add_admin_user(self, user_id: int):
        """Add admin user"""
        if user_id not in self.get_admin_users():
            self._settings.setdefault("admin_users", []).append(user_id)
            self.save_settings()
    
    def remove_admin_user(self, user_id: int):
        """Remove admin user"""
        admin_users = self.get_admin_users()
        if user_id in admin_users:
            admin_users.remove(user_id)
            self.save_settings()
    
    def update_vehicle_fuel(self, vehicle_name: str, fuel_level: float, total_cost: float = None):
        """Update current fuel level and total cost for vehicle"""
        vehicles = self.get_vehicles()
        if vehicle_name in vehicles:
            vehicles[vehicle_name]["current_fuel_level"] = fuel_level
            if total_cost is not None:
                vehicles[vehicle_name]["total_fuel_cost_in_tank"] = total_cost
            vehicles[vehicle_name]["last_updated"] = datetime.now().isoformat()
            self.save_settings()
            logger.info(f"Updated fuel for {vehicle_name}: {fuel_level}L, cost: {total_cost}")
    
    def update_vehicle_mileage(self, vehicle_name: str, mileage: int):
        """Update current mileage for vehicle"""
        vehicles = self.get_vehicles()
        if vehicle_name in vehicles:
            vehicles[vehicle_name]["current_mileage"] = mileage
            vehicles[vehicle_name]["last_updated"] = datetime.now().isoformat()
            self.save_settings()
            logger.info(f"Updated mileage for {vehicle_name}: {mileage}km")
    
    def get_fuel_control_settings(self) -> Dict:
        """Get fuel control configuration"""
        return self._settings.get("fuel_control", {})
    
    def is_fuel_tracking_enabled(self) -> bool:
        """Check if fuel tracking is enabled"""
        return self.get_fuel_control_settings().get("enable_fuel_tracking", True)
    
    def get_low_fuel_threshold_percent(self) -> float:
        """Get low fuel warning threshold as percentage"""
        return self.get_fuel_control_settings().get("low_fuel_warning_threshold_percent", 15.0)
    
    def get_critical_fuel_threshold_percent(self) -> float:
        """Get critical fuel threshold as percentage"""
        return self.get_fuel_control_settings().get("critical_fuel_threshold_percent", 5.0)
    
    def get_low_fuel_threshold_liters(self, vehicle_name: str) -> float:
        """Get low fuel warning threshold in liters for specific vehicle"""
        vehicle_config = self.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            return 0.0
        tank_capacity = vehicle_config.get("tank_capacity", 60.0)
        threshold_percent = self.get_low_fuel_threshold_percent()
        return (tank_capacity * threshold_percent) / 100
    
    def get_crm_filters(self) -> Dict:
        """Get CRM filtering configuration"""
        return self._settings.get("crm_filters", {})
    
    def get_target_status_names(self) -> List[str]:
        """Get list of target status names for CRM filtering"""
        return self.get_crm_filters().get("target_status_names", ["В роботі", "Срочный ремонт", "Реконструкция"])
    
    def get_target_status_id(self) -> int:
        """Get target status ID for CRM filtering"""
        return self.get_crm_filters().get("target_status_id", 2974853)
    
    def is_status_name_filter_enabled(self) -> bool:
        """Check if status name filtering is enabled"""
        return self.get_crm_filters().get("enable_status_name_filter", True)
    
    def is_status_id_filter_enabled(self) -> bool:
        """Check if status ID filtering is enabled"""
        return self.get_crm_filters().get("enable_status_id_filter", True)
    
    def get_cache_settings(self) -> Dict:
        """Get cache configuration"""
        return self._settings.get("cache_settings", {})
    
    def get_daily_objects_ttl_hours(self) -> int:
        """Get TTL for daily objects cache in hours"""
        return self.get_cache_settings().get("daily_objects_ttl_hours", 4)
    
    def get_all_objects_ttl_hours(self) -> int:
        """Get TTL for all objects cache in hours"""
        return self.get_cache_settings().get("all_objects_ttl_hours", 2)
    
    def is_cache_warnings_enabled(self) -> bool:
        """Check if cache warnings are enabled"""
        return self.get_cache_settings().get("enable_cache_warnings", True)
    
    def get_cache_warning_age_hours(self) -> int:
        """Get cache warning age threshold in hours"""
        return self.get_cache_settings().get("cache_warning_age_hours", 2)
    
    def is_auto_refresh_on_stale_enabled(self) -> bool:
        """Check if automatic refresh on stale cache is enabled"""
        return self.get_cache_settings().get("auto_refresh_on_stale", False)
    
    def get_max_cache_entries_per_user(self) -> int:
        """Get maximum cache entries per user"""
        return self.get_cache_settings().get("max_cache_entries_per_user", 10)
    
    def get_webhook_settings(self) -> Dict:
        """Получить конфигурацию вебхуков"""
        return self._settings.get("webhook_settings", {})
    
    def get_daily_report_webhook_url(self) -> str:
        """Получить URL вебхука для дневных отчетов"""
        return self.get_webhook_settings().get("daily_report_webhook_url", "")
    
    def is_webhook_sending_enabled(self) -> bool:
        """Проверить, включена ли отправка вебхуков"""
        return self.get_webhook_settings().get("enable_webhook_sending", True)
    
    def get_webhook_timeout_seconds(self) -> int:
        """Получить таймаут запроса вебхука в секундах"""
        return self.get_webhook_settings().get("webhook_timeout_seconds", 30)
    
    def get_webhook_retry_attempts(self) -> int:
        """Получить количество попыток повтора вебхука"""
        return self.get_webhook_settings().get("webhook_retry_attempts", 3)
    
    def get_work_cost_settings(self) -> Dict:
        """Получить настройки стоимости работы"""
        return self._settings.get("work_cost", {})
    
    def get_price_per_hour(self) -> float:
        """Получить стоимость часа работы"""
        return self.get_work_cost_settings().get("price_per_hour", 500.0)
    
    def get_work_currency(self) -> str:
        """Получить валюту для стоимости работы"""
        return self.get_work_cost_settings().get("currency", "UAH")

    def reload_settings(self):
        """Reload settings from file"""
        self.load_settings()
        logger.info("Настройки перезагружены")

# Глобальный экземпляр настроек
_settings_instance = None

def get_settings() -> Settings:
    """Get global settings instance"""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

def reload_settings():
    """Reload global settings"""
    global _settings_instance
    if _settings_instance:
        _settings_instance.reload_settings()