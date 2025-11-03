"""
Tests for authentication module (app/mod_common/auth.py)
"""
import time
import jwt
import base64
from datetime import datetime, UTC, timedelta
from unittest.mock import patch, MagicMock
import pytest
from nacl.signing import SigningKey
from nacl.encoding import Base64Encoder

from app.mod_common.auth import (
    generate_auth_challenge,
    verify_wallet_signature,
    cleanup_expired_nonces,
    TTL_IN_SECONDS
)
from app.models import Nonce
from app.database import db


class TestGenerateAuthChallenge:
    """Tests for generate_auth_challenge function"""

    def test_generates_unique_nonces(self, app):
        """Test that each challenge generates a unique nonce"""
        with app.app_context():
            wallet_address = "test_wallet_123"

            challenge1 = generate_auth_challenge(wallet_address)
            time.sleep(0.01)  # Small delay to ensure different timestamps
            challenge2 = generate_auth_challenge(wallet_address)

            assert challenge1['nonce'] != challenge2['nonce']
            # Timestamps should be close but nonces must be unique
            assert abs(challenge1['timestamp'] - challenge2['timestamp']) <= 1

    def test_challenge_structure(self, app):
        """Test that challenge has correct structure"""
        with app.app_context():
            wallet_address = "test_wallet_123"

            challenge = generate_auth_challenge(wallet_address)

            assert 'nonce' in challenge
            assert 'message' in challenge
            assert 'timestamp' in challenge
            assert isinstance(challenge['nonce'], str)
            assert isinstance(challenge['message'], str)
            assert isinstance(challenge['timestamp'], int)

    def test_challenge_message_format(self, app):
        """Test that challenge message contains required elements"""
        with app.app_context():
            wallet_address = "test_wallet_123"

            challenge = generate_auth_challenge(wallet_address)

            assert "Sign this message to authenticate with MYKOBO DAPP" in challenge['message']
            assert f"Nonce: {challenge['nonce']}" in challenge['message']
            assert f"Timestamp: {challenge['timestamp']}" in challenge['message']

    def test_nonce_stored_in_store(self, app):
        """Test that nonce is stored in database with correct data"""
        with app.app_context():
            wallet_address = "test_wallet_123"

            challenge = generate_auth_challenge(wallet_address, ttl_in_seconds=300)

            # Check nonce is in database
            nonce_record = Nonce.query.filter_by(nonce=challenge['nonce']).first()
            assert nonce_record is not None
            assert nonce_record.wallet_address == wallet_address
            assert nonce_record.used is False

            # Normalize datetimes for comparison (handle naive SQLite datetimes)
            expires_at = nonce_record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            assert expires_at > datetime.now(UTC)
            # Check expiry is approximately correct (within 2 seconds tolerance)
            expected_expiry = datetime.fromtimestamp(challenge['timestamp'] + 300, tz=UTC)
            assert abs((expires_at - expected_expiry).total_seconds()) <= 2

    def test_custom_ttl(self, app):
        """Test that custom TTL is respected"""
        with app.app_context():
            wallet_address = "test_wallet_123"
            custom_ttl = 600  # 10 minutes

            challenge = generate_auth_challenge(wallet_address, ttl_in_seconds=custom_ttl)

            nonce_record = Nonce.query.filter_by(nonce=challenge['nonce']).first()
            expected_expiry = datetime.fromtimestamp(challenge['timestamp'] + custom_ttl, tz=UTC)

            # Normalize datetimes for comparison
            expires_at = nonce_record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)

            assert abs((expires_at - expected_expiry).total_seconds()) <= 2


