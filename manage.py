#!/usr/bin/env python
"""
Management script for database operations.

Usage:
    python manage.py db init     # Initialize migrations folder
    python manage.py db migrate  # Create a new migration
    python manage.py db upgrade  # Apply migrations
    python manage.py db downgrade # Rollback migrations
"""
import os
from flask.cli import FlaskGroup
from app import create_app
from app.database import db
from app import models  # Import models to register them with SQLAlchemy

def create_cli_app():
    """Create app instance for CLI."""
    env = os.getenv('ENV', 'development')
    return create_app(env)

cli = FlaskGroup(create_app=create_cli_app)

if __name__ == '__main__':
    cli()
