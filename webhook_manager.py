"""
Менеджер вебхуков для отправки дневных отчетов во внешние системы
"""

import requests
import logging
import json
import time
from typing import Dict, Optional, Any
from settings import get_settings

logger = logging.getLogger(__name__)

class WebhookManager:
    def __init__(self):
        self.settings = get_settings()
    
    def send_daily_report(self, report_data: Dict[str, Any], user_info: Dict[str, Any] = None) -> bool:
        """Отправить дневной отчет на URL вебхука с логикой повторов"""
        
        webhook_url = self.settings.get_daily_report_webhook_url()
        
        if not webhook_url:
            logger.info("URL вебхука не настроен, пропускаем отправку")
            return True
        
        if not self.settings.is_webhook_sending_enabled():
            logger.info("Отправка вебхуков отключена в настройках")
            return True
        
        payload = {
            "type": "daily_report",
            "timestamp": report_data.get("date", ""),
            "data": report_data
        }
        
        # Добавляем информацию о пользователе, если предоставлена
        if user_info:
            payload["user"] = user_info
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "BotDriveLogistic/1.0"
        }
        
        timeout = self.settings.get_webhook_timeout_seconds()
        retry_attempts = self.settings.get_webhook_retry_attempts()
        
        for attempt in range(retry_attempts):
            try:
                logger.info(f"Отправляем дневной отчет на вебхук (попытка {attempt + 1}/{retry_attempts}): {webhook_url}")
                
                response = requests.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=timeout
                )
                
                if response.status_code in [200, 201, 202]:
                    logger.info(f"Успешно отправлен дневной отчет на вебхук: {response.status_code}")
                    return True
                else:
                    logger.warning(f"Вебхук вернул неуспешный статус: {response.status_code} - {response.text}")
                    
            except requests.exceptions.Timeout:
                logger.error(f"Таймаут вебхука через {timeout} секунд (попытка {attempt + 1})")
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Ошибка соединения с вебхуком (попытка {attempt + 1}): {e}")
            except Exception as e:
                logger.error(f"Неожиданная ошибка отправки вебхука (попытка {attempt + 1}): {e}")
            
            # Ожидаем перед повторной попыткой (экспоненциальная задержка)
            if attempt < retry_attempts - 1:
                wait_time = 2 ** attempt
                logger.info(f"Ожидаем {wait_time} секунд перед повторной попыткой...")
                time.sleep(wait_time)
        
        logger.error(f"Не удалось отправить дневной отчет на вебхук после {retry_attempts} попыток")
        return False
    
    def test_webhook(self) -> bool:
        """Проверить соединение с вебхуком"""
        webhook_url = self.settings.get_daily_report_webhook_url()
        
        if not webhook_url:
            logger.error("URL вебхука не настроен для тестирования")
            return False
        
        test_payload = {
            "type": "test",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "message": "Тест вебхука от BotDriveLogistic"
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "BotDriveLogistic/1.0"
        }
        
        try:
            logger.info(f"Проверяем соединение с вебхуком: {webhook_url}")
            
            response = requests.post(
                webhook_url,
                json=test_payload,
                headers=headers,
                timeout=self.settings.get_webhook_timeout_seconds()
            )
            
            if response.status_code in [200, 201, 202]:
                logger.info(f"Тест вебхука успешный: {response.status_code}")
                return True
            else:
                logger.warning(f"Тест вебхука вернул: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Тест вебхука не удался: {e}")
            return False

# Глобальный экземпляр
_webhook_manager_instance = None

def get_webhook_manager() -> WebhookManager:
    """Получить экземпляр менеджера вебхуков"""
    global _webhook_manager_instance
    if _webhook_manager_instance is None:
        _webhook_manager_instance = WebhookManager()
    return _webhook_manager_instance