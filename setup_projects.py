#!/usr/bin/env python3
"""
Script to set up initial projects in the database
"""

from database import create_tables, get_db_session
from models import Project

def setup_initial_projects():
    """Create initial projects"""
    create_tables()
    
    db = get_db_session()
    
    try:
        # Check if projects already exist
        existing_projects = db.query(Project).count()
        if existing_projects > 0:
            print(f"Database already has {existing_projects} projects. Skipping setup.")
            return
        
        # Create sample projects
        projects = [
            Project(name="Объект 1", description="Первый строительный объект"),
            Project(name="Объект 2", description="Второй строительный объект"),
            Project(name="Объект 3", description="Третий строительный объект"),
            Project(name="Склад", description="Складские операции"),
            Project(name="Заправка", description="Заправочная станция"),
            Project(name="Дом", description="Домашние дела")
        ]
        
        for project in projects:
            db.add(project)
        
        db.commit()
        print(f"Created {len(projects)} initial projects:")
        
        for project in projects:
            print(f"  - {project.name}: {project.description}")
    
    except Exception as e:
        print(f"Error setting up projects: {e}")
        db.rollback()
    
    finally:
        db.close()

if __name__ == "__main__":
    setup_initial_projects()