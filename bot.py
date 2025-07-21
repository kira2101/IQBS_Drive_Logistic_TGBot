import logging
import os
from datetime import datetime
from typing import List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from database import get_db_session, create_tables
from models import Project
from state_manager import StateManager
from report_generator import ReportGenerator
from settings import get_settings
from fuel_controller import get_fuel_controller

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

async def start_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new working day"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        state_manager.create_or_get_user(
            user.id, user.username, user.first_name, user.last_name
        )
        
        # Check if working day already started
        active_working_day = state_manager.get_active_working_day(user.id)
        if active_working_day:
            await update.message.reply_text(
                f"Рабочий день уже начат в {active_working_day.start_time.strftime('%H:%M')}\n"
                f"Используйте /start_trip для начала нового рейса."
            )
            return
        
        # Start working day
        working_day = state_manager.start_working_day(user.id)
        await update.message.reply_text(
            f"Рабочий день начат в {working_day.start_time.strftime('%H:%M')}!\n"
            f"Используйте /start_trip для начала рейса."
        )
    
    finally:
        db.close()

async def start_trip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new trip"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        
        # Check if working day is active
        active_working_day = state_manager.get_active_working_day(user.id)
        if not active_working_day:
            await update.message.reply_text("Сначала начните рабочий день с /start_day")
            return
        
        # Check if trip already started
        active_trip = state_manager.get_active_work_day(user.id)
        if active_trip:
            await update.message.reply_text(
                f"Рейс уже начат в {active_trip.start_time.strftime('%H:%M')}"
            )
            return
        
        # Show vehicle selection from settings
        settings = get_settings()
        vehicle_names = settings.get_vehicle_names()
        
        keyboard = []
        for vehicle in vehicle_names:
            keyboard.append([InlineKeyboardButton(vehicle, callback_data=f"vehicle:{vehicle}")])
        
        if not keyboard:
            await update.message.reply_text("Ошибка: не настроены автомобили в конфигурации")
            return
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Выберите автомобиль для рейса:",
            reply_markup=reply_markup
        )
    
    finally:
        db.close()