class TestVerifyWalletSignature:
    """Tests for verify_wallet_signature function"""

    def test_invalid_nonce_not_in_store(self, app):
        """Test verification fails for non-existent nonce"""
        with app.app_context():
            is_valid, error = verify_wallet_signature(
                "wallet_address",
                "signature",
                "nonexistent_nonce"
            )

            assert is_valid is False
            assert error == "Invalid or expired nonce"

    def test_already_used_nonce(self, app):
        """Test verification fails for already used nonce"""
        with app.app_context():
            wallet_address = "test_wallet"
            challenge = generate_auth_challenge(wallet_address)

            # Mark nonce as used
            nonce_record = Nonce.query.filter_by(nonce=challenge['nonce']).first()
            nonce_record.mark_used()
            db.session.commit()

            is_valid, error = verify_wallet_signature(
                wallet_address,
                "signature",
                challenge['nonce']
            )

            assert is_valid is False
            assert error == "Nonce already used"

    def test_expired_nonce(self, app):
        """Test verification fails for expired nonce"""
        with app.app_context():
            wallet_address = "test_wallet"
            challenge = generate_auth_challenge(wallet_address)

            # Set expiry to past
            nonce_record = Nonce.query.filter_by(nonce=challenge['nonce']).first()
            nonce_record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.session.commit()

            is_valid, error = verify_wallet_signature(
                wallet_address,
                "signature",
                challenge['nonce']
            )

            assert is_valid is False
            assert error == "Nonce expired"
            # Verify nonce was deleted
            nonce_check = Nonce.query.filter_by(nonce=challenge['nonce']).first()
            assert nonce_check is None

    def test_wallet_address_mismatch(self, app):
        """Test verification fails when wallet address doesn't match"""
        with app.app_context():
            wallet_address = "test_wallet"
            challenge = generate_auth_challenge(wallet_address)

            is_valid, error = verify_wallet_signature(
                "different_wallet",
                "signature",
                challenge['nonce']
            )

            assert is_valid is False
            assert error == "Wallet address mismatch"

    def test_invalid_signature_format(self, app):
        """Test verification fails for invalid signature format"""
        with app.app_context():
            wallet_address = "test_wallet"
            challenge = generate_auth_challenge(wallet_address)

            is_valid, error = verify_wallet_signature(
                wallet_address,
                "invalid_base64",
                challenge['nonce']
            )

            assert is_valid is False
            assert "verification failed" in error.lower()

    def test_signature_verification_failure(self, app):
        """Test verification fails for incorrect signature"""
        with app.app_context():
            # Create a signing key
            signing_key = SigningKey.generate()
            wallet_address = base64.b64encode(signing_key.verify_key.encode()).decode('utf-8')

            challenge = generate_auth_challenge(wallet_address)

            # Sign wrong message
            wrong_message = "wrong message"
            signed = signing_key.sign(wrong_message.encode('utf-8'))
            signature_b64 = base64.b64encode(signed.signature).decode('utf-8')

            is_valid, error = verify_wallet_signature(
                wallet_address,
                signature_b64,
                challenge['nonce']
            )

            assert is_valid is False
            assert "verification failed" in error.lower()

    def test_successful_signature_verification(self, app):
        """Test successful signature verification flow"""
        with app.app_context():
            # Create a signing key (simulating Solana wallet)
            signing_key = SigningKey.generate()
            # Use base58 encoding for Solana wallet address
            import base58
            wallet_address = base58.b58encode(signing_key.verify_key.encode()).decode('utf-8')

            # Generate challenge
            challenge = generate_auth_challenge(wallet_address)

            # Sign the message
            message = challenge['message']
            signed = signing_key.sign(message.encode('utf-8'))
            signature_b64 = base64.b64encode(signed.signature).decode('utf-8')

            # Verify
            is_valid, error = verify_wallet_signature(
                wallet_address,
                signature_b64,
                challenge['nonce']
            )

            assert is_valid is True
            assert error is None
            # Verify nonce is marked as used
            nonce_record = Nonce.query.filter_by(nonce=challenge['nonce']).first()
            assert nonce_record.used is True

    def test_nonce_cannot_be_reused(self, app):
        """Test that a nonce cannot be used twice"""
        with app.app_context():
            # Create a signing key
            signing_key = SigningKey.generate()
            # Use base58 encoding for Solana wallet address
            import base58
            wallet_address = base58.b58encode(signing_key.verify_key.encode()).decode('utf-8')

            # Generate challenge
            challenge = generate_auth_challenge(wallet_address)

            # Sign the message
            message = challenge['message']
            signed = signing_key.sign(message.encode('utf-8'))
            signature_b64 = base64.b64encode(signed.signature).decode('utf-8')

            # First verification - should succeed
            is_valid, error = verify_wallet_signature(
                wallet_address,
                signature_b64,
                challenge['nonce']
            )
            assert is_valid is True

            # Second verification with same nonce - should fail
            is_valid, error = verify_wallet_signature(
                wallet_address,
                signature_b64,
                challenge['nonce']
            )
            assert is_valid is False
            assert error == "Nonce already used"


