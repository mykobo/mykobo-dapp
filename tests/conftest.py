"""
Pytest configuration and fixtures
"""
import os
import pytest

# Set test database URI BEFORE any app imports
# This must be done at module level before create_app is called
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app
from app.database import db as _db


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app('development')
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key-for-jwt'
    app.config['WTF_CSRF_ENABLED'] = False

    # Explicitly set SQLite for tests (already set in env but making it clear)
    # Note: SQLite doesn't support PostgreSQL schemas, but SQLAlchemy will
    # automatically ignore the schema parameter when using SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        # For SQLite, we need to tell SQLAlchemy to ignore schema names
        # SQLite doesn't support schemas, so we use schema_translate_map
        # to effectively remove the schema from table names
        from sqlalchemy import event

        @event.listens_for(_db.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            """Set up schema translation for all SQLite connections"""
            # This is called for every new connection

        @event.listens_for(_db.session, "after_begin")
        def _set_schema_translate_map(session, transaction, connection):
            """Translate schema names for SQLite (removes schema prefix)"""
            if connection.engine.dialect.name == 'sqlite':
                connection.execution_options(
                    schema_translate_map={"dapp": None}
                )

        # Create all tables in the test database with schema translation
        connection = _db.engine.connect()
        connection = connection.execution_options(schema_translate_map={"dapp": None})
        _db.metadata.create_all(bind=connection)
        connection.close()

        yield app

        # Cleanup
        _db.session.remove()
        connection = _db.engine.connect()
        connection = connection.execution_options(schema_translate_map={"dapp": None})
        _db.metadata.drop_all(bind=connection)
        connection.close()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Create test CLI runner."""
    return app.test_cli_runner()


@pytest.fixture
def auth_headers(app):
    """Generate valid auth headers with JWT token."""
    import jwt
    from datetime import datetime, UTC, timedelta

    token = jwt.encode(
        {
            'wallet_address': 'test_wallet_address',
            'exp': datetime.now(UTC) + timedelta(hours=1),
            'iat': datetime.now(UTC)
        },
        app.config['SECRET_KEY'],
        algorithm='HS256'
    )

    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def expired_auth_headers(app):
    """Generate expired auth headers with JWT token."""
    import jwt
    from datetime import datetime, UTC, timedelta

    token = jwt.encode(
        {
            'wallet_address': 'test_wallet_address',
            'exp': datetime.now(UTC) - timedelta(hours=1),
            'iat': datetime.now(UTC) - timedelta(hours=2)
        },
        app.config['SECRET_KEY'],
        algorithm='HS256'
    )

    return {'Authorization': f'Bearer {token}'}
