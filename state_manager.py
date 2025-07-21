import json
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from models import UserState, User, Project, WorkDay, Activity, Trip, ShoppingSession
from crm_remonline import get_all_objects

class StateManager:
    def __init__(self, db: Session):
        self.db = db
    
    def get_user_state(self, telegram_id: int) -> Optional[str]:
        state = self.db.query(UserState).filter(
            UserState.user_id == self._get_user_id(telegram_id)
        ).order_by(UserState.created_at.desc()).first()
        
        return state.state if state else 'idle'
    
    def get_user_state_data(self, telegram_id: int) -> Dict:
        state = self.db.query(UserState).filter(
            UserState.user_id == self._get_user_id(telegram_id)
        ).order_by(UserState.created_at.desc()).first()
        
        if state and state.data:
            return json.loads(state.data)
        return {}
    
    def set_user_state(self, telegram_id: int, state: str, data: Dict = None):
        user_id = self._get_user_id(telegram_id)
        
        new_state = UserState(
            user_id=user_id,
            state=state,
            data=json.dumps(data) if data else None
        )
        
        self.db.add(new_state)
        self.db.commit()
    
    def _get_user_id(self, telegram_id: int) -> int:
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id)
            self.db.add(user)
            self.db.commit()
        return user.id
    
    def create_or_get_user(self, telegram_id: int, username: str = None, 
                          first_name: str = None, last_name: str = None) -> User:
        user = self.db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            self.db.add(user)
            self.db.commit()
        
        return user
    
    def get_active_work_day(self, telegram_id: int) -> Optional[WorkDay]:
        user_id = self._get_user_id(telegram_id)
        today = datetime.now().date()
        
        work_day = self.db.query(WorkDay).filter(
            WorkDay.user_id == user_id,
            WorkDay.date >= today,
            WorkDay.end_time.is_(None)
        ).first()
        
        return work_day
    
    def start_work_day(self, telegram_id: int, vehicle: str = None) -> WorkDay:
        user_id = self._get_user_id(telegram_id)
        
        # Check if there's already an active work day
        existing_day = self.get_active_work_day(telegram_id)
        if existing_day:
            return existing_day
        
        work_day = WorkDay(
            user_id=user_id,
            start_time=datetime.now(),
            date=datetime.now().date(),
            vehicle=vehicle
        )
        
        self.db.add(work_day)
        self.db.commit()
        
        self.set_user_state(telegram_id, 'working')
        
        return work_day
    
    def end_work_day(self, telegram_id: int) -> Optional[WorkDay]:
        work_day = self.get_active_work_day(telegram_id)
        if work_day:
            work_day.end_time = datetime.now()
            self.db.commit()
            self.set_user_state(telegram_id, 'idle')
        
        return work_day
    
    def get_projects(self) -> List[Project]:
        return self.db.query(Project).filter(Project.is_active == True).all()
    
    def get_all_objects(self) -> List[Dict]:
        """Get combined list of static and CRM objects"""
        return get_all_objects()
    
    def create_project(self, name: str, description: str = None) -> Project:
        project = Project(name=name, description=description)
        self.db.add(project)
        self.db.commit()
        return project
    
    def start_trip(self, telegram_id: int, destination: str, project_id: int = None):
        self.set_user_state(telegram_id, 'driving', {
            'destination': destination,
            'project_id': project_id,
            'start_time': datetime.now().isoformat()
        })
    
    def end_trip(self, telegram_id: int, distance_km: float) -> Trip:
        state_data = self.get_user_state_data(telegram_id)
        work_day = self.get_active_work_day(telegram_id)
        
        if not work_day or not state_data:
            raise ValueError("No active trip found")
        
        start_time = datetime.fromisoformat(state_data['start_time'])
        end_time = datetime.now()
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        trip = Trip(
            work_day_id=work_day.id,
            project_id=state_data.get('project_id'),
            start_location=state_data.get('start_location', ''),
            end_location=state_data.get('destination', ''),
            start_time=start_time,
            end_time=end_time,
            distance_km=distance_km,
            duration_minutes=duration_minutes
        )
        
        self.db.add(trip)
        self.db.commit()
        
        self.set_user_state(telegram_id, 'idle')
        
        return trip
    
    def start_shopping(self, telegram_id: int, project_ids: List[int]):
        self.set_user_state(telegram_id, 'shopping', {
            'project_ids': project_ids,
            'start_time': datetime.now().isoformat()
        })
    
    def end_shopping(self, telegram_id: int) -> ShoppingSession:
        state_data = self.get_user_state_data(telegram_id)
        work_day = self.get_active_work_day(telegram_id)
        
        if not work_day or not state_data:
            raise ValueError("No active shopping session found")
        
        start_time = datetime.fromisoformat(state_data['start_time'])
        end_time = datetime.now()
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        shopping_session = ShoppingSession(
            work_day_id=work_day.id,
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            projects_data=json.dumps(state_data['project_ids'])
        )
        
        self.db.add(shopping_session)
        self.db.commit()
        
        # Create activities for each project
        project_ids = state_data['project_ids']
        minutes_per_project = duration_minutes // len(project_ids)
        
        for project_id in project_ids:
            activity = Activity(
                work_day_id=work_day.id,
                project_id=project_id,
                activity_type='shopping',
                start_time=start_time,
                end_time=end_time,
                duration_minutes=minutes_per_project
            )
            self.db.add(activity)
        
        self.db.commit()
        self.set_user_state(telegram_id, 'idle')
        
        return shopping_session
    
    def get_last_destination(self, telegram_id: int) -> Optional[str]:
        """Get the last destination from trips"""
        user_id = self._get_user_id(telegram_id)
        work_day = self.get_active_work_day(telegram_id)
        
        if not work_day:
            return None
            
        last_trip = self.db.query(Trip).filter(
            Trip.work_day_id == work_day.id
        ).order_by(Trip.end_time.desc()).first()
        
        return last_trip.end_location if last_trip else None
    
    def get_project_by_name(self, name: str) -> Optional[Project]:
        """Get project by name"""
        return self.db.query(Project).filter(Project.name == name).first()
    
    def get_object_by_name(self, name: str) -> Optional[Dict]:
        """Get object by name from combined list (static + CRM)"""
        all_objects = self.get_all_objects()
        for obj in all_objects:
            if obj['name'] == name:
                return obj
        return None
    
    def get_object_by_name_and_id(self, obj_id: str) -> Optional[Dict]:
        """Get object by ID from combined list (static + CRM)"""
        all_objects = self.get_all_objects()
        for obj in all_objects:
            if str(obj.get('id', '')) == str(obj_id):
                return obj
        return None
    
    def ensure_crm_object_as_project(self, obj_id: str, obj_name: str) -> Project:
        """Create or get project for CRM object"""
        # Try to find existing project by name
        existing_project = self.get_project_by_name(obj_name)
        if existing_project:
            return existing_project
        
        # Create new project for CRM object
        project = Project(
            name=obj_name,
            description=f"CRM объект (ID: {obj_id})"
        )
        self.db.add(project)
        self.db.commit()
        return project

    def start_work(self, telegram_id: int, project_id: int):
        self.set_user_state(telegram_id, 'working', {
            'project_id': project_id,
            'start_time': datetime.now().isoformat()
        })
    
    def end_work(self, telegram_id: int) -> Activity:
        state_data = self.get_user_state_data(telegram_id)
        work_day = self.get_active_work_day(telegram_id)
        
        if not work_day or not state_data:
            raise ValueError("No active work session found")
        
        start_time = datetime.fromisoformat(state_data['start_time'])
        end_time = datetime.now()
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        activity = Activity(
            work_day_id=work_day.id,
            project_id=state_data['project_id'],
            activity_type='working',
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes
        )
        
        self.db.add(activity)
        self.db.commit()
        
        self.set_user_state(telegram_id, 'idle')
        
        return activity
    
    def start_idle_time(self, telegram_id: int, project_ids: List[int]):
        """Start idle time tracking"""
        self.set_user_state(telegram_id, 'idle_tracking', {
            'project_ids': project_ids,
            'start_time': datetime.now().isoformat()
        })
    
    def end_idle_time(self, telegram_id: int):
        """End idle time tracking"""
        from models import IdleTime
        import json
        
        state_data = self.get_user_state_data(telegram_id)
        work_day = self.get_active_work_day(telegram_id)
        
        if not work_day or not state_data:
            raise ValueError("No active idle time session found")
        
        start_time = datetime.fromisoformat(state_data['start_time'])
        end_time = datetime.now()
        duration_minutes = int((end_time - start_time).total_seconds() / 60)
        
        idle_session = IdleTime(
            work_day_id=work_day.id,
            project_ids=json.dumps(state_data['project_ids']),
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes
        )
        
        self.db.add(idle_session)
        self.db.commit()
        
        self.set_user_state(telegram_id, 'idle')
        
        return idle_session
    
    def get_active_working_day(self, telegram_id: int):
        """Get active working day for user"""
        from models import WorkingDay
        
        user_id = self._get_user_id(telegram_id)
        today = datetime.now().date()
        
        working_day = self.db.query(WorkingDay).filter(
            WorkingDay.user_id == user_id,
            WorkingDay.date >= today,
            WorkingDay.end_time.is_(None)
        ).first()
        
        return working_day
    
    def start_working_day(self, telegram_id: int):
        """Start a new working day"""
        from models import WorkingDay
        
        user_id = self._get_user_id(telegram_id)
        
        # Check if there's already an active working day
        existing_day = self.get_active_working_day(telegram_id)
        if existing_day:
            return existing_day
        
        working_day = WorkingDay(
            user_id=user_id,
            start_time=datetime.now(),
            date=datetime.now().date()
        )
        
        self.db.add(working_day)
        self.db.commit()
        
        return working_day
    
    def end_working_day(self, telegram_id: int):
        """End current working day"""
        working_day = self.get_active_working_day(telegram_id)
        if working_day:
            working_day.end_time = datetime.now()
            self.db.commit()
        
        return working_day