class TestCleanupExpiredNonces:
    """Tests for cleanup_expired_nonces function"""

    def test_removes_expired_nonces(self, app):
        """Test that expired nonces are removed"""
        with app.app_context():
            # Add some nonces to database
            current_time = datetime.now(UTC)

            expired1 = Nonce(
                nonce='expired1',
                wallet_address='wallet1',
                expires_at=current_time - timedelta(seconds=100),
                used=False
            )
            expired2 = Nonce(
                nonce='expired2',
                wallet_address='wallet2',
                expires_at=current_time - timedelta(seconds=50),
                used=False
            )
            valid = Nonce(
                nonce='valid',
                wallet_address='wallet3',
                expires_at=current_time + timedelta(seconds=100),
                used=False
            )

            db.session.add_all([expired1, expired2, valid])
            db.session.commit()

            cleanup_expired_nonces()

            assert Nonce.query.filter_by(nonce='expired1').first() is None
            assert Nonce.query.filter_by(nonce='expired2').first() is None
            assert Nonce.query.filter_by(nonce='valid').first() is not None

    def test_keeps_valid_nonces(self, app):
        """Test that non-expired nonces are kept"""
        with app.app_context():
            current_time = datetime.now(UTC)

            valid1 = Nonce(
                nonce='valid1',
                wallet_address='wallet1',
                expires_at=current_time + timedelta(seconds=100),
                used=False
            )
            valid2 = Nonce(
                nonce='valid2',
                wallet_address='wallet2',
                expires_at=current_time + timedelta(seconds=200),
                used=True  # Even if used
            )

            db.session.add_all([valid1, valid2])
            db.session.commit()

            cleanup_expired_nonces()

            assert Nonce.query.filter_by(nonce='valid1').first() is not None
            assert Nonce.query.filter_by(nonce='valid2').first() is not None

    def test_empty_store(self, app):
        """Test cleanup on empty database doesn't error"""
        with app.app_context():
            cleanup_expired_nonces()  # Should not raise
            assert Nonce.query.count() == 0

    def test_cleanup_returns_count(self, app):
        """Test that cleanup returns number of removed nonces"""
        with app.app_context():
            current_time = datetime.now(UTC)

            # Add 3 expired nonces
            for i in range(3):
                nonce = Nonce(
                    nonce=f'expired_{i}',
                    wallet_address=f'wallet_{i}',
                    expires_at=current_time - timedelta(seconds=100),
                    used=False
                )
                db.session.add(nonce)

            # Add 2 valid nonces
            for i in range(2):
                nonce = Nonce(
                    nonce=f'valid_{i}',
                    wallet_address=f'wallet_{i}',
                    expires_at=current_time + timedelta(seconds=100),
                    used=False
                )
                db.session.add(nonce)

            db.session.commit()

            removed_count = cleanup_expired_nonces()

            assert removed_count == 3
            assert Nonce.query.count() == 2


