"""
Module for fetching objects from Remonline CRM
"""

import requests
import json
import logging
from typing import List, Dict, Optional
from datetime import datetime



logger = logging.getLogger(__name__)


class RemonlineCRM:
    def __init__(self, api_key: str):
        """Initialize Remonline CRM client"""
        self.api_key = api_key
        self.base_url = "https://api.remonline.app"
        self.headers = {
            "accept": "application/json",
            "authorization": f"Bearer {api_key}"
        }
    
    def get_active_objects(self) -> List[Dict]:
        """
        Fetch active objects from Remonline CRM
        Returns objects with status_id = 2974853 or status names "В роботі", "Срочный ремонт", "Реконструкция"
        """
        try:
            url = f"{self.base_url}/orders"
            
            # Parameters for fetching orders  
            params = {
                'page': 1,
                'limit': 10,  # Start with smaller limit for testing
                # Add status filter if API supports it
                # 'status_ids[]': [2974853],
            }
            
            logger.info("Fetching objects from Remonline CRM...")
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            response_data = response.json()
            
            # Log the actual response structure for debugging
            logger.info(f"CRM API response type: {type(response_data)}")
            if isinstance(response_data, dict):
                logger.info(f"CRM API response keys: {list(response_data.keys())}")
            
            # Handle different response formats
            if isinstance(response_data, list):
                orders_list = response_data
            elif isinstance(response_data, dict):
                # Try common response wrapper formats
                if 'data' in response_data:
                    orders_list = response_data['data']
                elif 'orders' in response_data:
                    orders_list = response_data['orders']
                elif 'results' in response_data:
                    orders_list = response_data['results']
                else:
                    logger.error(f"Unexpected response format from CRM. Keys: {list(response_data.keys())}")
                    logger.error(f"Response sample: {str(response_data)[:1000]}")
                    # Try to find orders in any nested structure
                    for key, value in response_data.items():
                        if isinstance(value, list):
                            logger.info(f"Found list under key '{key}' with {len(value)} items")
                            orders_list = value
                            break
                    else:
                        return []
            else:
                logger.error(f"Unexpected response format from CRM: {type(response_data)}")
                return []
            
            if not isinstance(orders_list, list):
                logger.error(f"Orders data is not a list: {type(orders_list)}")
                return []
            
            # Filter objects by status using settings
            from settings import get_settings
            settings = get_settings()
            
            active_objects = []
            target_statuses = settings.get_target_status_names()
            target_status_id = settings.get_target_status_id()
            status_name_filter_enabled = settings.is_status_name_filter_enabled()
            status_id_filter_enabled = settings.is_status_id_filter_enabled()
            
            # Debug: log all unique statuses found
            found_statuses = set()
            found_status_ids = set()
            
            for order in orders_list:
                # Extract status from nested structure
                status_obj = order.get('status', {})
                status_id = status_obj.get('id') if status_obj else None
                status_name = status_obj.get('name', '') if status_obj else ''
                
                # Extract client from nested structure  
                client_obj = order.get('client', {})
                client_name = client_obj.get('name', '') if client_obj else ''
                
                found_statuses.add(status_name)
                found_status_ids.add(status_id)
                
                # Debug: log first few orders structure
                if len(active_objects) == 0 and len(found_statuses) <= 3:
                    logger.info(f"Sample order: ID={order.get('id')}, status_name='{status_name}', status_id={status_id}, client_name='{client_name}'")
                
                # Check if object meets criteria based on settings
                status_match = False
                
                if status_id_filter_enabled and status_id == target_status_id:
                    status_match = True
                elif status_name_filter_enabled and status_name in target_statuses:
                    status_match = True
                
                if status_match:
                    
                    order_id = order.get('id')
                    id_label = order.get('id_label', '')
                    
                    if client_name and order_id:
                        active_objects.append({
                            'id': order_id,
                            'name': client_name,
                            'id_label': id_label,
                            'status_name': status_name,
                            'status_id': status_id,
                            'created_at': order.get('created_at', ''),
                            'source': 'remonline'
                        })
                        logger.info(f"Found matching object: {client_name} (status: {status_name})")
            
            # Log all found statuses for debugging
            logger.info(f"All status names found: {sorted(found_statuses)}")
            logger.info(f"All status IDs found: {sorted(found_status_ids)}")
            logger.info(f"Looking for status ID: {target_status_id} or statuses: {target_statuses}")
            
            logger.info(f"Processed {len(orders_list)} total orders from CRM")
            logger.info(f"Successfully filtered {len(active_objects)} active objects from CRM")
            
            # Log some sample data for debugging
            if active_objects:
                logger.info(f"Sample active object: {active_objects[0]}")
            
            return active_objects
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error(f"HTTP 401: Unauthorized. Check API key")
            else:
                logger.error(f"HTTP error: {e.response.status_code} {e.response.reason}")
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error: {e}")
            return []
            
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from CRM")
            return []
            
        except Exception as e:
            logger.error(f"Unexpected error while fetching CRM objects: {e}")
            return []
    
    def get_combined_objects_list(self, static_objects: List[Dict]) -> List[Dict]:
        """
        Get combined list of static objects + CRM objects
        Static objects always come first
        """
        try:
            # Get active objects from CRM
            crm_objects = self.get_active_objects()
            
            # Combine lists: static objects first, then CRM objects
            combined_objects = static_objects.copy()
            combined_objects.extend(crm_objects)
            
            logger.info(f"Combined objects list: {len(static_objects)} static + {len(crm_objects)} CRM = {len(combined_objects)} total")
            
            return combined_objects
            
        except Exception as e:
            logger.error(f"Error combining objects lists: {e}")
            # Return only static objects in case of error
            return static_objects.copy()
    
    def get_all_objects_without_filters(self) -> List[Dict]:
        """
        Fetch ALL objects from Remonline CRM without status filters
        Used for similarity matching in manual input
        """
        try:
            url = f"{self.base_url}/orders"
            
            # Parameters for fetching all orders without filters
            params = {
                'page': 1,
                'limit': 100,  # Increase limit to get more objects for matching
            }
            
            logger.info("Fetching ALL objects from Remonline CRM (no filters)...")
            
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            
            response_data = response.json()
            
            # Handle different response formats
            if isinstance(response_data, list):
                orders_list = response_data
            elif isinstance(response_data, dict):
                if 'data' in response_data:
                    orders_list = response_data['data']
                elif 'orders' in response_data:
                    orders_list = response_data['orders']
                elif 'results' in response_data:
                    orders_list = response_data['results']
                else:
                    logger.error(f"Unexpected response format from CRM. Keys: {list(response_data.keys())}")
                    for key, value in response_data.items():
                        if isinstance(value, list):
                            logger.info(f"Found list under key '{key}' with {len(value)} items")
                            orders_list = value
                            break
                    else:
                        return []
            else:
                logger.error(f"Unexpected response format from CRM: {type(response_data)}")
                return []
            
            if not isinstance(orders_list, list):
                logger.error(f"Orders data is not a list: {type(orders_list)}")
                return []
            
            # Extract all objects without status filtering
            all_objects = []
            
            for order in orders_list:
                # Extract client from nested structure  
                client_obj = order.get('client', {})
                client_name = client_obj.get('name', '') if client_obj else ''
                
                order_id = order.get('id')
                id_label = order.get('id_label', '')
                
                if client_name and order_id:
                    # Extract status info for metadata
                    status_obj = order.get('status', {})
                    status_id = status_obj.get('id') if status_obj else None
                    status_name = status_obj.get('name', '') if status_obj else ''
                    
                    all_objects.append({
                        'id': order_id,
                        'name': client_name,
                        'id_label': id_label,
                        'status_name': status_name,
                        'status_id': status_id,
                        'created_at': order.get('created_at', ''),
                        'source': 'remonline'
                    })
            
            logger.info(f"Successfully fetched {len(all_objects)} total objects from CRM (no filters)")
            
            return all_objects
            
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error(f"HTTP 401: Unauthorized. Check API key")
            else:
                logger.error(f"HTTP error: {e.response.status_code} {e.response.reason}")
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Connection error: {e}")
            return []
            
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from CRM")
            return []
            
        except Exception as e:
            logger.error(f"Unexpected error while fetching all CRM objects: {e}")
            return []


