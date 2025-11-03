"""
Database initialization and configuration for the Flask application.
"""
import logging
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# Initialize SQLAlchemy
db = SQLAlchemy()

# Initialize Flask-Migrate
migrate = Migrate()


def init_app(app):
    """
    Initialize database extensions with the Flask app.

    Args:
        app: Flask application instance
    """
    db.init_app(app)
    migrate.init_app(app, db)

    # Configure SQLAlchemy logging to use DEBUG level instead of INFO
    # This applies to all database interaction logging
    logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