async def drive_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a trip to a destination"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        
        # Check if work day is active
        active_day = state_manager.get_active_work_day(user.id)
        if not active_day:
            await update.message.reply_text("Сначала начните рейс с /start_day")
            return
        
        # Get all objects (static + CRM)
        all_objects = state_manager.get_all_objects()
        
        # Create keyboard with destinations
        keyboard = []
        
        for obj in all_objects:
            obj_name = obj['name']
            obj_id = obj.get('id', '')
            
            if obj.get('source') == 'static':
                # Static objects (Магазин, Склад, Дом, Заправка)
                keyboard.append([InlineKeyboardButton(obj_name, callback_data=f"drive_to:static:{obj_id}")])
            else:
                # CRM objects - use only ID in callback_data
                keyboard.append([InlineKeyboardButton(obj_name, callback_data=f"drive_to:crm:{obj_id}")])
        
        # Add manual input option at the end
        keyboard.append([InlineKeyboardButton("✏️ Ввести вручную", callback_data="drive_to:manual:input")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Куда едете?",
            reply_markup=reply_markup
        )
    
    finally:
        db.close()

async def arrive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Arrive at destination"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        current_state = state_manager.get_user_state(user.id)
        
        if current_state != 'driving':
            await update.message.reply_text("Вы сейчас не в поездке. Используйте /drive_to для начала поездки.")
            return
        
        # Сохраняем данные о поездке при переходе к ожиданию расстояния
        trip_data = state_manager.get_user_state_data(user.id)
        await update.message.reply_text("Введите расстояние в км:")
        state_manager.set_user_state(user.id, 'waiting_distance', trip_data)
    
    finally:
        db.close()

async def shop_for(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start shopping for projects"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        
        # Check if work day is active
        active_day = state_manager.get_active_work_day(user.id)
        if not active_day:
            await update.message.reply_text("Сначала начните рейс с /start_day")
            return
        
        # Check if already shopping
        current_state = state_manager.get_user_state(user.id)
        if current_state == 'shopping':
            await update.message.reply_text("Закупка уже начата. Закончите текущую закупку командой /end_activity или продолжите работу.")
            return
        
        # Get all objects (static + CRM)
        all_objects = state_manager.get_all_objects()
        
        keyboard = []
        for obj in all_objects:
            obj_name = obj['name']
            obj_id = obj.get('id', '')
            
            # For shopping, exclude non-project destinations
            if obj_name not in ["Магазин", "Дом", "Заправка"]:
                keyboard.append([InlineKeyboardButton(
                    obj_name, 
                    callback_data=f"shop_toggle:{obj_id}"
                )])
        
        # Add done button
        keyboard.append([InlineKeyboardButton("Готово", callback_data="shop_done")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "Для каких проектов делаете закупку? (можно выбрать несколько)",
            reply_markup=reply_markup
        )
        
        # Store selected projects in state
        state_manager.set_user_state(user.id, 'selecting_shop_projects', {'selected': []})
    
    finally:
        db.close()

async def work_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start working on a project"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        
        # Check if work day is active
        active_day = state_manager.get_active_work_day(user.id)
        if not active_day:
            await update.message.reply_text("Сначала начните рейс с /start_day")
            return
        
        # Get last destination and try to find matching project
        last_destination = state_manager.get_last_destination(user.id)
        if last_destination and last_destination != "Магазин":
            project = state_manager.get_project_by_name(last_destination)
            if project:
                # Start work automatically on the last destination
                state_manager.start_work(user.id, project.id)
                await update.message.reply_text(
                    f"Работа на {project.name} начата. Используйте /end_activity когда закончите."
                )
                return
        
        # If no last destination found or it's Магазин, show object selection
        all_objects = state_manager.get_all_objects()
        
        keyboard = []
        for obj in all_objects:
            obj_name = obj['name']
            obj_id = obj.get('id', '')
            
            # Exclude Магазин and Заправка from work selection
            if obj_name not in ["Магазин", "Заправка"]:
                keyboard.append([InlineKeyboardButton(
                    obj_name, 
                    callback_data=f"work_on:{obj_id}"
                )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "На каком объекте работаете?",
            reply_markup=reply_markup
        )
    
    finally:
        db.close()

async def end_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End current activity"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        current_state = state_manager.get_user_state(user.id)
        
        if current_state == 'shopping':
            shopping_session = state_manager.end_shopping(user.id)
            await update.message.reply_text(
                f"Закупка завершена. Время: {shopping_session.duration_minutes} минут.\n\n"
                f"Доступные команды:\n/drive_to - Поехать в другое место"
            )
        elif current_state == 'working':
            activity = state_manager.end_work(user.id)
            project = db.query(Project).filter(Project.id == activity.project_id).first()
            await update.message.reply_text(
                f"Работа на {project.name} завершена. Время: {activity.duration_minutes} минут.\n\n"
                f"Доступные команды:\n/drive_to - Поехать в другое место"
            )
        else:
            await update.message.reply_text("Нет активной деятельности для завершения.")
    
    finally:
        db.close()

async def end_trip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End current trip and show trip report"""
    db = get_db_session()
    state_manager = StateManager(db)
    report_generator = ReportGenerator(db)
    
    try:
        user = update.effective_user
        
        # Get the current work day (trip) for report generation
        work_day = state_manager.get_active_work_day(user.id)
        if not work_day:
            await update.message.reply_text("Нет активного рейса.")
            return
        
        # End the current work day (trip) and generate report
        ended_work_day = state_manager.end_work_day(user.id)
        
        # Generate report
        report = report_generator.generate_daily_report(ended_work_day)
        
        await update.message.reply_text(
            f"Рейс завершен в {ended_work_day.end_time.strftime('%H:%M')}!\n\n{report}\n\n"
            f"Доступные команды:\n/start\\_trip - Начать новый рейс\n/end\\_day - Завершить рабочий день",
            parse_mode='Markdown'
        )
    
    finally:
        db.close()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = query.from_user
        data = query.data
        
        if data == 'drive_to:manual:input':
            # Set state for manual input
            state_manager.set_user_state(user.id, 'waiting_manual_destination')
            await query.edit_message_text("Введите название объекта:")
        
        elif data.startswith('drive_to:'):
            parts = data.split(':')
            obj_type = parts[1]  # 'static' or 'crm'
            obj_id = parts[2] if len(parts) > 2 else None
            
            # Get object info to find the name
            obj = state_manager.get_object_by_name_and_id(obj_id)
            if not obj:
                await query.edit_message_text("Ошибка: объект не найден.")
                return
                
            destination = obj['name']
            
            # For CRM objects, ensure they exist as projects
            project_id = None
            if obj_type == 'crm':
                # This is a CRM object, create/get corresponding project
                project = state_manager.ensure_crm_object_as_project(obj_id, destination)
                project_id = project.id
            elif obj_type == 'static':
                # Static object - may or may not have project
                if obj_id.isdigit():
                    project_id = int(obj_id)
            
            state_manager.start_trip(user.id, destination, project_id)
            await query.edit_message_text(
                f"Поездка к {destination} начата.\n\nИспользуйте /arrive когда прибудете."
            )
        
        elif data.startswith('shop_toggle:'):
            project_id = data.split(':')[1]
            state_data = state_manager.get_user_state_data(user.id)
            selected = state_data.get('selected', [])
            
            if project_id in selected:
                selected.remove(project_id)
            else:
                selected.append(project_id)
            
            state_manager.set_user_state(user.id, 'selecting_shop_projects', {'selected': selected})
            
            # Update keyboard to show selected items
            all_objects = state_manager.get_all_objects()
            keyboard = []
            
            for obj in all_objects:
                obj_name = obj['name']
                obj_id = str(obj.get('id', ''))
                
                # For shopping, exclude non-project destinations
                if obj_name not in ["Магазин", "Дом", "Заправка"]:
                    text = f"✓ {obj_name}" if obj_id in selected else obj_name
                    keyboard.append([InlineKeyboardButton(
                        text, 
                        callback_data=f"shop_toggle:{obj_id}"
                    )])
            
            keyboard.append([InlineKeyboardButton("Готово", callback_data="shop_done")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        
        elif data == 'shop_done':
            state_data = state_manager.get_user_state_data(user.id)
            selected = state_data.get('selected', [])
            
            if not selected:
                await query.edit_message_text("Выберите хотя бы один проект.")
                return
            
            # Convert selected objects to project IDs
            project_ids = []
            for obj_id in selected:
                obj = state_manager.get_object_by_name_and_id(obj_id)
                if obj:
                    if obj.get('source') == 'static' and obj_id.isdigit():
                        # Database project ID
                        project_ids.append(int(obj_id))
                    else:
                        # CRM object or static object - ensure project exists
                        project = state_manager.ensure_crm_object_as_project(obj_id, obj['name'])
                        project_ids.append(project.id)
            
            state_manager.start_shopping(user.id, project_ids)
            await query.edit_message_text(
                f"Закупка начата для {len(project_ids)} проектов. Используйте /end_activity когда закончите."
            )
        
        elif data.startswith('vehicle:'):
            vehicle = data.split(':')[1]
            work_day = state_manager.start_work_day(user.id, vehicle)
            await query.edit_message_text(
                f"Рейс начат в {work_day.start_time.strftime('%H:%M')} на {vehicle}!\n"
                f"Используйте /drive_to для начала поездки."
            )
        
        elif data.startswith('work_on:'):
            object_id = data.split(':')[1]
            
            # Find object first
            obj = state_manager.get_object_by_name_and_id(object_id)
            if not obj:
                await query.edit_message_text("Ошибка: объект не найден.")
                return
            
            # Handle both CRM and static objects
            if obj.get('source') == 'static' and object_id.isdigit():
                # Database project ID
                project_id = int(object_id)
                project = db.query(Project).filter(Project.id == project_id).first()
            else:
                # CRM object - ensure project exists
                project = state_manager.ensure_crm_object_as_project(object_id, obj['name'])
                project_id = project.id
            
            state_manager.start_work(user.id, project_id)
            await query.edit_message_text(
                f"Работа на {project.name} начата. Используйте /end_activity когда закончите."
            )
        
        elif data.startswith('idle_toggle:'):
            project_id = data.split(':')[1]
            state_data = state_manager.get_user_state_data(user.id)
            selected = state_data.get('selected', [])
            
            if project_id in selected:
                selected.remove(project_id)
            else:
                selected.append(project_id)
            
            state_manager.set_user_state(user.id, 'selecting_idle_projects', {'selected': selected})
            
            # Update keyboard to show selected items
            all_objects = state_manager.get_all_objects()
            keyboard = []
            
            for obj in all_objects:
                obj_name = obj['name']
                obj_id = str(obj.get('id', ''))
                
                if obj_name != "Заправка":
                    text = f"✓ {obj_name}" if obj_id in selected else obj_name
                    keyboard.append([InlineKeyboardButton(
                        text, 
                        callback_data=f"idle_toggle:{obj_id}"
                    )])
            
            keyboard.append([InlineKeyboardButton("Готово", callback_data="idle_done")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        
        elif data == 'idle_done':
            state_data = state_manager.get_user_state_data(user.id)
            selected = state_data.get('selected', [])
            
            if not selected:
                await query.edit_message_text("Выберите хотя бы один объект.")
                return
            
            # Convert selected objects to project IDs
            project_ids = []
            for obj_id in selected:
                obj = state_manager.get_object_by_name_and_id(obj_id)
                if obj:
                    if obj.get('source') == 'static' and obj_id.isdigit():
                        # Database project ID
                        project_ids.append(int(obj_id))
                    else:
                        # CRM object or static object - ensure project exists
                        project = state_manager.ensure_crm_object_as_project(obj_id, obj['name'])
                        project_ids.append(project.id)
            
            state_manager.start_idle_time(user.id, project_ids)
            await query.edit_message_text(
                f"Простой начат для {len(project_ids)} объектов. Используйте /end_idle_time когда закончите."
            )
        
        elif data.startswith('similarity_yes:'):
            # User accepted a similarity suggestion - ask for confirmation
            crm_object_id = data.split(':')[1]
            
            # Get CRM object details
            from crm_remonline import get_crm_client
            crm_client = get_crm_client()
            
            if crm_client:
                all_crm_objects = crm_client.get_all_objects_without_filters()
                selected_obj = None
                
                for obj in all_crm_objects:
                    if str(obj['id']) == crm_object_id:
                        selected_obj = obj
                        break
                
                if selected_obj:
                    # Show confirmation before starting trip
                    keyboard = [
                        [InlineKeyboardButton("✅ Да, начать поездку", callback_data=f"confirm_trip_crm:{crm_object_id}")],
                        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_manual_input")]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    await query.edit_message_text(
                        f"Начать поездку к:\n*{selected_obj['name']}*?",
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
                else:
                    await query.edit_message_text("Ошибка: объект не найден в CRM.")
            else:
                await query.edit_message_text("Ошибка: нет доступа к CRM.")
        
        elif data.startswith('similarity_no:'):
            # User rejected all suggestions - ask for confirmation to create new destination
            user_input = data.split(':', 1)[1]  # Get the original user input
            
            # Get stored user input if available
            state_data = state_manager.get_user_state_data(user.id)
            if state_data and 'manual_destination_input' in state_data:
                user_input = state_data['manual_destination_input']
            
            # Show confirmation before creating new destination
            keyboard = [
                [InlineKeyboardButton("✅ Да, создать новый объект", callback_data=f"confirm_trip_new:{user_input}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_manual_input")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"Создать новый объект и начать поездку к:\n*{user_input}*?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        elif data.startswith('confirm_trip_crm:'):
            # User confirmed trip to CRM object
            crm_object_id = data.split(':')[1]
            
            # Get CRM object details
            from crm_remonline import get_crm_client
            crm_client = get_crm_client()
            
            if crm_client:
                all_crm_objects = crm_client.get_all_objects_without_filters()
                selected_obj = None
                
                for obj in all_crm_objects:
                    if str(obj['id']) == crm_object_id:
                        selected_obj = obj
                        break
                
                if selected_obj:
                    # Create/get project for the CRM object
                    project = state_manager.ensure_crm_object_as_project(
                        str(selected_obj['id']), 
                        selected_obj['name']
                    )
                    
                    # Start trip to this destination
                    state_manager.start_trip(user.id, selected_obj['name'], project.id)
                    
                    # Keep driving state - user will call /arrive manually
                    
                    # Get current time for display
                    from datetime import datetime
                    start_time = datetime.now()
                    
                    await query.edit_message_text(
                        f"Поездка начата!\n"
                        f"Откуда: Текущее местоположение\n"  
                        f"Куда: {selected_obj['name']}\n"
                        f"Время начала: {start_time.strftime('%H:%M')}\n\n"
                        f"Используйте /arrive когда прибудете."
                    )
                else:
                    await query.edit_message_text("Ошибка: объект не найден в CRM.")
            else:
                await query.edit_message_text("Ошибка: нет доступа к CRM.")
        
        elif data.startswith('confirm_trip_new:'):
            # User confirmed trip to new destination
            user_input = data.split(':', 1)[1]  # Get the destination name
            
            # Get stored user input if available
            state_data = state_manager.get_user_state_data(user.id)
            if state_data and 'manual_destination_input' in state_data:
                user_input = state_data['manual_destination_input']
            
            # Check if this destination already exists as a project
            existing_project = state_manager.get_project_by_name(user_input)
            
            if existing_project:
                # Use existing project
                state_manager.start_trip(user.id, user_input, existing_project.id)
            else:
                # Create new project
                project = state_manager.create_project(user_input, f"Введено вручную пользователем")
                state_manager.start_trip(user.id, user_input, project.id)
                
                # Send notification to admin about new destination
                await _notify_admin_new_destination(context.bot, user_input, user.id, user.username)
            
            # Keep driving state - user will call /arrive manually
            
            # Get current time for display
            from datetime import datetime
            start_time = datetime.now()
            
            await query.edit_message_text(
                f"Поездка начата!\n"
                f"Откуда: Текущее местоположение\n"  
                f"Куда: {user_input}\n"
                f"Время начала: {start_time.strftime('%H:%M')}\n\n"
                f"Используйте /arrive когда прибудете."
            )
        
        elif data == 'cancel_manual_input':
            # User cancelled manual input
            state_manager.set_user_state(user.id, 'idle')
            await query.edit_message_text("Ввод отменен.")
    
    finally:
        db.close()

def _check_daily_fuel_warnings(work_days):
    """Check fuel levels for all vehicles used during the day and return warnings"""
    try:
        fuel_controller = get_fuel_controller()
        
        # Get unique vehicles from work days
        vehicles_used = set()
        for work_day in work_days:
            if work_day.vehicle:
                vehicles_used.add(work_day.vehicle)
        
        warnings = []
        for vehicle in vehicles_used:
            should_warn, warning_msg = fuel_controller.should_warn_about_fuel(vehicle)
            if should_warn:
                warnings.append(warning_msg)
        
        if warnings:
            return "\n⚠️ ВНИМАНИЕ: Проверьте топливо!\n" + "\n".join(warnings)
        
        return ""
    except Exception as e:
        logger.error(f"Error checking daily fuel warnings: {e}")
        return ""

async def end_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End work day and show day report with all trips"""
    db = get_db_session()
    state_manager = StateManager(db)
    report_generator = ReportGenerator(db)
    
    try:
        user = update.effective_user
        
        # Check if working day is active
        active_working_day = state_manager.get_active_working_day(user.id)
        if not active_working_day:
            await update.message.reply_text("Рабочий день не начат. Используйте /start_day для начала.")
            return
        
        # Get all work days for today
        from datetime import datetime, date
        from models import WorkDay
        today = date.today()
        work_days = db.query(WorkDay).filter(
            WorkDay.user_id == state_manager._get_user_id(user.id),
            WorkDay.date >= today
        ).all()
        
        if not work_days:
            await update.message.reply_text("Нет рейсов за сегодня. Завершаем рабочий день без рейсов.")
            # Still end the working day
            state_manager.end_working_day(user.id)
            return
        
        # End any active work day and working day
        active_day = state_manager.get_active_work_day(user.id)
        if active_day:
            work_day = state_manager.end_work_day(user.id)
        
        # End working day
        state_manager.end_working_day(user.id)
        
        # Generate day report for all trips
        day_report = report_generator.generate_day_report(work_days)
        
        # Save day report as JSON
        report_generator.save_day_report_json(work_days)
        
        # Check fuel levels at end of day and send warnings if needed
        fuel_warnings = _check_daily_fuel_warnings(work_days)
        
        message = f"Рабочий день завершен!\n\n{day_report}"
        if fuel_warnings:
            message += f"\n{fuel_warnings}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    finally:
        db.close()

async def idle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start idle time tracking"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        
        # Check if work day is active
        active_day = state_manager.get_active_work_day(user.id)
        if not active_day:
            await update.message.reply_text("Сначала начните рейс с /start_day")
            return
        
        # Get last destination and auto-assign idle time to it
        last_destination = state_manager.get_last_destination(user.id)
        if last_destination and last_destination not in ["Магазин", "Заправка"]:
            project = state_manager.get_project_by_name(last_destination)
            if project:
                # Start idle time automatically for the last destination
                state_manager.start_idle_time(user.id, [project.id])
                await update.message.reply_text(
                    f"Простой начат для {project.name}. Используйте /end_idle_time когда закончите."
                )
                return
        
        # If no suitable last destination, show error
        await update.message.reply_text(
            "Не удалось определить последний объект для простоя. "
            "Сначала поезжайте на объект с помощью /drive_to"
        )
    
    finally:
        db.close()

async def end_idle_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End idle time tracking"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        current_state = state_manager.get_user_state(user.id)
        
        if current_state != 'idle_tracking':
            await update.message.reply_text("Простой не начат. Используйте команду /idle_time для начала.")
            return
        
        # End idle time
        idle_session = state_manager.end_idle_time(user.id)
        
        await update.message.reply_text(
            f"Простой завершен. Время: {idle_session.duration_minutes}мин.\n\n"
            f"Доступные команды:\n/drive_to - Поехать в другое место\n/work_on - Начать работу"
        )
    
    finally:
        db.close()

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text input for various states"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        current_state = state_manager.get_user_state(user.id)
        
        if current_state == 'waiting_distance':
            await handle_distance_input(update, db, state_manager, user)
        elif current_state == 'waiting_odometer_reading':
            await handle_odometer_reading(update, db, state_manager, user)
        elif current_state == 'waiting_fuel_liters':
            await handle_fuel_liters(update, db, state_manager, user)
        elif current_state == 'waiting_fuel_amount':
            await handle_fuel_amount(update, db, state_manager, user)
        elif current_state == 'waiting_manual_destination':
            await handle_manual_destination_input(update, db, state_manager, user)
        else:
            return
    
    finally:
        db.close()

async def handle_distance_input(update, db, state_manager, user):
    """Handle distance input specifically"""
    try:
        # Заменяем запятую на точку для корректного парсинга
        distance_text = update.message.text.replace(',', '.')
        distance = float(distance_text)
        
        if distance <= 0:
            await update.message.reply_text("Пожалуйста, введите положительное расстояние в км.")
            return
            
        trip = state_manager.end_trip(user.id, distance)
        
        # Update fuel consumption using advanced algorithm
        work_day = state_manager.get_active_work_day(user.id)
        fuel_warning_message = ""
        if work_day and work_day.vehicle:
            fuel_controller = get_fuel_controller()
            fuel_update = fuel_controller.update_fuel_after_trip(work_day.vehicle, distance)
            
            if not fuel_update.get("tracking_disabled") and not fuel_update.get("error"):
                fuel_after = fuel_update.get("fuel_after_liters", 0)
                fuel_warning_message = f"\nОстаток топлива: {fuel_after:.1f} л."
                
                # Check for fuel warnings
                should_warn, warning_msg = fuel_controller.should_warn_about_fuel(work_day.vehicle)
                if should_warn:
                    fuel_warning_message += f"\n⛽ {warning_msg}"
        
        message = (f"✅ Поездка завершена!\n"
                  f"Расстояние: {trip.distance_km} км.{fuel_warning_message}\n\n")
        
        # Предлагаем команды в зависимости от места прибытия
        if trip.end_location == "Магазин":
            message += "Доступные команды:\n/shop_for - Начать закупку\n/drive_to - Поехать в другое место"
        elif trip.end_location == "Заправка":
            message += "Пожалуйста, сделайте фото одометра и отправьте его в чат."
            # Устанавливаем состояние ожидания фото одометра
            state_manager.set_user_state(user.id, 'waiting_odometer_photo')
        elif trip.end_location == "Дом":
            message += "Доступные команды:\n/drive_to - Поехать в другое место\n/idle_time - Начать простой\n/end_trip - Закончить рейс\n/end_day - Завершить рабочий день"
        else:
            message += "Доступные команды:\n/work_on - Начать работу\n/drive_to - Поехать в другое место"
        
        await update.message.reply_text(message)
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное расстояние в км.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def handle_odometer_reading(update, db, state_manager, user):
    """Handle odometer reading input"""
    try:
        # Заменяем запятую на точку для корректного парсинга
        reading_text = update.message.text.replace(',', '.')
        reading = float(reading_text)
        
        if reading <= 0:
            await update.message.reply_text("Пожалуйста, введите корректные показания одометра.")
            return
        
        # Сохраняем показания в состоянии и переходим к фото чека
        state_data = state_manager.get_user_state_data(user.id)
        state_data['odometer_reading'] = reading
        state_manager.set_user_state(user.id, 'waiting_receipt_photo', state_data)
        
        await update.message.reply_text("Показания одометра сохранены. Теперь сделайте фото чека заправки и отправьте его.")
        
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректные показания одометра (только цифры).")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def handle_fuel_liters(update, db, state_manager, user):
    """Handle fuel liters input"""
    try:
        # Заменяем запятую на точку для корректного парсинга
        liters_text = update.message.text.replace(',', '.')
        liters = float(liters_text)
        
        if liters <= 0:
            await update.message.reply_text("Пожалуйста, введите корректное количество литров.")
            return
        
        # Сохраняем литры в состоянии и переходим к вводу суммы
        state_data = state_manager.get_user_state_data(user.id)
        state_data['fuel_liters'] = liters
        state_manager.set_user_state(user.id, 'waiting_fuel_amount', state_data)
        
        await update.message.reply_text("Количество литров сохранено. Введите сумму заправки в гривнах (например: 2500.50):")
        
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное количество литров (например: 45.2).")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def handle_fuel_amount(update, db, state_manager, user):
    """Handle fuel amount input and save fuel purchase"""
    try:
        # Заменяем запятую на точку для корректного парсинга
        amount_text = update.message.text.replace(',', '.')
        amount = float(amount_text)
        
        if amount <= 0:
            await update.message.reply_text("Пожалуйста, введите корректную сумму.")
            return
        
        # Проверяем активный рейс
        work_day = state_manager.get_active_work_day(user.id)
        if not work_day:
            await update.message.reply_text("Нет активного рейса. Начните рейс с /start_day")
            return
        
        # Получаем все данные из состояния
        state_data = state_manager.get_user_state_data(user.id)
        
        # Сохраняем заправку в базу данных
        from models import FuelPurchase
        fuel_purchase = FuelPurchase(
            work_day_id=work_day.id,
            odometer_photo_path=state_data.get('odometer_photo'),
            receipt_photo_path=state_data.get('receipt_photo'),
            odometer_reading=state_data.get('odometer_reading'),
            fuel_liters=state_data.get('fuel_liters'),
            fuel_amount=amount
        )
        db.add(fuel_purchase)
        db.commit()
        
        # Update fuel level in system using advanced algorithm
        fuel_controller = get_fuel_controller()
        fuel_liters = state_data.get('fuel_liters', 0)
        fuel_status_msg = ""
        
        if work_day.vehicle and fuel_liters > 0:
            refuel_result = fuel_controller.update_fuel_after_refuel(
                work_day.vehicle, 
                fuel_liters, 
                amount
            )
            
            if not refuel_result.get("error"):
                fuel_after = refuel_result.get("fuel_after_liters", 0)
                fuel_status_msg = f"\nТекущий остаток: {fuel_after:.1f} л."
        
        # Очищаем состояние
        state_manager.set_user_state(user.id, 'idle')
        
        await update.message.reply_text(
            f"⛽️ Заправка выполнена!\n"
            f"Добавлено: {state_data.get('fuel_liters')} л.\n"
            f"Сумма: {amount} грн.{fuel_status_msg}\n\n"
            f"Доступные команды:\n/drive_to - Поехать в другое место"
        )
        
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректную сумму (например: 2500.50).")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")

async def handle_manual_destination_input(update, db, state_manager, user):
    """Handle manual destination input with similarity matching"""
    try:
        user_input = update.message.text.strip()
        
        if not user_input:
            await update.message.reply_text("Пожалуйста, введите название объекта.")
            return
        
        # Get all CRM objects without filters for similarity matching
        from crm_remonline import get_crm_client
        crm_client = get_crm_client()
        
        if not crm_client:
            # No CRM available, accept user input directly
            await _accept_manual_destination(update, db, state_manager, user, user_input)
            return
            
        # Get all CRM objects for similarity matching
        all_crm_objects = crm_client.get_all_objects_without_filters()
        
        # Find similar objects using fuzzy matching (no exact matching)
        similar_objects = _find_similar_objects(user_input, all_crm_objects)
        
        if similar_objects:
            # Show similarity suggestions
            keyboard = []
            for i, obj in enumerate(similar_objects[:3]):  # Show max 3 suggestions
                similarity_score = obj['similarity']
                callback_data = f"similarity_yes:{obj['id']}"
                keyboard.append([InlineKeyboardButton(
                    f"✅ {obj['name']} ({similarity_score:.0%})", 
                    callback_data=callback_data
                )])
            
            # Add option to reject all suggestions
            keyboard.append([InlineKeyboardButton(
                "❌ Нет, ввести новый объект", 
                callback_data=f"similarity_no:{user_input}"
            )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"Найдены похожие объекты для '{user_input}':\n\n"
                f"Выберите подходящий или создайте новый:",
                reply_markup=reply_markup
            )
            
            # Store user input for potential new object creation
            state_manager.set_user_state(user.id, 'waiting_manual_destination', {'manual_destination_input': user_input})
        else:
            # No similar objects found, ask for confirmation to create new destination
            keyboard = [
                [InlineKeyboardButton("✅ Да, создать новый объект", callback_data=f"confirm_trip_new:{user_input}")],
                [InlineKeyboardButton("❌ Отмена", callback_data="cancel_manual_input")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store user input for potential new object creation
            state_manager.set_user_state(user.id, 'waiting_manual_destination', {'manual_destination_input': user_input})
            
            await update.message.reply_text(
                f"Не найдено похожих объектов.\n\nСоздать новый объект и начать поездку к:\n*{user_input}*?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
    except Exception as e:
        logger.error(f"Error in handle_manual_destination_input: {e}")
        await update.message.reply_text(f"Ошибка при обработке ввода: {str(e)}")

def _find_similar_objects(user_input: str, objects: list, threshold: float = 0.7) -> list:
    """Find similar objects using improved fuzzy string matching"""
    try:
        from difflib import SequenceMatcher
        import re
        
        def normalize_text(text):
            """Normalize text for better matching"""
            # Convert to lowercase
            text = text.lower()
            # Remove common punctuation and extra spaces
            text = re.sub(r'[^\w\s]', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
        
        def transliterate_ua_to_en(text):
            """Simple Ukrainian to English transliteration"""
            ua_to_en = {
                'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'ґ': 'g', 'д': 'd', 'е': 'e', 'є': 'e', 
                'ж': 'zh', 'з': 'z', 'и': 'y', 'і': 'i', 'ї': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 
                'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 
                'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ь': '', 'ю': 'yu', 
                'я': 'ya', 'ё': 'yo', 'ъ': ''
            }
            result = ""
            for char in text.lower():
                result += ua_to_en.get(char, char)
            return result
        
        def transliterate_en_to_ua(text):
            """Simple English to Ukrainian transliteration"""
            en_to_ua = {
                'a': 'а', 'b': 'б', 'c': 'ц', 'd': 'д', 'e': 'е', 'f': 'ф', 'g': 'г', 'h': 'х', 
                'i': 'і', 'j': 'й', 'k': 'к', 'l': 'л', 'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 
                'q': 'к', 'r': 'р', 's': 'с', 't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс', 
                'y': 'і', 'z': 'з'
            }
            result = ""
            for char in text.lower():
                result += en_to_ua.get(char, char)
            return result
        
        def similarity(a, b):
            return SequenceMatcher(None, a, b).ratio()
        
        def comprehensive_similarity(user_text, obj_name):
            """Calculate similarity using multiple methods"""
            # Normalize both texts
            norm_user = normalize_text(user_text)
            norm_obj = normalize_text(obj_name)
            
            scores = []
            
            # TEMPORARY DEBUG: Simple test cases
            if 'бориспіль' in norm_obj.lower() and 'борис' in norm_user.lower():
                scores.append(0.9)  # Force high score for obvious match
            if 'борис' in norm_obj.lower() and 'борис' in norm_user.lower():
                scores.append(0.9)  # Force high score for obvious match
            
            # Generate transliterations
            translit_user_en = transliterate_ua_to_en(norm_user)
            translit_user_ua = transliterate_en_to_ua(norm_user)
            translit_obj_en = transliterate_ua_to_en(norm_obj)
            translit_obj_ua = transliterate_en_to_ua(norm_obj)
            
            # Split object name into words for word-by-word comparison
            obj_words = norm_obj.split()
            translit_obj_words_en = translit_obj_en.split()
            translit_obj_words_ua = translit_obj_ua.split()
            
            # Word-by-word matching (high priority for exact word matches)
            user_variants = [norm_user, translit_user_en, translit_user_ua]
            
            for user_variant in user_variants:
                # Check exact word match
                if user_variant in obj_words:
                    scores.append(0.95)
                if user_variant in translit_obj_words_en:
                    scores.append(0.95)
                if user_variant in translit_obj_words_ua:
                    scores.append(0.95)
                
                # Check partial matches within words (both directions)
                all_word_lists = [obj_words, translit_obj_words_en, translit_obj_words_ua]
                
                for word_list in all_word_lists:
                    for word in word_list:
                        if len(user_variant) >= 3 and len(word) >= 3:
                            # User input is part of word (e.g. "борис" in "бориспіль")
                            if user_variant in word:
                                # Calculate how much of the word the user input covers
                                coverage = len(user_variant) / len(word)
                                if coverage >= 0.5:  # At least 50% of the word
                                    scores.append(0.85 + coverage * 0.1)  # 85-95%
                                else:
                                    scores.append(0.7 + coverage * 0.15)   # 70-85%
                            
                            # Word is part of user input (less common but possible)
                            elif word in user_variant:
                                coverage = len(word) / len(user_variant)
                                if coverage >= 0.5:
                                    scores.append(0.8 + coverage * 0.1)   # 80-90%
                                else:
                                    scores.append(0.6 + coverage * 0.2)   # 60-80%
                            
                            # Check similarity for close matches
                            else:
                                word_similarity = similarity(user_variant, word)
                                if word_similarity >= 0.7:
                                    scores.append(0.7 + word_similarity * 0.25)  # 70-95%
                                elif word_similarity >= 0.5:
                                    scores.append(0.5 + word_similarity * 0.3)   # 50-80%
                
                # Also check if user input starts/ends with any word or vice versa
                for word_list in all_word_lists:
                    for word in word_list:
                        if len(user_variant) >= 3 and len(word) >= 3:
                            # Check if user input starts with word or word starts with user input
                            if user_variant.startswith(word) or word.startswith(user_variant):
                                min_len = min(len(user_variant), len(word))
                                max_len = max(len(user_variant), len(word))
                                coverage = min_len / max_len
                                if coverage >= 0.6:
                                    scores.append(0.75 + coverage * 0.2)  # 75-95%
                            
                            # Check if user input ends with word or word ends with user input  
                            elif user_variant.endswith(word) or word.endswith(user_variant):
                                min_len = min(len(user_variant), len(word))
                                max_len = max(len(user_variant), len(word))
                                coverage = min_len / max_len
                                if coverage >= 0.6:
                                    scores.append(0.7 + coverage * 0.2)   # 70-90%
            
            # Full text comparisons (lower priority)
            scores.append(similarity(norm_user, norm_obj) * 0.6)
            scores.append(similarity(translit_user_en, norm_obj) * 0.6)
            scores.append(similarity(translit_user_ua, norm_obj) * 0.6)
            scores.append(similarity(norm_user, translit_obj_en) * 0.6)
            scores.append(similarity(norm_user, translit_obj_ua) * 0.6)
            
            # Substring matching (medium priority)
            if len(norm_user) >= 3:
                if norm_user in norm_obj:
                    scores.append(0.8)
                if translit_user_en in norm_obj:
                    scores.append(0.8)
                if translit_user_ua in norm_obj:
                    scores.append(0.8)
                if norm_user in translit_obj_en:
                    scores.append(0.8)
                if norm_user in translit_obj_ua:
                    scores.append(0.8)
            
            # Return the maximum score from all methods
            return max(scores) if scores else 0
        
        similar = []
        debug_scores = []
        
        for obj in objects:
            score = comprehensive_similarity(user_input, obj['name'])
            logger.info(f"Similarity for '{user_input}' vs '{obj['name']}': {score:.3f}")
            
            # TEMPORARY DEBUG: Store all scores for debugging
            debug_scores.append(f"'{obj['name']}': {score:.3f}")
            
            if score >= threshold:
                obj_with_score = obj.copy()
                obj_with_score['similarity'] = score
                similar.append(obj_with_score)
        
        # TEMPORARY DEBUG: Log all scores
        logger.info(f"All similarity scores for '{user_input}': {debug_scores[:10]}")  # First 10
        
        # Sort by similarity score (highest first)
        similar.sort(key=lambda x: x['similarity'], reverse=True)
        
        logger.info(f"Found {len(similar)} similar objects above threshold {threshold}")
        
        return similar[:5]  # Return top 5 matches
        
    except Exception as e:
        logger.error(f"Error in similarity matching: {e}")
        return []

async def _accept_manual_destination(update, db, state_manager, user, destination_name):
    """Accept manual destination and check if admin notification is needed"""
    try:
        # Check if this destination already exists as a project
        existing_project = state_manager.get_project_by_name(destination_name)
        
        if existing_project:
            # Use existing project
            await _start_trip_to_destination(update, state_manager, user, destination_name, existing_project.id)
        else:
            # Create new project
            project = state_manager.create_project(destination_name, f"Введено вручную пользователем")
            await _start_trip_to_destination(update, state_manager, user, destination_name, project.id)
            
            # Send notification to admin
            await _notify_admin_new_destination(update.get_bot(), destination_name, user.id, user.username)
        
    except Exception as e:
        logger.error(f"Error accepting manual destination: {e}")
        await update.message.reply_text(f"Ошибка при создании назначения: {str(e)}")

async def _start_trip_to_destination(update, state_manager, user, destination_name, project_id):
    """Start trip to destination and clear manual input state"""
    try:
        # Start trip using state manager (this only sets state, doesn't create Trip object)
        state_manager.start_trip(user.id, destination_name, project_id)
        
        # Keep driving state - user will call /arrive manually
        # Don't change to waiting_distance automatically
        
        # Get current time for display
        from datetime import datetime
        start_time = datetime.now()
        
        await update.message.reply_text(
            f"Поездка начата!\n"
            f"Откуда: Текущее местоположение\n"  
            f"Куда: {destination_name}\n"
            f"Время начала: {start_time.strftime('%H:%M')}\n\n"
            f"По прибытии введите расстояние в км."
        )
        
    except Exception as e:
        logger.error(f"Error starting trip to destination: {e}")
        await update.message.reply_text(f"Ошибка при начале поездки: {str(e)}")

async def _notify_admin_new_destination(bot, destination_name, creator_user_id, creator_username=None):
    """Send notification to admins about new manually entered destination"""
    try:
        settings = get_settings()
        admin_user_ids = settings.get_admin_users()
        remonline_link = "https://web.remonline.app/orders/board"
        
        # Format creator info
        creator_info = f"ID: {creator_user_id}"
        if creator_username:
            creator_info += f" (@{creator_username})"
        
        message = (
            f"🔔 Новый объект введен вручную\n\n"
            f"Название: {destination_name}\n"
            f"Создал: {creator_info}\n"
            f"Проверьте в CRM: {remonline_link}"
        )
        
        # Send to both admins - ensure all get notified regardless of individual failures
        success_count = 0
        for admin_id in admin_user_ids:
            try:
                logger.info(f"Attempting to send notification to admin {admin_id}...")
                await bot.send_message(chat_id=admin_id, text=message)
                logger.info(f"✅ Admin notification successfully sent to {admin_id} for new destination: {destination_name}")
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to send admin notification to {admin_id}: {type(e).__name__}: {e}")
                if "403" in str(e) or "Forbidden" in str(e):
                    logger.error(f"User {admin_id} has blocked the bot or hasn't started it")
                elif "400" in str(e) or "Bad Request" in str(e):
                    logger.error(f"Invalid chat ID or message format for {admin_id}")
                # Continue to next admin even if this one fails
                
        logger.info(f"Admin notifications: {success_count}/{len(admin_user_ids)} sent successfully for destination: {destination_name}")
        
    except Exception as e:
        logger.error(f"Error in admin notification process: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo uploads for fuel station"""
    db = get_db_session()
    state_manager = StateManager(db)
    
    try:
        user = update.effective_user
        current_state = state_manager.get_user_state(user.id)
        
        if current_state == 'waiting_odometer_photo':
            # Проверяем активный рейс
            work_day = state_manager.get_active_work_day(user.id)
            if not work_day:
                await update.message.reply_text("Нет активного рейса. Начните рейс с /start_day")
                return
            
            # Сохраняем фото одометра
            photo = update.message.photo[-1]  # Берем фото наилучшего качества
            file = await context.bot.get_file(photo.file_id)
            photo_path = f"photos/odometer_{user.id}_{photo.file_id}.jpg"
            await file.download_to_drive(photo_path)
            
            # Сохраняем путь к фото в состоянии и переходим к вводу показаний
            state_manager.set_user_state(user.id, 'waiting_odometer_reading', {'odometer_photo': photo_path})
            
            await update.message.reply_text("Фото одометра сохранено. Введите показания одометра (например: 123456):")
            
        elif current_state == 'waiting_receipt_photo':
            # Проверяем активный рейс
            work_day = state_manager.get_active_work_day(user.id)
            if not work_day:
                await update.message.reply_text("Нет активного рейса. Начните рейс с /start_day")
                return
            
            # Сохраняем фото чека
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            photo_path = f"photos/receipt_{user.id}_{photo.file_id}.jpg"
            await file.download_to_drive(photo_path)
            
            # Получаем данные из состояния и добавляем путь к фото чека
            state_data = state_manager.get_user_state_data(user.id)
            state_data['receipt_photo'] = photo_path
            
            # Переходим к вводу литража
            state_manager.set_user_state(user.id, 'waiting_fuel_liters', state_data)
            
            await update.message.reply_text("Фото чека сохранено. Введите количество заправленных литров (например: 45.2):")
            
        else:
            # Если фото отправлено не в нужном состоянии
            await update.message.reply_text("Фотографии принимаются только на заправке после команды /arrive")
    
    finally:
        db.close()

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message"""
    help_text = """
    Доступные команды:
    
    /start_day - Начать рабочий день
    /start_trip - Начать рейс
    /drive_to - Начать поездку
    /arrive - Прибыть в пункт назначения
    /shop_for - Начать закупку
    /work_on - Начать работу на объекте
    /end_activity - Закончить текущую деятельность
    /end_trip - Закончить рейс и показать отчет
    /end_day - Закончить рабочий день и показать отчет по всем рейсам
    /idle_time - Начать простой
    /end_idle_time - Закончить простой
    /fuel_status - Показать статус топлива
    /help - Показать это сообщение
    """
    
    await update.message.reply_text(help_text)

async def fuel_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show fuel status for all vehicles or specific vehicle"""
    try:
        fuel_controller = get_fuel_controller()
        
        # Check if specific vehicle requested
        if context.args:
            vehicle_name = ' '.join(context.args)
            report = fuel_controller.generate_fuel_report(vehicle_name)
        else:
            report = fuel_controller.generate_fuel_report()
        
        await update.message.reply_text(report, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"Ошибка при получении статуса топлива: {str(e)}")

def main():
    """Start the bot"""
    # Create tables
    create_tables()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start_day", start_day))
    application.add_handler(CommandHandler("start_trip", start_trip))
    application.add_handler(CommandHandler("drive_to", drive_to))
    application.add_handler(CommandHandler("arrive", arrive))
    application.add_handler(CommandHandler("shop_for", shop_for))
    application.add_handler(CommandHandler("work_on", work_on))
    application.add_handler(CommandHandler("end_activity", end_activity))
    application.add_handler(CommandHandler("end_trip", end_trip))
    application.add_handler(CommandHandler("end_day", end_day))
    application.add_handler(CommandHandler("idle_time", idle_time))
    application.add_handler(CommandHandler("end_idle_time", end_idle_time))
    application.add_handler(CommandHandler("fuel_status", fuel_status))
    application.add_handler(CommandHandler("help", help_command))
    
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()