class TestAuthEndpoints:
    """Tests for authentication API endpoints"""

    def test_get_challenge_success(self, client):
        """Test successful challenge generation"""
        response = client.post(
            '/auth/auth/challenge',
            json={'wallet_address': 'test_wallet_123'}
        )

        assert response.status_code == 200
        data = response.get_json()

        assert 'challenge' in data
        assert 'expires_in' in data
        assert data['expires_in'] == TTL_IN_SECONDS

        challenge = data['challenge']
        assert 'nonce' in challenge
        assert 'message' in challenge
        assert 'timestamp' in challenge

    def test_get_challenge_missing_wallet_address(self, client):
        """Test challenge generation fails without wallet address"""
        response = client.post(
            '/auth/auth/challenge',
            json={}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data
        assert data['error'] == 'Wallet address required'

    def test_get_challenge_rate_limiting(self, client):
        """Test rate limiting on challenge endpoint"""
        wallet_address = 'test_wallet_123'

        # Make 5 requests (should all succeed)
        for i in range(5):
            response = client.post(
                '/auth/auth/challenge',
                json={'wallet_address': wallet_address}
            )
            assert response.status_code == 200

        # 6th request should be rate limited
        response = client.post(
            '/auth/auth/challenge',
            json={'wallet_address': wallet_address}
        )
        assert response.status_code == 429  # Too Many Requests

    def test_verify_signature_missing_fields(self, client):
        """Test verify endpoint with missing fields"""
        # Missing all fields
        response = client.post('/auth/auth/verify', json={})
        assert response.status_code == 400

        # Missing signature
        response = client.post(
            '/auth/auth/verify',
            json={'wallet_address': 'addr', 'nonce': 'nonce'}
        )
        assert response.status_code == 400

        # Missing nonce
        response = client.post(
            '/auth/auth/verify',
            json={'wallet_address': 'addr', 'signature': 'sig'}
        )
        assert response.status_code == 400

    def test_verify_signature_invalid_nonce(self, client):
        """Test verify endpoint with invalid nonce"""
        response = client.post(
            '/auth/auth/verify',
            json={
                'wallet_address': 'test_wallet',
                'signature': 'fake_signature',
                'nonce': 'invalid_nonce'
            }
        )

        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data

    @patch('app.mod_common.auth.verify_wallet_signature')
    def test_verify_signature_success(self, mock_verify, client, app):
        """Test successful signature verification"""
        # Mock successful verification
        mock_verify.return_value = (True, None)

        response = client.post(
            '/auth/auth/verify',
            json={
                'wallet_address': 'test_wallet',
                'signature': 'valid_signature',
                'nonce': 'valid_nonce'
            }
        )

        assert response.status_code == 200
        data = response.get_json()

        assert 'token' in data
        assert 'wallet_address' in data
        assert 'expires_in' in data
        assert data['wallet_address'] == 'test_wallet'
        assert data['expires_in'] == 1800  # 30 minutes in seconds

        # Verify JWT token is valid
        token = data['token']
        payload = jwt.decode(
            token,
            app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        assert payload['wallet_address'] == 'test_wallet'

    @patch('app.mod_common.auth.verify_wallet_signature')
    def test_verify_signature_creates_session(self, mock_verify, client):
        """Test that successful verification creates session"""
        mock_verify.return_value = (True, None)

        with client.session_transaction() as sess:
            assert 'wallet_address' not in sess
            assert 'authenticated' not in sess

        response = client.post(
            '/auth/auth/verify',
            json={
                'wallet_address': 'test_wallet',
                'signature': 'valid_signature',
                'nonce': 'valid_nonce'
            }
        )

        assert response.status_code == 200

        with client.session_transaction() as sess:
            assert sess['wallet_address'] == 'test_wallet'
            assert sess['authenticated'] is True


    def test_auth_stats_endpoint(self, app, client):
        """Test the stats endpoint returns correct information"""
        with app.app_context():
            current_time = datetime.now(UTC)

            # Add various nonces to database
            expired_used = Nonce(
                nonce='expired_used',
                wallet_address='wallet1',
                expires_at=current_time - timedelta(seconds=100),
                used=True
            )
            expired_unused = Nonce(
                nonce='expired_unused',
                wallet_address='wallet2',
                expires_at=current_time - timedelta(seconds=50),
                used=False
            )
            valid_used = Nonce(
                nonce='valid_used',
                wallet_address='wallet3',
                expires_at=current_time + timedelta(seconds=100),
                used=True
            )
            valid_unused = Nonce(
                nonce='valid_unused',
                wallet_address='wallet4',
                expires_at=current_time + timedelta(seconds=200),
                used=False
            )

            db.session.add_all([expired_used, expired_unused, valid_used, valid_unused])
            db.session.commit()

            response = client.get('/auth/auth/stats')

            assert response.status_code == 200
            data = response.get_json()

            assert 'before_cleanup' in data
            assert 'after_cleanup' in data
            assert 'timestamp' in data

            # Before cleanup: 4 total, 2 used, 2 unused, 2 expired
            before = data['before_cleanup']
            assert before['total'] == 4
            assert before['used'] == 2
            assert before['unused'] == 2
            assert before['expired'] == 2

            # After cleanup: 2 remaining (valid ones), 2 cleaned (expired)
            after = data['after_cleanup']
            assert after['total'] == 2
            assert after['cleaned'] == 2

    def test_challenge_endpoint_triggers_cleanup(self, app, client):
        """Test that challenge endpoint automatically cleans up expired nonces"""
        with app.app_context():
            current_time = datetime.now(UTC)

            # Add expired nonce to database
            expired1 = Nonce(
                nonce='expired1',
                wallet_address='wallet1',
                expires_at=current_time - timedelta(seconds=100),
                used=False
            )
            db.session.add(expired1)
            db.session.commit()

            # Request new challenge (should trigger cleanup)
            response = client.post(
                '/auth/auth/challenge',
                json={'wallet_address': 'new_wallet'}
            )

            assert response.status_code == 200

            # Expired nonce should be gone
            assert Nonce.query.filter_by(nonce='expired1').first() is None

            # But new challenge nonce should be present
            data = response.get_json()
            new_nonce = data['challenge']['nonce']
            assert Nonce.query.filter_by(nonce=new_nonce).first() is not None

    def test_verify_endpoint_triggers_cleanup(self, app, client):
        """Test that verify endpoint automatically cleans up expired nonces"""
        with app.app_context():
            current_time = datetime.now(UTC)

            # Add expired nonce to database
            expired1 = Nonce(
                nonce='expired1',
                wallet_address='wallet1',
                expires_at=current_time - timedelta(seconds=100),
                used=False
            )
            db.session.add(expired1)
            db.session.commit()

            # Make verify request (should trigger cleanup)
            response = client.post(
                '/auth/auth/verify',
                json={
                    'wallet_address': 'test_wallet',
                    'signature': 'fake_signature',
                    'nonce': 'invalid_nonce'
                }
            )

            # Expired nonce should be gone (even though verify failed)
            assert Nonce.query.filter_by(nonce='expired1').first() is None


class TestAuthIntegration:
    """Integration tests for full authentication flow"""

    def test_full_authentication_flow(self, client, app):
        """Test complete flow from challenge to verification"""
        # Generate signing key
        signing_key = SigningKey.generate()
        # Use base58 encoding for Solana wallet address
        import base58
        wallet_address = base58.b58encode(signing_key.verify_key.encode()).decode('utf-8')

        # Step 1: Request challenge
        response = client.post(
            '/auth/auth/challenge',
            json={'wallet_address': wallet_address}
        )
        assert response.status_code == 200
        challenge_data = response.get_json()
        challenge = challenge_data['challenge']

        # Step 2: Sign the message
        message = challenge['message']
        signed = signing_key.sign(message.encode('utf-8'))
        signature_b64 = base64.b64encode(signed.signature).decode('utf-8')

        # Step 3: Verify signature
        response = client.post(
            '/auth/auth/verify',
            json={
                'wallet_address': wallet_address,
                'signature': signature_b64,
                'nonce': challenge['nonce']
            }
        )

        assert response.status_code == 200
        verify_data = response.get_json()

        assert 'token' in verify_data
        assert verify_data['wallet_address'] == wallet_address

        # Verify JWT is valid
        token = verify_data['token']
        payload = jwt.decode(
            token,
            app.config['SECRET_KEY'],
            algorithms=['HS256']
        )
        assert payload['wallet_address'] == wallet_address
        assert 'exp' in payload
        assert 'iat' in payload
