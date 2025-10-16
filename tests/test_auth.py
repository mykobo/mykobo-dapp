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
    nonce_store,
    TTL_IN_SECONDS
)


class TestGenerateAuthChallenge:
    """Tests for generate_auth_challenge function"""

    def test_generates_unique_nonces(self):
        """Test that each challenge generates a unique nonce"""
        wallet_address = "test_wallet_123"

        challenge1 = generate_auth_challenge(wallet_address)
        time.sleep(0.01)  # Small delay to ensure different timestamps
        challenge2 = generate_auth_challenge(wallet_address)

        assert challenge1['nonce'] != challenge2['nonce']
        # Timestamps should be close but nonces must be unique
        assert abs(challenge1['timestamp'] - challenge2['timestamp']) <= 1

    def test_challenge_structure(self):
        """Test that challenge has correct structure"""
        wallet_address = "test_wallet_123"

        challenge = generate_auth_challenge(wallet_address)

        assert 'nonce' in challenge
        assert 'message' in challenge
        assert 'timestamp' in challenge
        assert isinstance(challenge['nonce'], str)
        assert isinstance(challenge['message'], str)
        assert isinstance(challenge['timestamp'], int)

    def test_challenge_message_format(self):
        """Test that challenge message contains required elements"""
        wallet_address = "test_wallet_123"

        challenge = generate_auth_challenge(wallet_address)

        assert "Sign this message to authenticate with MYKOBO DAPP" in challenge['message']
        assert f"Nonce: {challenge['nonce']}" in challenge['message']
        assert f"Timestamp: {challenge['timestamp']}" in challenge['message']

    def test_nonce_stored_in_store(self):
        """Test that nonce is stored with correct data"""
        nonce_store.clear()
        wallet_address = "test_wallet_123"

        challenge = generate_auth_challenge(wallet_address, ttl_in_seconds=300)

        assert challenge['nonce'] in nonce_store
        nonce_data = nonce_store[challenge['nonce']]
        assert nonce_data['wallet_address'] == wallet_address
        assert nonce_data['used'] is False
        assert nonce_data['expires_at'] > time.time()
        assert nonce_data['expires_at'] <= time.time() + 301  # Allow 1 second tolerance

    def test_custom_ttl(self):
        """Test that custom TTL is respected"""
        nonce_store.clear()
        wallet_address = "test_wallet_123"
        custom_ttl = 600  # 10 minutes

        challenge = generate_auth_challenge(wallet_address, ttl_in_seconds=custom_ttl)

        nonce_data = nonce_store[challenge['nonce']]
        expected_expiry = challenge['timestamp'] + custom_ttl
        assert abs(nonce_data['expires_at'] - expected_expiry) <= 1  # Allow 1 second tolerance


class TestVerifyWalletSignature:
    """Tests for verify_wallet_signature function"""

    def setup_method(self):
        """Clear nonce store before each test"""
        nonce_store.clear()

    def test_invalid_nonce_not_in_store(self):
        """Test verification fails for non-existent nonce"""
        is_valid, error = verify_wallet_signature(
            "wallet_address",
            "signature",
            "nonexistent_nonce"
        )

        assert is_valid is False
        assert error == "Invalid or expired nonce"

    def test_already_used_nonce(self):
        """Test verification fails for already used nonce"""
        wallet_address = "test_wallet"
        challenge = generate_auth_challenge(wallet_address)

        # Mark nonce as used
        nonce_store[challenge['nonce']]['used'] = True

        is_valid, error = verify_wallet_signature(
            wallet_address,
            "signature",
            challenge['nonce']
        )

        assert is_valid is False
        assert error == "Nonce already used"

    def test_expired_nonce(self):
        """Test verification fails for expired nonce"""
        wallet_address = "test_wallet"
        challenge = generate_auth_challenge(wallet_address)

        # Set expiry to past
        nonce_store[challenge['nonce']]['expires_at'] = time.time() - 1

        is_valid, error = verify_wallet_signature(
            wallet_address,
            "signature",
            challenge['nonce']
        )

        assert is_valid is False
        assert error == "Nonce expired"
        # Verify nonce was deleted
        assert challenge['nonce'] not in nonce_store

    def test_wallet_address_mismatch(self):
        """Test verification fails when wallet address doesn't match"""
        wallet_address = "test_wallet"
        challenge = generate_auth_challenge(wallet_address)

        is_valid, error = verify_wallet_signature(
            "different_wallet",
            "signature",
            challenge['nonce']
        )

        assert is_valid is False
        assert error == "Wallet address mismatch"

    def test_invalid_signature_format(self):
        """Test verification fails for invalid signature format"""
        wallet_address = "test_wallet"
        challenge = generate_auth_challenge(wallet_address)

        is_valid, error = verify_wallet_signature(
            wallet_address,
            "invalid_base64",
            challenge['nonce']
        )

        assert is_valid is False
        assert "verification failed" in error.lower()

    def test_signature_verification_failure(self):
        """Test verification fails for incorrect signature"""
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

    def test_successful_signature_verification(self):
        """Test successful signature verification flow"""
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
        assert nonce_store[challenge['nonce']]['used'] is True

    def test_nonce_cannot_be_reused(self):
        """Test that a nonce cannot be used twice"""
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

    def setup_method(self):
        """Clear nonce store before each test"""
        nonce_store.clear()

    def test_removes_expired_nonces(self):
        """Test that expired nonces are removed"""
        # Add some nonces
        current_time = time.time()

        nonce_store['expired1'] = {
            'wallet_address': 'wallet1',
            'expires_at': current_time - 100,
            'used': False
        }
        nonce_store['expired2'] = {
            'wallet_address': 'wallet2',
            'expires_at': current_time - 50,
            'used': False
        }
        nonce_store['valid'] = {
            'wallet_address': 'wallet3',
            'expires_at': current_time + 100,
            'used': False
        }

        cleanup_expired_nonces()

        assert 'expired1' not in nonce_store
        assert 'expired2' not in nonce_store
        assert 'valid' in nonce_store

    def test_keeps_valid_nonces(self):
        """Test that non-expired nonces are kept"""
        current_time = time.time()

        nonce_store['valid1'] = {
            'wallet_address': 'wallet1',
            'expires_at': current_time + 100,
            'used': False
        }
        nonce_store['valid2'] = {
            'wallet_address': 'wallet2',
            'expires_at': current_time + 200,
            'used': True  # Even if used
        }

        cleanup_expired_nonces()

        assert 'valid1' in nonce_store
        assert 'valid2' in nonce_store

    def test_empty_store(self):
        """Test cleanup on empty store doesn't error"""
        nonce_store.clear()
        cleanup_expired_nonces()  # Should not raise
        assert len(nonce_store) == 0


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
        assert data['expires_in'] == 86400

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
