"""
Fuel control module for tracking and managing vehicle fuel consumption
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from settings import get_settings

logger = logging.getLogger(__name__)

class FuelController:
    def __init__(self):
        self.settings = get_settings()
    
    def calculate_fuel_consumption(self, vehicle_name: str, distance_km: float) -> float:
        """Calculate expected fuel consumption for given distance"""
        vehicle_config = self.settings.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            logger.warning(f"No configuration found for vehicle: {vehicle_name}")
            return 0.0
        
        consumption_per_100km = vehicle_config.get("fuel_consumption_per_100km", 8.0)
        return (distance_km / 100) * consumption_per_100km
    
    def calculate_average_fuel_price_per_liter(self, vehicle_name: str) -> float:
        """Calculate current average fuel price per liter using weighted average"""
        vehicle_config = self.settings.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            return 0.0
        
        current_fuel_level = vehicle_config.get("current_fuel_level", 0.0)
        total_fuel_cost = vehicle_config.get("total_fuel_cost_in_tank", 0.0)
        
        if current_fuel_level <= 0:
            return 0.0
        
        return total_fuel_cost / current_fuel_level
    
    def update_fuel_after_trip(self, vehicle_name: str, distance_km: float) -> Dict:
        """Update fuel level after a trip using weighted average cost method"""
        if not self.settings.is_fuel_tracking_enabled():
            return {"tracking_disabled": True}
        
        vehicle_config = self.settings.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            return {"error": f"Vehicle {vehicle_name} not found"}
        
        # Step 1: Get current data
        current_fuel_level = vehicle_config.get("current_fuel_level", 0.0)
        total_fuel_cost = vehicle_config.get("total_fuel_cost_in_tank", 0.0)
        
        if current_fuel_level <= 0:
            return {"error": "No fuel in tank"}
        
        # Step 2: Calculate average price per liter
        average_price_per_liter = self.calculate_average_fuel_price_per_liter(vehicle_name)
        
        # Step 3: Calculate fuel consumption for this trip
        fuel_consumed_liters = self.calculate_fuel_consumption(vehicle_name, distance_km)
        
        # Step 4: Calculate trip cost
        trip_fuel_cost = fuel_consumed_liters * average_price_per_liter
        
        # Step 5: Update fuel data
        new_fuel_level = max(0.0, current_fuel_level - fuel_consumed_liters)
        new_total_cost = max(0.0, total_fuel_cost - trip_fuel_cost)
        
        # Update in settings
        self.settings.update_vehicle_fuel(vehicle_name, new_fuel_level, new_total_cost)
        
        # Check fuel status for warnings
        fuel_status = self.check_fuel_status(vehicle_name)
        
        # Log the fuel event
        self.log_fuel_event(vehicle_name, "trip_completed", {
            "distance_km": distance_km,
            "fuel_consumed_liters": fuel_consumed_liters,
            "trip_fuel_cost": trip_fuel_cost,
            "average_price_per_liter": average_price_per_liter
        })
        
        return {
            "vehicle": vehicle_name,
            "distance_km": distance_km,
            "fuel_consumed_liters": fuel_consumed_liters,
            "trip_fuel_cost": trip_fuel_cost,
            "average_price_per_liter": average_price_per_liter,
            "fuel_before_liters": current_fuel_level,
            "fuel_after_liters": new_fuel_level,
            "fuel_cost_before": total_fuel_cost,
            "fuel_cost_after": new_total_cost,
            "fuel_status": fuel_status
        }
    
    def update_fuel_after_refuel(self, vehicle_name: str, liters_added: float, refuel_cost: float) -> Dict:
        """Update fuel level and cost after refueling using weighted average method"""
        vehicle_config = self.settings.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            return {"error": f"Vehicle {vehicle_name} not found"}
        
        # Step 1: Get current data
        current_fuel_level = vehicle_config.get("current_fuel_level", 0.0)
        current_total_cost = vehicle_config.get("total_fuel_cost_in_tank", 0.0)
        tank_capacity = vehicle_config.get("tank_capacity", 60.0)
        
        # Step 2: Update fuel and cost (weighted average method)
        new_fuel_level = min(tank_capacity, current_fuel_level + liters_added)
        new_total_cost = current_total_cost + refuel_cost
        
        # Step 3: Update in settings
        self.settings.update_vehicle_fuel(vehicle_name, new_fuel_level, new_total_cost)
        
        # Calculate new average price per liter
        new_average_price_per_liter = new_total_cost / new_fuel_level if new_fuel_level > 0 else 0
        
        # Log the fuel event
        self.log_fuel_event(vehicle_name, "refueled", {
            "liters_added": liters_added,
            "refuel_cost": refuel_cost,
            "new_average_price_per_liter": new_average_price_per_liter
        })
        
        return {
            "vehicle": vehicle_name,
            "liters_added": liters_added,
            "refuel_cost": refuel_cost,
            "fuel_before_liters": current_fuel_level,
            "fuel_after_liters": new_fuel_level,
            "fuel_cost_before": current_total_cost,
            "fuel_cost_after": new_total_cost,
            "tank_capacity": tank_capacity,
            "new_average_price_per_liter": new_average_price_per_liter,
            "fuel_status": self.check_fuel_status(vehicle_name)
        }
    
    def check_fuel_status(self, vehicle_name: str) -> Dict:
        """Check current fuel status and return warnings if needed"""
        vehicle_config = self.settings.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            return {"error": f"Vehicle {vehicle_name} not found"}
        
        current_fuel = vehicle_config.get("current_fuel_level", 0.0)
        tank_capacity = vehicle_config.get("tank_capacity", 60.0)
        
        # Calculate percentage-based thresholds in liters
        low_threshold_percent = self.settings.get_low_fuel_threshold_percent()
        critical_threshold_percent = self.settings.get_critical_fuel_threshold_percent()
        
        low_threshold_liters = (tank_capacity * low_threshold_percent) / 100
        critical_threshold_liters = (tank_capacity * critical_threshold_percent) / 100
        
        fuel_percentage = (current_fuel / tank_capacity) * 100 if tank_capacity > 0 else 0
        
        status = {
            "current_fuel_liters": current_fuel,
            "tank_capacity": tank_capacity,
            "fuel_percentage": fuel_percentage,
            "low_threshold_liters": low_threshold_liters,
            "critical_threshold_liters": critical_threshold_liters,
            "level": "normal"
        }
        
        if current_fuel <= critical_threshold_liters:
            status["level"] = "critical"
            status["message"] = f"🔴 КРИТИЧЕСКИЙ уровень топлива: {current_fuel:.1f}L ({fuel_percentage:.0f}%)"
            status["action_required"] = "Немедленная заправка!"
        elif current_fuel <= low_threshold_liters:
            status["level"] = "low"
            status["message"] = f"🟡 Низкий уровень топлива: {current_fuel:.1f}L ({fuel_percentage:.0f}%)"
            status["action_required"] = "Рекомендуется заправка"
        else:
            status["message"] = f"🟢 Нормальный уровень топлива: {current_fuel:.1f}L ({fuel_percentage:.0f}%)"
        
        return status
    
    def get_estimated_range(self, vehicle_name: str) -> Dict:
        """Calculate estimated driving range with current fuel"""
        vehicle_config = self.settings.get_vehicle_config(vehicle_name)
        if not vehicle_config:
            return {"error": f"Vehicle {vehicle_name} not found"}
        
        current_fuel = vehicle_config.get("current_fuel_level", 0.0)
        consumption_per_100km = vehicle_config.get("fuel_consumption_per_100km", 8.0)
        
        # Estimated range in km
        estimated_range = (current_fuel / consumption_per_100km) * 100
        
        return {
            "vehicle": vehicle_name,
            "current_fuel": current_fuel,
            "consumption_per_100km": consumption_per_100km,
            "estimated_range_km": round(estimated_range, 1)
        }
    
    def generate_fuel_report(self, vehicle_name: str = None) -> str:
        """Generate fuel status report for vehicle(s)"""
        vehicles = self.settings.get_vehicles()
        
        if vehicle_name:
            if vehicle_name not in vehicles:
                return f"Автомобиль '{vehicle_name}' не найден."
            vehicles = {vehicle_name: vehicles[vehicle_name]}
        
        report = "*Отчет по топливу:*\n\n"
        
        for name, config in vehicles.items():
            fuel_status = self.check_fuel_status(name)
            range_info = self.get_estimated_range(name)
            
            report += f"*{name}:*\n"
            report += f"  {fuel_status.get('message', 'Нет данных')}\n"
            report += f"  Запас хода: ~{range_info.get('estimated_range_km', 0):.0f} км\n"
            
            if fuel_status.get("action_required"):
                report += f"  ⚠️ {fuel_status['action_required']}\n"
            
            report += "\n"
        
        return report
    
    def should_warn_about_fuel(self, vehicle_name: str) -> Tuple[bool, str]:
        """Check if fuel warning should be sent"""
        fuel_status = self.check_fuel_status(vehicle_name)
        
        if fuel_status.get("level") == "critical":
            return True, f"🔴 ВНИМАНИЕ! {fuel_status.get('message', '')}"
        elif fuel_status.get("level") == "low":
            return True, f"🟡 {fuel_status.get('message', '')}"
        
        return False, ""
    
    def log_fuel_event(self, vehicle_name: str, event_type: str, details: Dict):
        """Log fuel-related events"""
        timestamp = datetime.now().isoformat()
        logger.info(f"Fuel event - Vehicle: {vehicle_name}, Type: {event_type}, "
                   f"Details: {details}, Time: {timestamp}")

# Global fuel controller instance
_fuel_controller_instance = None

def get_fuel_controller() -> FuelController:
    """Get global fuel controller instance"""
    global _fuel_controller_instance
    if _fuel_controller_instance is None:
        _fuel_controller_instance = FuelController()
    return _fuel_controller_instance