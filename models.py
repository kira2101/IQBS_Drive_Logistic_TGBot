from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Boolean, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String(100))
    first_name = Column(String(100))
    last_name = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    work_days = relationship("WorkDay", back_populates="user")
    user_states = relationship("UserState", back_populates="user")

class Project(Base):
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    activities = relationship("Activity", back_populates="project")
    trips = relationship("Trip", back_populates="project")

class WorkDay(Base):
    __tablename__ = 'work_days'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    date = Column(DateTime, nullable=False)
    vehicle = Column(String(100))
    
    user = relationship("User", back_populates="work_days")
    activities = relationship("Activity", back_populates="work_day")
    trips = relationship("Trip", back_populates="work_day")

class UserState(Base):
    __tablename__ = 'user_states'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    state = Column(String(50), nullable=False)  # 'idle', 'driving', 'shopping', 'working'
    data = Column(Text)  # JSON data for state context
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="user_states")

class Activity(Base):
    __tablename__ = 'activities'
    
    id = Column(Integer, primary_key=True)
    work_day_id = Column(Integer, ForeignKey('work_days.id'), nullable=False)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=False)
    activity_type = Column(String(50), nullable=False)  # 'shopping', 'working', 'driving'
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)
    description = Column(Text)
    
    work_day = relationship("WorkDay", back_populates="activities")
    project = relationship("Project", back_populates="activities")

class Trip(Base):
    __tablename__ = 'trips'
    
    id = Column(Integer, primary_key=True)
    work_day_id = Column(Integer, ForeignKey('work_days.id'), nullable=False)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    start_location = Column(String(200))
    end_location = Column(String(200))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    distance_km = Column(Float)
    duration_minutes = Column(Integer)
    
    work_day = relationship("WorkDay", back_populates="trips")
    project = relationship("Project", back_populates="trips")

class ShoppingSession(Base):
    __tablename__ = 'shopping_sessions'
    
    id = Column(Integer, primary_key=True)
    work_day_id = Column(Integer, ForeignKey('work_days.id'), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)
    projects_data = Column(Text)  # JSON list of project IDs
    
    work_day = relationship("WorkDay", back_populates="shopping_sessions")

WorkDay.shopping_sessions = relationship("ShoppingSession", back_populates="work_day")

class FuelPurchase(Base):
    __tablename__ = 'fuel_purchases'
    
    id = Column(Integer, primary_key=True)
    work_day_id = Column(Integer, ForeignKey('work_days.id'), nullable=False)
    odometer_photo_path = Column(String(500))
    receipt_photo_path = Column(String(500))
    odometer_reading = Column(Float)  # Показания одометра
    fuel_liters = Column(Float)       # Литры топлива
    fuel_amount = Column(Float)       # Сумма заправки
    created_at = Column(DateTime, default=datetime.utcnow)
    
    work_day = relationship("WorkDay", back_populates="fuel_purchases")

WorkDay.fuel_purchases = relationship("FuelPurchase", back_populates="work_day")

class IdleTime(Base):
    __tablename__ = 'idle_times'
    
    id = Column(Integer, primary_key=True)
    work_day_id = Column(Integer, ForeignKey('work_days.id'), nullable=False)
    project_ids = Column(Text)  # JSON list of project IDs to distribute idle time
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    work_day = relationship("WorkDay", back_populates="idle_times")

WorkDay.idle_times = relationship("IdleTime", back_populates="work_day")

class WorkingDay(Base):
    __tablename__ = 'working_days'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="working_days")

User.working_days = relationship("WorkingDay", back_populates="user")

class CRMCache(Base):
    __tablename__ = 'crm_cache'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    cache_type = Column(String(50), nullable=False, default='daily')  # 'daily', 'all_objects'
    cache_data = Column(JSON, nullable=False)  # Stored as JSON
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow)