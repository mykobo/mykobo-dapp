"""
Tests for authentication decorators (app/decorators.py)
"""
import jwt
import pytest
from datetime import datetime, UTC, timedelta
from flask import Blueprint, jsonify

from app.decorators import require_wallet_auth


class TestRequireWalletAuthDecorator:
    """Tests for @require_wallet_auth decorator"""

    @pytest.fixture
    def test_blueprint(self, app):
        """Create a test blueprint with protected routes"""
        test_bp = Blueprint('test', __name__)

        @test_bp.route('/protected')
        @require_wallet_auth
        def protected_route():
            from flask import request
            return jsonify({
                'message': 'Access granted',
                'wallet': request.wallet_address
            })

        @test_bp.route('/unprotected')
        def unprotected_route():
            return jsonify({'message': 'Public access'})

        app.register_blueprint(test_bp)
        return test_bp

    def test_no_authorization_header(self, client, test_blueprint):
        """Test that request without Authorization header is rejected"""
        response = client.get('/protected')

        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'No authorization token provided'

    def test_valid_token_grants_access(self, client, test_blueprint, app):
        """Test that valid JWT token grants access"""
        # Create valid token
        token = jwt.encode(
            {
                'wallet_address': 'test_wallet_123',
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token}'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['message'] == 'Access granted'
        assert data['wallet'] == 'test_wallet_123'

    def test_token_without_bearer_prefix(self, client, test_blueprint, app):
        """Test that token without 'Bearer ' prefix works"""
        token = jwt.encode(
            {
                'wallet_address': 'test_wallet_123',
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': token}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['wallet'] == 'test_wallet_123'

    def test_expired_token_rejected(self, client, test_blueprint, app):
        """Test that expired JWT token is rejected"""
        # Create expired token
        token = jwt.encode(
            {
                'wallet_address': 'test_wallet_123',
                'exp': datetime.now(UTC) - timedelta(hours=1),
                'iat': datetime.now(UTC) - timedelta(hours=2)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token}'}
        )

        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'Token expired'

    def test_invalid_token_rejected(self, client, test_blueprint):
        """Test that invalid JWT token is rejected"""
        response = client.get(
            '/protected',
            headers={'Authorization': 'Bearer invalid_token_string'}
        )

        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'Invalid token'

    def test_token_with_wrong_secret(self, client, test_blueprint):
        """Test that token signed with wrong secret is rejected"""
        # Create token with wrong secret
        token = jwt.encode(
            {
                'wallet_address': 'test_wallet_123',
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            'wrong-secret-key',
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token}'}
        )

        assert response.status_code == 401
        data = response.get_json()
        assert data['error'] == 'Invalid token'

    def test_token_missing_wallet_address(self, client, test_blueprint, app):
        """Test that token without wallet_address in payload is rejected"""
        # Create token without wallet_address
        token = jwt.encode(
            {
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token}'}
        )

        # Should be rejected with 401
        assert response.status_code == 401
        data = response.get_json()
        assert data['error'] == 'Invalid token'

    def test_wallet_address_available_in_request(self, client, test_blueprint, app):
        """Test that wallet_address is properly set in request context"""
        wallet_address = 'specific_wallet_address_xyz'
        token = jwt.encode(
            {
                'wallet_address': wallet_address,
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token}'}
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['wallet'] == wallet_address

    def test_unprotected_route_accessible(self, client, test_blueprint):
        """Test that unprotected routes work without auth"""
        response = client.get('/unprotected')

        assert response.status_code == 200
        data = response.get_json()
        assert data['message'] == 'Public access'

    def test_multiple_requests_with_same_token(self, client, test_blueprint, app):
        """Test that same token can be used for multiple requests"""
        token = jwt.encode(
            {
                'wallet_address': 'test_wallet_123',
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        headers = {'Authorization': f'Bearer {token}'}

        # Make multiple requests
        for i in range(3):
            response = client.get('/protected', headers=headers)
            assert response.status_code == 200
            data = response.get_json()
            assert data['wallet'] == 'test_wallet_123'

    def test_different_tokens_for_different_wallets(self, client, test_blueprint, app):
        """Test that different wallet addresses are properly distinguished"""
        wallet1 = 'wallet_address_1'
        wallet2 = 'wallet_address_2'

        token1 = jwt.encode(
            {
                'wallet_address': wallet1,
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        token2 = jwt.encode(
            {
                'wallet_address': wallet2,
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        # Request with wallet1 token
        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token1}'}
        )
        assert response.status_code == 200
        assert response.get_json()['wallet'] == wallet1

        # Request with wallet2 token
        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token2}'}
        )
        assert response.status_code == 200
        assert response.get_json()['wallet'] == wallet2

    def test_token_expiring_soon_still_works(self, client, test_blueprint, app):
        """Test that token expiring in 1 second still works"""
        token = jwt.encode(
            {
                'wallet_address': 'test_wallet_123',
                'exp': datetime.now(UTC) + timedelta(seconds=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.get(
            '/protected',
            headers={'Authorization': f'Bearer {token}'}
        )

        assert response.status_code == 200

    def test_malformed_authorization_header(self, client, test_blueprint):
        """Test various malformed Authorization headers"""
        malformed_headers = [
            {'Authorization': ''},  # Empty
            {'Authorization': 'Bearer'},  # Just "Bearer"
            {'Authorization': 'NotBearer token'},  # Wrong prefix
            {'Authorization': 'Bearer  '},  # Bearer with spaces
        ]

        for headers in malformed_headers:
            response = client.get('/protected', headers=headers)
            assert response.status_code == 401


class TestDecoratorIntegration:
    """Integration tests for decorator with auth flow"""

    @pytest.fixture
    def protected_app(self, app):
        """Create app with protected Solana transaction route"""
        from flask import Blueprint, jsonify, request

        solana_bp = Blueprint('solana', __name__, url_prefix='/api/solana')

        @solana_bp.route('/transaction', methods=['POST'])
        @require_wallet_auth
        def create_transaction():
            data = request.get_json()
            # Verify wallet matches
            if request.wallet_address != data.get('from_address'):
                return jsonify({'error': 'Unauthorized'}), 403

            return jsonify({
                'transaction_id': 'tx_123',
                'from': request.wallet_address,
                'to': data.get('to_address'),
                'amount': data.get('amount')
            })

        app.register_blueprint(solana_bp)
        return app

    def test_authorized_transaction_creation(self, protected_app, app):
        """Test that authorized user can create transaction"""
        client = protected_app.test_client()
        wallet_address = 'authorized_wallet'

        token = jwt.encode(
            {
                'wallet_address': wallet_address,
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.post(
            '/api/solana/transaction',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'from_address': wallet_address,
                'to_address': 'recipient_wallet',
                'amount': 100
            }
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data['from'] == wallet_address
        assert data['to'] == 'recipient_wallet'
        assert data['amount'] == 100

    def test_unauthorized_transaction_attempt(self, protected_app, app):
        """Test that user cannot create transaction for another wallet"""
        client = protected_app.test_client()
        actual_wallet = 'wallet_1'
        spoofed_wallet = 'wallet_2'

        token = jwt.encode(
            {
                'wallet_address': actual_wallet,
                'exp': datetime.now(UTC) + timedelta(hours=1),
                'iat': datetime.now(UTC)
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )

        response = client.post(
            '/api/solana/transaction',
            headers={'Authorization': f'Bearer {token}'},
            json={
                'from_address': spoofed_wallet,  # Trying to spoof
                'to_address': 'recipient_wallet',
                'amount': 100
            }
        )

        assert response.status_code == 403
        data = response.get_json()
        assert data['error'] == 'Unauthorized'
