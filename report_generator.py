import json
import os
from datetime import datetime
from typing import Dict, List, Tuple
from sqlalchemy.orm import Session
from models import WorkDay, Activity, Trip, ShoppingSession, Project, IdleTime
from crm_remonline import get_crm_client
from fuel_controller import get_fuel_controller
from crm_cache_manager import get_cache_manager

class ReportGenerator:
    def __init__(self, db: Session):
        self.db = db
    
    def generate_daily_report(self, work_day: WorkDay) -> str:
        """Generate a detailed daily report"""
        
        # Get all activities, trips, shopping sessions, and idle times for this work day
        activities = self.db.query(Activity).filter(Activity.work_day_id == work_day.id).all()
        trips = self.db.query(Trip).filter(Trip.work_day_id == work_day.id).all()
        shopping_sessions = self.db.query(ShoppingSession).filter(ShoppingSession.work_day_id == work_day.id).all()
        idle_times = self.db.query(IdleTime).filter(IdleTime.work_day_id == work_day.id).all()
        
        # Calculate totals per project
        project_totals = self._calculate_project_totals(activities, trips, shopping_sessions, idle_times, work_day)
        
        # Calculate fuel consumption for this trip
        fuel_data = self._calculate_trip_fuel_consumption(work_day, trips)
        
        # Generate report
        report = f"*Отчет за {work_day.date.strftime('%d.%m.%Y')}*\n"
        report += f"Автомобиль: {work_day.vehicle or 'Не указан'}\n"
        report += f"Начало: {work_day.start_time.strftime('%H:%M')}\n"
        report += f"Окончание: {work_day.end_time.strftime('%H:%M')}\n\n"
        
        if not project_totals:
            report += "За день не было зарегистрировано активностей.\n"
            return report
        
        report += "*Сводка по проектам:*\n\n"
        
        total_time = 0
        total_distance = 0
        
        for project_id, data in project_totals.items():
            project = self.db.query(Project).filter(Project.id == project_id).first()
            project_name = project.name if project else f"Проект {project_id}"
            
            time_str = self._format_minutes(data['time_minutes'])
            report += f"*{project_name}*\n"
            report += f"  Время: {time_str}\n"
            report += f"  Расстояние: {data['distance_km']:.1f} км\n"
            
            if data['activities']:
                report += f"  Детализация:\n"
                for activity in data['activities']:
                    report += f"    • {activity}\n"
            
            report += "\n"
            
            total_time += data['time_minutes']
            total_distance += data['distance_km']
        
        # Подсчитываем реальное время рейса
        actual_work_time = (work_day.end_time - work_day.start_time).total_seconds() / 60
        # Подсчитываем общее расстояние из всех поездок  
        actual_total_distance = sum(trip.distance_km for trip in trips if trip.distance_km)
        
        report += f"*Итого:*\n"
        report += f"Общее время: {self._format_minutes(actual_work_time)}\n"
        report += f"Общее расстояние: {actual_total_distance:.1f} км\n"
        
        # Add fuel consumption information
        if fuel_data and fuel_data.get('fuel_consumed_liters', 0) > 0:
            report += f"\n*Расход топлива:*\n"
            report += f"Потрачено топлива: {fuel_data['fuel_consumed_liters']:.1f} л\n"
            report += f"Стоимость топлива: {fuel_data['trip_fuel_cost']:.2f} грн\n"
            report += f"Остаток топлива: {fuel_data['fuel_after_liters']:.1f} л\n"
        
        return report
    
    def _calculate_project_totals(self, activities: List[Activity], trips: List[Trip], 
                                 shopping_sessions: List[ShoppingSession], idle_times: List[IdleTime],
                                 work_day: WorkDay = None) -> Dict[int, Dict]:
        """Рассчитать итоги по проекту с правильным распределением затрат"""
        
        project_totals = {}
        fuel_controller = get_fuel_controller()
        
        # Получаем стоимость часа работы
        from settings import get_settings
        settings = get_settings()
        price_per_hour = settings.get_price_per_hour()
        
        # Add activities (work and shopping time)
        for activity in activities:
            if activity.project_id not in project_totals:
                project_totals[activity.project_id] = {
                    'time_minutes': 0,
                    'distance_km': 0.0,
                    'fuel_consumed_liters': 0.0,
                    'fuel_cost': 0.0,
                    'time_cost': 0.0,
                    'activities': []
                }
            
            project_totals[activity.project_id]['time_minutes'] += activity.duration_minutes
            project_totals[activity.project_id]['time_cost'] += (activity.duration_minutes / 60.0) * price_per_hour
            
            activity_type = 'Работа' if activity.activity_type == 'working' else 'Закупка'
            time_range = f"{activity.start_time.strftime('%H:%M')}-{activity.end_time.strftime('%H:%M')}" if activity.end_time else f"{activity.start_time.strftime('%H:%M')}-"
            project_totals[activity.project_id]['activities'].append(
                f"{activity_type}: {time_range} ({self._format_minutes(activity.duration_minutes)})"
            )
        
        # Add trips
        for trip in trips:
            if trip.project_id:
                if trip.project_id not in project_totals:
                    project_totals[trip.project_id] = {
                        'time_minutes': 0,
                        'distance_km': 0.0,
                        'fuel_consumed_liters': 0.0,
                        'fuel_cost': 0.0,
                        'time_cost': 0.0,
                        'activities': []
                    }
                
                project_totals[trip.project_id]['time_minutes'] += trip.duration_minutes
                project_totals[trip.project_id]['distance_km'] += trip.distance_km
                project_totals[trip.project_id]['time_cost'] += (trip.duration_minutes / 60.0) * price_per_hour
                
                # Рассчитываем топливо для этой поездки
                if work_day and work_day.vehicle and trip.distance_km > 0:
                    trip_fuel_consumed = fuel_controller.calculate_fuel_consumption(work_day.vehicle, trip.distance_km)
                    trip_fuel_cost = trip_fuel_consumed * fuel_controller.calculate_average_fuel_price_per_liter(work_day.vehicle)
                    
                    project_totals[trip.project_id]['fuel_consumed_liters'] += trip_fuel_consumed
                    project_totals[trip.project_id]['fuel_cost'] += trip_fuel_cost
                
                trip_time_range = f"{trip.start_time.strftime('%H:%M')}-{trip.end_time.strftime('%H:%M')}" if trip.end_time else f"{trip.start_time.strftime('%H:%M')}-"
                project_totals[trip.project_id]['activities'].append(
                    f"Поездка до {trip.end_location}: {trip_time_range} ({self._format_minutes(trip.duration_minutes)}, {trip.distance_km:.1f} км)"
                )
        
        # Handle trips to shop - distribute among shopping projects
        shop_trips = [t for t in trips if not t.project_id and 'Магазин' in (t.end_location or '')]
        
        for trip in shop_trips:
            # Find shopping sessions to determine which projects to distribute to
            shopping_projects = set()
            for session in shopping_sessions:
                if session.projects_data:
                    project_ids = json.loads(session.projects_data)
                    shopping_projects.update(project_ids)
            
            if shopping_projects:
                # Распределяем время, расстояние и топливо поровну между проектами для закупок
                time_per_project = trip.duration_minutes / len(shopping_projects)
                distance_per_project = trip.distance_km / len(shopping_projects)
                
                # Рассчитываем топливо для магазинной поездки
                trip_fuel_consumed = 0
                trip_fuel_cost = 0
                if work_day and work_day.vehicle and trip.distance_km > 0:
                    trip_fuel_consumed = fuel_controller.calculate_fuel_consumption(work_day.vehicle, trip.distance_km)
                    trip_fuel_cost = trip_fuel_consumed * fuel_controller.calculate_average_fuel_price_per_liter(work_day.vehicle)
                
                fuel_per_project = trip_fuel_consumed / len(shopping_projects)
                fuel_cost_per_project = trip_fuel_cost / len(shopping_projects)
                time_cost_per_project = (time_per_project / 60.0) * price_per_hour
                
                for project_id in shopping_projects:
                    if project_id not in project_totals:
                        project_totals[project_id] = {
                            'time_minutes': 0,
                            'distance_km': 0.0,
                            'fuel_consumed_liters': 0.0,
                            'fuel_cost': 0.0,
                            'time_cost': 0.0,
                            'activities': []
                        }
                    
                    project_totals[project_id]['time_minutes'] += time_per_project
                    project_totals[project_id]['distance_km'] += distance_per_project
                    project_totals[project_id]['fuel_consumed_liters'] += fuel_per_project
                    project_totals[project_id]['fuel_cost'] += fuel_cost_per_project
                    project_totals[project_id]['time_cost'] += time_cost_per_project
                    
                    trip_time_range = f"{trip.start_time.strftime('%H:%M')}-{trip.end_time.strftime('%H:%M')}" if trip.end_time else f"{trip.start_time.strftime('%H:%M')}-"
                    project_totals[project_id]['activities'].append(
                        f"Поездка до магазина (доля): {trip_time_range} ({self._format_minutes(time_per_project)}, {distance_per_project:.1f} км)"
                    )
        
        # Handle trips to home and warehouse - distribute among active projects
        home_warehouse_trips = [t for t in trips if not t.project_id and 
                               (('Дом' in (t.end_location or '')) or ('Склад' in (t.end_location or '')))]
        
        for trip in home_warehouse_trips:
            # Get active projects ТОЛЬКО для этого конкретного work_day (машины)
            # Поездки домой должны распределяться только среди проектов той же машины
            active_projects = set()
            
            # Получаем проекты только из переданных данных (уже отфильтрованы по work_day)
            # Add projects from activities
            for activity in activities:
                if activity.project_id:
                    active_projects.add(activity.project_id)
            
            # Add projects from trips (excluding home/warehouse/fuel trips)
            for t in trips:
                if t.project_id:
                    active_projects.add(t.project_id)
            
            # Add projects from shopping sessions
            for session in shopping_sessions:
                if session.projects_data:
                    project_ids = json.loads(session.projects_data)
                    active_projects.update(project_ids)
            
            if active_projects:
                # Распределяем время, расстояние и топливо поровну между активными проектами
                time_per_project = trip.duration_minutes / len(active_projects)
                distance_per_project = trip.distance_km / len(active_projects)
                
                # Рассчитываем топливо для поездки домой/на склад
                trip_fuel_consumed = 0
                trip_fuel_cost = 0
                if work_day and work_day.vehicle and trip.distance_km > 0:
                    trip_fuel_consumed = fuel_controller.calculate_fuel_consumption(work_day.vehicle, trip.distance_km)
                    trip_fuel_cost = trip_fuel_consumed * fuel_controller.calculate_average_fuel_price_per_liter(work_day.vehicle)
                
                fuel_per_project = trip_fuel_consumed / len(active_projects)
                fuel_cost_per_project = trip_fuel_cost / len(active_projects)
                time_cost_per_project = (time_per_project / 60.0) * price_per_hour
                
                destination_name = "дома" if 'Дом' in trip.end_location else "склада"
                
                for project_id in active_projects:
                    if project_id not in project_totals:
                        project_totals[project_id] = {
                            'time_minutes': 0,
                            'distance_km': 0.0,
                            'fuel_consumed_liters': 0.0,
                            'fuel_cost': 0.0,
                            'time_cost': 0.0,
                            'activities': []
                        }
                    
                    project_totals[project_id]['time_minutes'] += time_per_project
                    project_totals[project_id]['distance_km'] += distance_per_project
                    project_totals[project_id]['fuel_consumed_liters'] += fuel_per_project
                    project_totals[project_id]['fuel_cost'] += fuel_cost_per_project
                    project_totals[project_id]['time_cost'] += time_cost_per_project
                    
                    trip_time_range = f"{trip.start_time.strftime('%H:%M')}-{trip.end_time.strftime('%H:%M')}" if trip.end_time else f"{trip.start_time.strftime('%H:%M')}-"
                    project_totals[project_id]['activities'].append(
                        f"Поездка до {destination_name} (доля): {trip_time_range} ({self._format_minutes(time_per_project)}, {distance_per_project:.1f} км)"
                    )
        
        # Handle trips to fuel station - distribute among ALL available projects for the day
        fuel_station_trips = [t for t in trips if not t.project_id and 'Заправка' in (t.end_location or '')]
        
        for trip in fuel_station_trips:
            # Get available projects ТОЛЬКО для этого конкретного work_day (машины)
            all_available_projects = set()
            
            # Получаем проекты только из переданных данных (уже отфильтрованы по work_day)
            # Add projects from activities
            for activity in activities:
                if activity.project_id:
                    all_available_projects.add(activity.project_id)
            
            # Add projects from trips (excluding static object trips)
            for t in trips:
                if t.project_id:
                    all_available_projects.add(t.project_id)
            
            # Add projects from shopping sessions
            for session in shopping_sessions:
                if session.projects_data:
                    project_ids = json.loads(session.projects_data)
                    all_available_projects.update(project_ids)
            
            # Add projects from idle times
            for idle_time in idle_times:
                if idle_time.project_ids:
                    project_ids = json.loads(idle_time.project_ids)
                    all_available_projects.update(project_ids)
            
            if all_available_projects:
                # Распределяем время, расстояние и топливо поровну между всеми доступными проектами
                time_per_project = trip.duration_minutes / len(all_available_projects)
                distance_per_project = trip.distance_km / len(all_available_projects)
                
                # Рассчитываем топливо для поездки на заправку
                trip_fuel_consumed = 0
                trip_fuel_cost = 0
                if work_day and work_day.vehicle and trip.distance_km > 0:
                    trip_fuel_consumed = fuel_controller.calculate_fuel_consumption(work_day.vehicle, trip.distance_km)
                    trip_fuel_cost = trip_fuel_consumed * fuel_controller.calculate_average_fuel_price_per_liter(work_day.vehicle)
                
                fuel_per_project = trip_fuel_consumed / len(all_available_projects)
                fuel_cost_per_project = trip_fuel_cost / len(all_available_projects)
                time_cost_per_project = (time_per_project / 60.0) * price_per_hour
                
                for project_id in all_available_projects:
                    if project_id not in project_totals:
                        project_totals[project_id] = {
                            'time_minutes': 0,
                            'distance_km': 0.0,
                            'fuel_consumed_liters': 0.0,
                            'fuel_cost': 0.0,
                            'time_cost': 0.0,
                            'activities': []
                        }
                    
                    project_totals[project_id]['time_minutes'] += time_per_project
                    project_totals[project_id]['distance_km'] += distance_per_project
                    project_totals[project_id]['fuel_consumed_liters'] += fuel_per_project
                    project_totals[project_id]['fuel_cost'] += fuel_cost_per_project
                    project_totals[project_id]['time_cost'] += time_cost_per_project
                    
                    trip_time_range = f"{trip.start_time.strftime('%H:%M')}-{trip.end_time.strftime('%H:%M')}" if trip.end_time else f"{trip.start_time.strftime('%H:%M')}-"
                    project_totals[project_id]['activities'].append(
                        f"Поездка на заправку (доля): {trip_time_range} ({self._format_minutes(time_per_project)}, {distance_per_project:.1f} км)"
                    )
        
        # Add idle times
        for idle_time in idle_times:
            if idle_time.project_ids:
                project_ids = json.loads(idle_time.project_ids)
                if project_ids:
                    # Distribute idle time equally among projects
                    time_per_project = idle_time.duration_minutes / len(project_ids)
                    time_cost_per_project = (time_per_project / 60.0) * price_per_hour
                    
                    for project_id in project_ids:
                        if project_id not in project_totals:
                            project_totals[project_id] = {
                                'time_minutes': 0,
                                'distance_km': 0.0,
                                'fuel_consumed_liters': 0.0,
                                'fuel_cost': 0.0,
                                'time_cost': 0.0,
                                'activities': []
                            }
                        
                        project_totals[project_id]['time_minutes'] += time_per_project
                        project_totals[project_id]['time_cost'] += time_cost_per_project
                        idle_time_range = f"{idle_time.start_time.strftime('%H:%M')}-{idle_time.end_time.strftime('%H:%M')}" if idle_time.end_time else f"{idle_time.start_time.strftime('%H:%M')}-"
                        project_totals[project_id]['activities'].append(
                            f"Простой: {idle_time_range} ({self._format_minutes(time_per_project)})"
                        )
        
        return project_totals
    
    def _format_minutes(self, minutes: float) -> str:
        """Format minutes as 'часов минут'"""
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        if hours > 0:
            return f"{hours}ч {mins:02d}мин"
        else:
            return f"{mins}мин"
    
    def generate_day_report(self, work_days: List[WorkDay]) -> str:
        """Generate comprehensive report for all trips in a day"""
        if not work_days:
            return "Нет рейсов за день."
        
        report = f"*Отчет за день {work_days[0].date.strftime('%d.%m.%Y')}*\n\n"
        
        total_time = 0
        total_distance = 0
        project_totals = {}
        vehicle_totals = {}
        vehicle_projects = {}  # Track which projects each vehicle worked on
        total_idle_time = 0
        
        # Process each trip
        for i, work_day in enumerate(work_days, 1):
            if work_day.end_time:
                trip_time = (work_day.end_time - work_day.start_time).total_seconds() / 60
                total_time += trip_time
                
                # Get all data for this trip
                activities = self.db.query(Activity).filter(Activity.work_day_id == work_day.id).all()
                trips = self.db.query(Trip).filter(Trip.work_day_id == work_day.id).all()
                shopping_sessions = self.db.query(ShoppingSession).filter(ShoppingSession.work_day_id == work_day.id).all()
                idle_times = self.db.query(IdleTime).filter(IdleTime.work_day_id == work_day.id).all()
                
                trip_distance = sum(trip.distance_km for trip in trips if trip.distance_km)
                total_distance += trip_distance
                
                # Calculate project totals for this trip
                trip_project_totals = self._calculate_project_totals(activities, trips, shopping_sessions, idle_times, work_day)
                
                # Accumulate project totals across all trips
                for project_id, data in trip_project_totals.items():
                    if project_id not in project_totals:
                        project_totals[project_id] = {
                            'time_minutes': 0,
                            'distance_km': 0.0
                        }
                    project_totals[project_id]['time_minutes'] += data['time_minutes']
                    project_totals[project_id]['distance_km'] += data['distance_km']
                
                # Vehicle totals
                vehicle = work_day.vehicle or 'Не указан'
                if vehicle not in vehicle_totals:
                    vehicle_totals[vehicle] = {
                        'time_minutes': 0,
                        'distance_km': 0.0,
                        'trips_count': 0
                    }
                    vehicle_projects[vehicle] = {}
                
                vehicle_totals[vehicle]['time_minutes'] += trip_time
                vehicle_totals[vehicle]['distance_km'] += trip_distance
                vehicle_totals[vehicle]['trips_count'] += 1
                
                # Track projects for this vehicle
                for project_id, data in trip_project_totals.items():
                    if project_id not in vehicle_projects[vehicle]:
                        vehicle_projects[vehicle][project_id] = {
                            'time_minutes': 0,
                            'distance_km': 0.0
                        }
                    vehicle_projects[vehicle][project_id]['time_minutes'] += data['time_minutes']
                    vehicle_projects[vehicle][project_id]['distance_km'] += data['distance_km']
                
                # Accumulate idle time
                for idle_time in idle_times:
                    total_idle_time += idle_time.duration_minutes
                
                # Trip summary
                report += f"*Рейс {i}:* {vehicle}\n"
                report += f"Время: {work_day.start_time.strftime('%H:%M')} - {work_day.end_time.strftime('%H:%M')} ({self._format_minutes(trip_time)})\n"
                report += f"Расстояние: {trip_distance:.1f} км\n\n"
        
        # Summary by projects
        if project_totals:
            report += f"*Сводка по объектам:*\n"
            for project_id, data in project_totals.items():
                project = self.db.query(Project).filter(Project.id == project_id).first()
                project_name = project.name if project else f"Проект {project_id}"
                time_str = self._format_minutes(data['time_minutes'])
                
                # Calculate total fuel consumption for this project across all vehicles
                project_total_fuel = 0
                project_total_cost = 0
                if data['distance_km'] > 0:
                    # For simplicity, calculate using first available vehicle from the day
                    sample_vehicle = None
                    for work_day in work_days:
                        if work_day.vehicle:
                            sample_vehicle = work_day.vehicle
                            break
                    
                    if sample_vehicle:
                        fuel_controller = get_fuel_controller()
                        project_total_fuel = fuel_controller.calculate_fuel_consumption(sample_vehicle, data['distance_km'])
                        average_price = fuel_controller.calculate_average_fuel_price_per_liter(sample_vehicle)
                        project_total_cost = project_total_fuel * average_price
                
                report += f"{project_name}: {time_str}, {data['distance_km']:.1f} км"
                if project_total_fuel > 0:
                    report += f", топливо: {project_total_fuel:.1f} л ({project_total_cost:.2f} грн)"
                report += "\n"
            report += "\n"
        
        # Total idle time
        if total_idle_time > 0:
            report += f"*Общий простой:* {self._format_minutes(total_idle_time)}\n\n"
        
        # Calculate total fuel consumption for the day
        total_fuel_data = self._calculate_day_fuel_consumption(work_days)
        
        # Detailed summary by vehicles
        if vehicle_totals:
            report += f"*Детальная сводка по машинам:*\n"
            for vehicle, data in vehicle_totals.items():
                time_str = self._format_minutes(data['time_minutes'])
                report += f"*{vehicle}:* {data['trips_count']} рейс(ов), {time_str}, {data['distance_km']:.1f} км\n"
                
                # Add fuel consumption data for this vehicle
                if vehicle in total_fuel_data and total_fuel_data[vehicle].get('fuel_consumed_liters', 0) > 0:
                    fuel_info = total_fuel_data[vehicle]
                    report += f"  Расход топлива: {fuel_info['fuel_consumed_liters']:.1f} л, стоимость: {fuel_info['total_fuel_cost']:.2f} грн\n"
                    report += f"  Остаток топлива: {fuel_info['fuel_after_liters']:.1f} л\n"
                
                # Show which objects this vehicle worked on
                if vehicle in vehicle_projects and vehicle_projects[vehicle]:
                    report += f"  Объекты:\n"
                    for project_id, project_data in vehicle_projects[vehicle].items():
                        project = self.db.query(Project).filter(Project.id == project_id).first()
                        project_name = project.name if project else f"Проект {project_id}"
                        project_time_str = self._format_minutes(project_data['time_minutes'])
                        
                        # Calculate fuel consumption for this project
                        project_fuel_consumed = 0
                        project_fuel_cost = 0
                        if vehicle in total_fuel_data and project_data['distance_km'] > 0:
                            fuel_controller = get_fuel_controller()
                            project_fuel_consumed = fuel_controller.calculate_fuel_consumption(vehicle, project_data['distance_km'])
                            average_price = fuel_controller.calculate_average_fuel_price_per_liter(vehicle)
                            project_fuel_cost = project_fuel_consumed * average_price
                        
                        report += f"    • {project_name}: {project_time_str}, {project_data['distance_km']:.1f} км"
                        if project_fuel_consumed > 0:
                            report += f", топливо: {project_fuel_consumed:.1f} л ({project_fuel_cost:.2f} грн)"
                        report += "\n"
                report += "\n"
        
        # Overall totals
        report += f"*Итого за день:*\n"
        report += f"Общее время: {self._format_minutes(total_time)}\n"
        report += f"Общее расстояние: {total_distance:.1f} км\n"
        
        # Add daily fuel consumption summary
        if total_fuel_data:
            report += f"\n*Расход топлива за день:*\n"
            for vehicle, fuel_info in total_fuel_data.items():
                if fuel_info.get('fuel_consumed_liters', 0) > 0:
                    report += f"{vehicle}: {fuel_info['fuel_consumed_liters']:.1f} л, {fuel_info['total_fuel_cost']:.2f} грн\n"
                    report += f"  Остаток: {fuel_info['fuel_after_liters']:.1f} л\n"
        
        return report

    def generate_weekly_report(self, user_id: int, week_start: datetime) -> str:
        """Generate weekly report for a user"""
        # Implementation for weekly reports
        pass
    
    def generate_project_report(self, project_id: int, start_date: datetime, end_date: datetime) -> str:
        """Generate report for a specific project"""
        # Implementation for project-specific reports
        pass
    
    def get_day_report_data(self, work_days: List[WorkDay]) -> dict:
        """Get comprehensive day report data as dictionary (for webhook sending)"""
        if not work_days:
            return {}
        
        return self._build_day_report_data(work_days)
    
    def _build_day_report_data(self, work_days: List[WorkDay]) -> dict:
        """Build comprehensive day report data structure"""
        json_data = {
            "report_type": "day_report",
            "report_date": work_days[0].date.strftime('%Y-%m-%d'),
            "user_id": work_days[0].user_id,
            "total_trips": len(work_days),
            "trips": []
        }
        
        total_time = 0
        total_distance = 0
        all_project_totals = {}
        vehicle_totals = {}
        total_idle_time = 0
        
        for work_day in work_days:
            if work_day.end_time:
                trip_time = (work_day.end_time - work_day.start_time).total_seconds() / 60
                total_time += trip_time
                
                # Get all data for this work day
                activities = self.db.query(Activity).filter(Activity.work_day_id == work_day.id).all()
                trips = self.db.query(Trip).filter(Trip.work_day_id == work_day.id).all()
                shopping_sessions = self.db.query(ShoppingSession).filter(ShoppingSession.work_day_id == work_day.id).all()
                idle_times = self.db.query(IdleTime).filter(IdleTime.work_day_id == work_day.id).all()
                
                trip_distance = sum(trip.distance_km for trip in trips if trip.distance_km)
                total_distance += trip_distance
                
                # Calculate project totals for this trip
                project_totals = self._calculate_project_totals(activities, trips, shopping_sessions, idle_times, work_day)
                
                # Calculate fuel consumption for this trip
                trip_fuel_data = self._calculate_trip_fuel_consumption(work_day, trips)
                
                # Prepare trip data with all details
                trip_data = {
                    "trip_id": work_day.id,
                    "vehicle": work_day.vehicle,
                    "start_time": work_day.start_time.isoformat(),
                    "end_time": work_day.end_time.isoformat(),
                    "duration_minutes": trip_time,
                    "distance_km": trip_distance,
                    "fuel_consumption": trip_fuel_data,
                    "project_totals": {},
                    "activities": [],
                    "trips": [],
                    "shopping_sessions": [],
                    "idle_times": []
                }
                
                # Get bulk CRM metadata for all projects (optimization)
                project_ids = list(project_totals.keys())
                bulk_crm_metadata = self._get_bulk_crm_metadata_for_projects(project_ids, work_day.user_id)
                
                # Add project totals with names
                for project_id, data in project_totals.items():
                    project = self.db.query(Project).filter(Project.id == project_id).first()
                    project_name = project.name if project else f"Project {project_id}"
                    # Get CRM metadata from bulk fetch
                    crm_metadata = bulk_crm_metadata.get(project_id, {"source": "static"})
                    
                    trip_data["project_totals"][project_name] = {
                        "project_id": project_id,
                        "time_minutes": data['time_minutes'],
                        "distance_km": data['distance_km'],
                        "fuel_consumed_liters": data.get('fuel_consumed_liters', 0.0),
                        "fuel_cost": data.get('fuel_cost', 0.0),
                        "time_cost": data.get('time_cost', 0.0),
                        "activities_summary": data['activities'],
                        "crm_metadata": crm_metadata
                    }
                    
                    # Accumulate for day totals
                    if project_name not in all_project_totals:
                        all_project_totals[project_name] = {
                            "project_id": project_id,
                            "time_minutes": 0,
                            "distance_km": 0,
                            "fuel_consumed_liters": 0.0,
                            "fuel_cost": 0.0,
                            "time_cost": 0.0,
                            "activities_summary": [],
                            "crm_metadata": crm_metadata
                        }
                    all_project_totals[project_name]["time_minutes"] += data['time_minutes']
                    all_project_totals[project_name]["distance_km"] += data['distance_km']
                    all_project_totals[project_name]["fuel_consumed_liters"] += data.get('fuel_consumed_liters', 0.0)
                    all_project_totals[project_name]["fuel_cost"] += data.get('fuel_cost', 0.0)
                    all_project_totals[project_name]["time_cost"] += data.get('time_cost', 0.0)
                    all_project_totals[project_name]["activities_summary"].extend(data['activities'])
                
                # Vehicle totals
                vehicle = work_day.vehicle or 'Не указан'
                if vehicle not in vehicle_totals:
                    vehicle_totals[vehicle] = {
                        "time_minutes": 0,
                        "distance_km": 0,
                        "trips_count": 0
                    }
                vehicle_totals[vehicle]["time_minutes"] += trip_time
                vehicle_totals[vehicle]["distance_km"] += trip_distance
                vehicle_totals[vehicle]["trips_count"] += 1
                
                # Accumulate idle time
                for idle_time in idle_times:
                    total_idle_time += idle_time.duration_minutes
                
                # Add detailed activities
                for activity in activities:
                    project = self.db.query(Project).filter(Project.id == activity.project_id).first()
                    trip_data["activities"].append({
                        "id": activity.id,
                        "project_id": activity.project_id,
                        "project_name": project.name if project else f"Project {activity.project_id}",
                        "activity_type": activity.activity_type,
                        "start_time": activity.start_time.isoformat(),
                        "end_time": activity.end_time.isoformat() if activity.end_time else None,
                        "duration_minutes": activity.duration_minutes,
                        "description": activity.description
                    })
                
                # Add detailed trips
                for trip in trips:
                    project = None
                    if trip.project_id:
                        project = self.db.query(Project).filter(Project.id == trip.project_id).first()
                    
                    trip_data["trips"].append({
                        "id": trip.id,
                        "project_id": trip.project_id,
                        "project_name": project.name if project else None,
                        "start_location": trip.start_location,
                        "end_location": trip.end_location,
                        "start_time": trip.start_time.isoformat(),
                        "end_time": trip.end_time.isoformat() if trip.end_time else None,
                        "distance_km": trip.distance_km,
                        "duration_minutes": trip.duration_minutes
                    })
                
                # Add shopping sessions
                for session in shopping_sessions:
                    project_ids = json.loads(session.projects_data) if session.projects_data else []
                    project_names = []
                    for pid in project_ids:
                        if pid == 'warehouse':
                            project_names.append('Склад')
                        else:
                            project = self.db.query(Project).filter(Project.id == pid).first()
                            project_names.append(project.name if project else f"Project {pid}")
                    
                    trip_data["shopping_sessions"].append({
                        "id": session.id,
                        "project_ids": project_ids,
                        "project_names": project_names,
                        "start_time": session.start_time.isoformat(),
                        "end_time": session.end_time.isoformat() if session.end_time else None,
                        "duration_minutes": session.duration_minutes
                    })
                
                # Add idle times
                for idle_time in idle_times:
                    project_ids = json.loads(idle_time.project_ids) if idle_time.project_ids else []
                    project_names = []
                    for pid in project_ids:
                        project = self.db.query(Project).filter(Project.id == pid).first()
                        project_names.append(project.name if project else f"Project {pid}")
                    
                    trip_data["idle_times"].append({
                        "id": idle_time.id,
                        "project_ids": project_ids,
                        "project_names": project_names,
                        "start_time": idle_time.start_time.isoformat(),
                        "end_time": idle_time.end_time.isoformat() if idle_time.end_time else None,
                        "duration_minutes": idle_time.duration_minutes
                    })
                
                json_data["trips"].append(trip_data)
        
        # Calculate fuel data for JSON report
        fuel_data_for_json = self._calculate_day_fuel_consumption(work_days)
        
        # Add day totals
        json_data["totals"] = {
            "total_time_minutes": total_time,
            "total_distance_km": total_distance,
            "total_idle_time_minutes": total_idle_time,
            "project_totals": all_project_totals,
            "vehicle_totals": vehicle_totals,
            "fuel_consumption_by_vehicle": fuel_data_for_json
        }
        
        # Создать секцию for_excel для экспорта
        json_data["for_excel"] = self._build_for_excel_section(all_project_totals, work_days)
        
        return json_data
    
    def save_day_report_json(self, work_days: List[WorkDay]):
        """Save comprehensive day report with all trips and details as JSON"""
        try:
            if not work_days:
                return
            
            # Create reports directory if it doesn't exist
            reports_dir = "reports"
            if not os.path.exists(reports_dir):
                os.makedirs(reports_dir)
            
            # Get report data
            json_data = self._build_day_report_data(work_days)
            
            # Save to file
            filename = f"day_report_{work_days[0].date.strftime('%Y%m%d')}.json"
            filepath = os.path.join(reports_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Warning: Failed to save day report JSON: {e}")
    
    def _get_crm_metadata_for_project(self, project: Project) -> Dict:
        """Get CRM metadata for a project if it's from CRM"""
        if not project:
            return {}
        
        # Check if project description indicates it's from CRM
        if project.description and "CRM объект" in project.description:
            try:
                # Extract CRM ID from description
                import re
                match = re.search(r'ID: ([^)]+)', project.description)
                if match:
                    crm_id = match.group(1)
                    
                    # Try to get fresh data from CRM
                    crm_client = get_crm_client()
                    if crm_client:
                        crm_objects = crm_client.get_active_objects()
                        for obj in crm_objects:
                            if str(obj.get('id')) == str(crm_id):
                                return {
                                    "source": "remonline",
                                    "crm_id": obj.get('id'),
                                    "id_label": obj.get('id_label'),
                                    "status_name": obj.get('status_name'),
                                    "status_id": obj.get('status_id'),
                                    "created_at": obj.get('created_at')
                                }
            except Exception as e:
                print(f"Warning: Failed to get CRM metadata: {e}")
        
        return {"source": "static"}
    
    def _get_bulk_crm_metadata_for_projects(self, project_ids: List[int], user_id: int) -> Dict[int, Dict]:
        """Get CRM metadata for multiple projects in a single optimized operation"""
        try:
            # Use cache manager for bulk metadata fetching
            cache_manager = get_cache_manager(self.db)
            return cache_manager.get_bulk_crm_metadata(user_id, project_ids)
        except Exception as e:
            logger.error(f"Error getting bulk CRM metadata: {e}")
            # Fallback: return static metadata for all projects
            return {project_id: {"source": "static"} for project_id in project_ids}
    
    def _calculate_trip_fuel_consumption(self, work_day: WorkDay, trips: List[Trip]) -> Dict:
        """Calculate fuel consumption for a single trip"""
        if not work_day.vehicle or not trips:
            return {}
        
        fuel_controller = get_fuel_controller()
        total_distance = sum(trip.distance_km for trip in trips if trip.distance_km)
        
        if total_distance <= 0:
            return {}
        
        # Calculate expected fuel consumption
        fuel_consumed_liters = fuel_controller.calculate_fuel_consumption(work_day.vehicle, total_distance)
        average_price_per_liter = fuel_controller.calculate_average_fuel_price_per_liter(work_day.vehicle)
        trip_fuel_cost = fuel_consumed_liters * average_price_per_liter
        
        # Get current fuel status
        fuel_status = fuel_controller.check_fuel_status(work_day.vehicle)
        
        return {
            'fuel_consumed_liters': fuel_consumed_liters,
            'trip_fuel_cost': trip_fuel_cost,
            'average_price_per_liter': average_price_per_liter,
            'fuel_after_liters': fuel_status.get('current_fuel_liters', 0),
            'vehicle': work_day.vehicle
        }
    
    def _calculate_day_fuel_consumption(self, work_days: List[WorkDay]) -> Dict[str, Dict]:
        """Calculate total fuel consumption per vehicle for all trips in a day"""
        fuel_controller = get_fuel_controller()
        vehicle_fuel_data = {}
        
        for work_day in work_days:
            if not work_day.vehicle:
                continue
            
            # Get trips for this work day
            trips = self.db.query(Trip).filter(Trip.work_day_id == work_day.id).all()
            total_distance = sum(trip.distance_km for trip in trips if trip.distance_km)
            
            if total_distance <= 0:
                continue
            
            vehicle = work_day.vehicle
            if vehicle not in vehicle_fuel_data:
                vehicle_fuel_data[vehicle] = {
                    'fuel_consumed_liters': 0,
                    'total_fuel_cost': 0,
                    'total_distance': 0
                }
            
            # Calculate fuel consumption for this trip
            fuel_consumed = fuel_controller.calculate_fuel_consumption(vehicle, total_distance)
            average_price = fuel_controller.calculate_average_fuel_price_per_liter(vehicle)
            trip_cost = fuel_consumed * average_price
            
            vehicle_fuel_data[vehicle]['fuel_consumed_liters'] += fuel_consumed
            vehicle_fuel_data[vehicle]['total_fuel_cost'] += trip_cost
            vehicle_fuel_data[vehicle]['total_distance'] += total_distance
        
        # Add current fuel levels
        for vehicle in vehicle_fuel_data.keys():
            fuel_status = fuel_controller.check_fuel_status(vehicle)
            vehicle_fuel_data[vehicle]['fuel_after_liters'] = fuel_status.get('current_fuel_liters', 0)
        
        return vehicle_fuel_data
    
    def _build_for_excel_section(self, all_project_totals: Dict, work_days: List[WorkDay]) -> List[Dict]:
        """Создать секцию for_excel с данными для экспорта в Excel"""
        excel_data = []
        
        # Получаем данные по машинам для каждого проекта только для текущего дня
        vehicle_project_data = {}
        
        for work_day in work_days:
            if not work_day.vehicle:
                continue
                
            # Получаем данные для этого рабочего дня
            activities = self.db.query(Activity).filter(Activity.work_day_id == work_day.id).all()
            trips = self.db.query(Trip).filter(Trip.work_day_id == work_day.id).all()
            shopping_sessions = self.db.query(ShoppingSession).filter(ShoppingSession.work_day_id == work_day.id).all()
            idle_times = self.db.query(IdleTime).filter(IdleTime.work_day_id == work_day.id).all()
            
            # Получаем итоги по проектам для этой машины
            project_totals = self._calculate_project_totals(activities, trips, shopping_sessions, idle_times, work_day)
            
            for project_id, data in project_totals.items():
                if project_id not in vehicle_project_data:
                    vehicle_project_data[project_id] = {}
                
                vehicle = work_day.vehicle
                if vehicle not in vehicle_project_data[project_id]:
                    vehicle_project_data[project_id][vehicle] = {
                        'time_minutes': 0,
                        'fuel_cost': 0.0,
                        'time_cost': 0.0
                    }
                
                vehicle_project_data[project_id][vehicle]['time_minutes'] += data.get('time_minutes', 0)
                vehicle_project_data[project_id][vehicle]['fuel_cost'] += data.get('fuel_cost', 0.0)
                vehicle_project_data[project_id][vehicle]['time_cost'] += data.get('time_cost', 0.0)
        
        # Создаем записи для Excel
        for project_name, project_data in all_project_totals.items():
            project_id = project_data['project_id']
            crm_metadata = project_data.get('crm_metadata', {})
            
            # Основные данные проекта
            excel_row = {
                'object_name': project_name,
                'remonline_id': crm_metadata.get('crm_id', ''),
                'status': crm_metadata.get('status_name', ''),
                'total_fuel_cost': project_data.get('fuel_cost', 0.0),
                'vehicles': [],
                'total_costs': project_data.get('fuel_cost', 0.0) + project_data.get('time_cost', 0.0)
            }
            
            # Добавляем данные по машинам, если на объект ездили несколько машин
            if project_id in vehicle_project_data:
                for vehicle, vehicle_data in vehicle_project_data[project_id].items():
                    excel_row['vehicles'].append({
                        'vehicle': vehicle,
                        'time_minutes': vehicle_data['time_minutes'],
                        'time_cost': vehicle_data['time_cost'],
                        'fuel_cost': vehicle_data['fuel_cost']
                    })
            
            # Если нет данных по машинам, добавляем общие данные
            if not excel_row['vehicles']:
                excel_row['vehicles'].append({
                    'vehicle': 'Общие данные',
                    'time_minutes': project_data.get('time_minutes', 0),
                    'time_cost': project_data.get('time_cost', 0.0),
                    'fuel_cost': project_data.get('fuel_cost', 0.0)
                })
            
            excel_data.append(excel_row)
        
        return excel_data