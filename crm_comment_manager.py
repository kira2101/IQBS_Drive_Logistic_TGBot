"""
Менеджер комментариев CRM для автоматического добавления комментариев к заказам Remonline
"""

import requests
import logging
from datetime import datetime
from typing import Optional
from crm_remonline import get_crm_client

logger = logging.getLogger(__name__)

class CRMCommentManager:
    def __init__(self):
        self.crm_client = get_crm_client()
        
    def post_comment(self, order_id: str, comment_text: str, is_private: bool = True) -> bool:
        """Отправить комментарий к заказу CRM"""
        try:
            if not self.crm_client:
                logger.warning("CRM клиент недоступен")
                return False
                
            url = f"https://api.remonline.app/orders/{order_id}/comments"
            
            payload = {
                "comment": comment_text,
                "is_private": is_private
            }
            
            headers = {
                "accept": "application/json", 
                "content-type": "application/json",
                "authorization": f"Bearer {self.crm_client.api_key}"
            }
            
            response = requests.post(url, json=payload, headers=headers)
            
            if response.status_code in [200, 201]:
                logger.info(f"Успешно отправлен комментарий к заказу {order_id}")
                return True
            else:
                logger.error(f"Ошибка отправки комментария к заказу {order_id}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при отправке комментария к заказу {order_id}: {e}")
            return False
    
    def post_arrival_comment(self, order_id: str, user_name: str, arrival_time: datetime = None) -> bool:
        """Отправить комментарий о прибытии к заказу CRM"""
        if arrival_time is None:
            arrival_time = datetime.now()
            
        time_str = arrival_time.strftime("%H:%M")
        comment_text = f"{user_name} прибыл на объект {time_str}"
        
        return self.post_comment(order_id, comment_text)
    
    def post_departure_comment(self, order_id: str, user_name: str, departure_time: datetime = None) -> bool:
        """Отправить комментарий об отъезде к заказу CRM"""
        if departure_time is None:
            departure_time = datetime.now()
            
        time_str = departure_time.strftime("%H:%M")
        comment_text = f"{user_name} уехал с объекта {time_str}"
        
        return self.post_comment(order_id, comment_text)

# Глобальный экземпляр
_comment_manager_instance = None

def get_comment_manager() -> CRMCommentManager:
    """Получить экземпляр менеджера комментариев"""
    global _comment_manager_instance
    if _comment_manager_instance is None:
        _comment_manager_instance = CRMCommentManager()
    return _comment_manager_instance