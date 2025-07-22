"""
CRM Cache Manager for optimizing CRM data fetching
Implements caching strategies to reduce API calls and improve performance
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from models import CRMCache
from crm_remonline import get_crm_client
from settings import get_settings

logger = logging.getLogger(__name__)

class CRMCacheManager:
    def __init__(self, db: Session):
        self.db = db
        self.crm_client = get_crm_client()
        self.settings = get_settings()
    
    def get_cached_objects(self, user_id: int, cache_type: str = 'daily') -> Optional[List[Dict]]:
        """Get cached CRM objects if valid cache exists"""
        try:
            cache_entry = self.db.query(CRMCache).filter(
                CRMCache.user_id == user_id,
                CRMCache.cache_type == cache_type,
                CRMCache.expires_at > datetime.utcnow()
            ).first()
            
            if cache_entry:
                logger.info(f"Cache HIT for user {user_id}, type {cache_type}")
                return cache_entry.cache_data
            else:
                logger.info(f"Cache MISS for user {user_id}, type {cache_type}")
                return None
        except Exception as e:
            logger.error(f"Error getting cached objects: {e}")
            return None
    
    def set_cached_objects(self, user_id: int, objects: List[Dict], cache_type: str = 'daily', 
                          expire_hours: int = None) -> bool:
        """Cache CRM objects with expiration"""
        try:
            # Get TTL from settings if not specified
            if expire_hours is None:
                from settings import get_settings
                settings = get_settings()
                if cache_type == 'daily':
                    expire_hours = settings.get_daily_objects_ttl_hours()
                else:
                    expire_hours = settings.get_all_objects_ttl_hours()
            
            # Remove existing cache for this user and type
            self.db.query(CRMCache).filter(
                CRMCache.user_id == user_id,
                CRMCache.cache_type == cache_type
            ).delete()
            
            # Create new cache entry
            expires_at = datetime.utcnow() + timedelta(hours=expire_hours)
            
            cache_entry = CRMCache(
                user_id=user_id,
                cache_type=cache_type,
                cache_data=objects,
                expires_at=expires_at
            )
            
            self.db.add(cache_entry)
            self.db.commit()
            
            logger.info(f"Cached {len(objects)} CRM objects for user {user_id}, expires at {expires_at}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching objects: {e}")
            self.db.rollback()
            return False
    
    def get_or_fetch_daily_objects(self, user_id: int, force_refresh: bool = False) -> List[Dict]:
        """Get daily objects from cache or fetch from CRM if cache miss"""
        if not force_refresh:
            # Try cache first
            cached_objects = self.get_cached_objects(user_id, 'daily')
            
            if cached_objects is not None:
                return cached_objects
        
        # Cache miss or forced refresh - fetch from CRM
        logger.info(f"Fetching fresh CRM daily objects for user {user_id}")
        
        if not self.crm_client:
            logger.warning("CRM client not available")
            return []
        
        try:
            # Fetch daily objects from CRM
            daily_objects = self.crm_client.get_active_objects()
            
            # Cache the results using configured TTL
            self.set_cached_objects(user_id, daily_objects, 'daily')
            
            return daily_objects
            
        except Exception as e:
            logger.error(f"Error fetching CRM daily objects: {e}")
            return []
    
    def get_or_fetch_all_objects(self, user_id: int, force_refresh: bool = False) -> List[Dict]:
        """Get all objects from cache or fetch from CRM if cache miss"""
        if not force_refresh:
            # Try cache first  
            cached_objects = self.get_cached_objects(user_id, 'all_objects')
            
            if cached_objects is not None:
                return cached_objects
        
        # Cache miss or forced refresh - fetch from CRM
        logger.info(f"Fetching fresh CRM all objects for user {user_id}")
        
        if not self.crm_client:
            logger.warning("CRM client not available")
            return []
        
        try:
            # Fetch all objects from CRM (without filters)
            all_objects = self.crm_client.get_all_objects_without_filters()
            
            # Cache the results using configured TTL
            self.set_cached_objects(user_id, all_objects, 'all_objects')
            
            return all_objects
            
        except Exception as e:
            logger.error(f"Error fetching CRM all objects: {e}")
            return []
    
    def get_bulk_crm_metadata(self, user_id: int, project_ids: List[int]) -> Dict[int, Dict]:
        """Get CRM metadata for multiple projects in a single operation"""
        # Get cached daily objects
        daily_objects = self.get_or_fetch_daily_objects(user_id)
        
        # Create lookup dictionary by CRM ID
        crm_lookup = {}
        for obj in daily_objects:
            if obj.get('id'):
                crm_lookup[str(obj['id'])] = {
                    "source": "remonline",
                    "crm_id": obj.get('id'),
                    "id_label": obj.get('id_label'),
                    "status_name": obj.get('status_name'),
                    "status_id": obj.get('status_id'),
                    "created_at": obj.get('created_at')
                }
        
        # Map project IDs to CRM metadata
        result = {}
        
        # This needs to be enhanced to link projects to CRM IDs
        # For now, we'll check project descriptions for CRM ID references
        from models import Project
        
        projects = self.db.query(Project).filter(Project.id.in_(project_ids)).all()
        
        for project in projects:
            if project.description and "CRM объект" in project.description:
                # Extract CRM ID from description
                import re
                match = re.search(r'ID: ([^)]+)', project.description)
                if match:
                    crm_id = match.group(1)
                    if crm_id in crm_lookup:
                        result[project.id] = crm_lookup[crm_id]
                        continue
            
            # Default for non-CRM projects
            result[project.id] = {"source": "static"}
        
        return result
    
    def invalidate_cache(self, user_id: int, cache_type: Optional[str] = None):
        """Invalidate cache for user"""
        try:
            query = self.db.query(CRMCache).filter(CRMCache.user_id == user_id)
            
            if cache_type:
                query = query.filter(CRMCache.cache_type == cache_type)
            
            deleted_count = query.delete()
            self.db.commit()
            
            logger.info(f"Invalidated {deleted_count} cache entries for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            self.db.rollback()
    
    def cleanup_expired_cache(self):
        """Clean up expired cache entries"""
        try:
            deleted_count = self.db.query(CRMCache).filter(
                CRMCache.expires_at < datetime.utcnow()
            ).delete()
            
            self.db.commit()
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired cache entries")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired cache: {e}")
            self.db.rollback()
    
    def is_cache_stale(self, user_id: int, cache_type: str = 'daily') -> bool:
        """Check if cache is stale (older than warning threshold)"""
        try:
            from settings import get_settings
            settings = get_settings()
            
            if not settings.is_cache_warnings_enabled():
                return False
            
            warning_hours = settings.get_cache_warning_age_hours()
            warning_threshold = datetime.utcnow() - timedelta(hours=warning_hours)
            
            cache_entry = self.db.query(CRMCache).filter(
                CRMCache.user_id == user_id,
                CRMCache.cache_type == cache_type,
                CRMCache.expires_at > datetime.utcnow()
            ).first()
            
            if cache_entry:
                return cache_entry.created_at < warning_threshold
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking cache staleness: {e}")
            return False
    
    def get_cache_age_info(self, user_id: int, cache_type: str = 'daily') -> Optional[Dict]:
        """Get detailed cache age information"""
        try:
            cache_entry = self.db.query(CRMCache).filter(
                CRMCache.user_id == user_id,
                CRMCache.cache_type == cache_type
            ).first()
            
            if not cache_entry:
                return None
            
            now = datetime.utcnow()
            age_minutes = int((now - cache_entry.created_at).total_seconds() / 60)
            expires_in_minutes = int((cache_entry.expires_at - now).total_seconds() / 60)
            is_expired = expires_in_minutes <= 0
            is_stale = self.is_cache_stale(user_id, cache_type)
            
            objects_count = len(cache_entry.cache_data) if cache_entry.cache_data else 0
            
            return {
                'user_id': user_id,
                'cache_type': cache_type,
                'created_at': cache_entry.created_at,
                'expires_at': cache_entry.expires_at,
                'age_minutes': age_minutes,
                'expires_in_minutes': expires_in_minutes,
                'is_expired': is_expired,
                'is_stale': is_stale,
                'objects_count': objects_count,
                'last_updated': cache_entry.last_updated
            }
            
        except Exception as e:
            logger.error(f"Error getting cache age info: {e}")
            return None
    
    def cleanup_user_cache_limit(self, user_id: int):
        """Clean up old cache entries if user exceeds limit"""
        try:
            from settings import get_settings
            settings = get_settings()
            max_entries = settings.get_max_cache_entries_per_user()
            
            # Get all cache entries for user ordered by creation time
            entries = self.db.query(CRMCache).filter(
                CRMCache.user_id == user_id
            ).order_by(CRMCache.created_at.desc()).all()
            
            if len(entries) > max_entries:
                # Remove oldest entries
                entries_to_remove = entries[max_entries:]
                for entry in entries_to_remove:
                    self.db.delete(entry)
                
                self.db.commit()
                logger.info(f"Cleaned up {len(entries_to_remove)} old cache entries for user {user_id}")
                
        except Exception as e:
            logger.error(f"Error cleaning up user cache limit: {e}")
            self.db.rollback()
    
    def get_or_fetch_with_staleness_check(self, user_id: int, cache_type: str = 'daily') -> tuple[List[Dict], bool]:
        """Get objects with staleness warning"""
        # Try cache first
        cached_objects = self.get_cached_objects(user_id, cache_type)
        is_stale = False
        
        if cached_objects is not None:
            is_stale = self.is_cache_stale(user_id, cache_type)
            
            # Auto-refresh if enabled and cache is stale
            from settings import get_settings
            settings = get_settings()
            
            if is_stale and settings.is_auto_refresh_on_stale_enabled():
                logger.info(f"Auto-refreshing stale cache for user {user_id}, type {cache_type}")
                
                try:
                    if cache_type == 'daily':
                        fresh_objects = self._fetch_daily_objects()
                        self.set_cached_objects(user_id, fresh_objects, cache_type)
                        return fresh_objects, False
                    elif cache_type == 'all_objects':
                        fresh_objects = self._fetch_all_objects()
                        self.set_cached_objects(user_id, fresh_objects, cache_type)
                        return fresh_objects, False
                except Exception as e:
                    logger.error(f"Auto-refresh failed, using stale cache: {e}")
            
            return cached_objects, is_stale
        
        # Cache miss - fetch fresh data
        logger.info(f"Fetching fresh CRM {cache_type} objects for user {user_id}")
        
        try:
            if cache_type == 'daily':
                objects = self._fetch_daily_objects()
            elif cache_type == 'all_objects':
                objects = self._fetch_all_objects()
            else:
                return [], False
            
            # Cache the results
            self.set_cached_objects(user_id, objects, cache_type)
            
            # Clean up old entries
            self.cleanup_user_cache_limit(user_id)
            
            return objects, False
            
        except Exception as e:
            logger.error(f"Error fetching CRM {cache_type} objects: {e}")
            return [], False
    
    def _fetch_daily_objects(self) -> List[Dict]:
        """Internal method to fetch daily objects from CRM"""
        if not self.crm_client:
            logger.warning("CRM client not available")
            return []
        
        return self.crm_client.get_active_objects()
    
    def _fetch_all_objects(self) -> List[Dict]:
        """Internal method to fetch all objects from CRM"""
        if not self.crm_client:
            logger.warning("CRM client not available")
            return []
        
        return self.crm_client.get_all_objects_without_filters()

# Global cache manager instance
_cache_manager_instance = None

def get_cache_manager(db: Session) -> CRMCacheManager:
    """Get cache manager instance"""
    return CRMCacheManager(db)