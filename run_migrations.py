#!/usr/bin/env python
"""
Run database migrations automatically.

This script is called before the application starts to ensure
the database schema is up to date.
"""
import os
import sys
from flask_migrate import upgrade
from app import create_app
from app.database import db


def run_migrations():
    """Run database migrations."""
    env = os.getenv('ENV', 'production')

    print(f"[Migration] Environment: {env}")
    print(f"[Migration] Initializing Flask app...")

    try:
        app = create_app(env)

        with app.app_context():
            print(f"[Migration] Database URL: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured')[:50]}...")
            print(f"[Migration] Running database migrations...")

            # Run migrations
            upgrade()

            print(f"[Migration] ✓ Migrations completed successfully")
            return 0

    except Exception as e:
        print(f"[Migration] ✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()

        # Decide whether to fail or continue
        # If AUTO_MIGRATE_FAIL_ON_ERROR is true, exit with error
        if os.getenv('AUTO_MIGRATE_FAIL_ON_ERROR', 'false').lower() == 'true':
            print(f"[Migration] Exiting due to migration failure (AUTO_MIGRATE_FAIL_ON_ERROR=true)")
            return 1
        else:
            print(f"[Migration] Continuing despite migration failure (set AUTO_MIGRATE_FAIL_ON_ERROR=true to exit on error)")
            return 0


if __name__ == '__main__':
    sys.exit(run_migrations())