# Static objects that are always present
STATIC_OBJECTS = [
    {
        'id': 'shop',
        'name': 'Магазин',
        'description': 'Магазин для закупок',
        'source': 'static'
    },
    {
        'id': 'warehouse',
        'name': 'Склад',
        'description': 'Складские операции',
        'source': 'static'
    },
    {
        'id': 'home',
        'name': 'Дом',
        'description': 'Домашние дела',
        'source': 'static'
    },
    {
        'id': 'fuel_station',
        'name': 'Заправка',
        'description': 'Заправочная станция',
        'source': 'static'
    }
]


def get_crm_client() -> Optional[RemonlineCRM]:
    """Get CRM client instance with API key from environment"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    api_key = os.getenv('REMONLINE_API_KEY')
    if not api_key:
        logger.warning("REMONLINE_API_KEY not found in environment variables")
        return None
    
    return RemonlineCRM(api_key)


def get_all_objects() -> List[Dict]:
    """
    Get all objects: static + CRM objects
    Returns static objects only if CRM is unavailable
    """
    try:
        crm_client = get_crm_client()
        
        if crm_client:
            return crm_client.get_combined_objects_list(STATIC_OBJECTS)
        else:
            logger.warning("CRM client not available, using static objects only")
            return STATIC_OBJECTS.copy()
    except Exception as e:
        logger.error(f"Error getting CRM objects, falling back to static objects: {e}")
        return STATIC_OBJECTS.copy()