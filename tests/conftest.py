"""
Pytest configuration and fixtures
"""
import pytest
from app import create_app
from app.mod_common.auth import nonce_store


@pytest.fixture
def app():
    """Create application for testing."""
    app = create_app('development')
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key-for-jwt'
    app.config['WTF_CSRF_ENABLED'] = False

    yield app

    # Cleanup
    nonce_store.clear()


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
