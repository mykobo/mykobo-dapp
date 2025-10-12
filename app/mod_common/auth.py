import secrets
import time
from datetime import datetime, UTC, timedelta
from typing import Dict, Optional

import jwt
from flask import session, Blueprint, request, jsonify, current_app
from nacl.signing import VerifyKey
from nacl.encoding import Base64Encoder
import base64
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# In-memory nonce store (use Redis in production)
nonce_store = {}
TTL_IN_SECONDS = 300 # 5 minutes

def generate_auth_challenge(wallet_address: str, ttl_in_seconds: int = 300) -> Dict[str, str]:
    """
    Generate a challenge for wallet authentication.

    Returns:
        Dict with nonce and message to sign
    """
    # Generate cryptographically secure nonce
    nonce = secrets.token_urlsafe(32)
    timestamp = int(time.time())

    # Store nonce with expiration (5 minutes)
    nonce_store[nonce] = {
        'wallet_address': wallet_address,
        'expires_at': timestamp + ttl_in_seconds,
        'used': False
    }

    # Message to sign - includes timestamp to prevent replay attacks
    message = f"Sign this message to authenticate with MYKOBO DAPP.\n\nNonce: {nonce}\nTimestamp: {timestamp}"

    return {
        'nonce': nonce,
        'message': message,
        'timestamp': timestamp
    }

def verify_wallet_signature(
        wallet_address: str,
        signature: str,
        nonce: str
) -> tuple[bool, Optional[str]]:
    """
    Verify a Solana wallet signature.

    Returns:
        (is_valid, error_message)
    """
    try:
        # Check nonce exists and is valid
        if nonce not in nonce_store:
            return False, "Invalid or expired nonce"

        nonce_data = nonce_store[nonce]

        # Check if already used (prevent replay attacks)
        if nonce_data['used']:
            return False, "Nonce already used"

        # Check expiration
        if time.time() > nonce_data['expires_at']:
            del nonce_store[nonce]
            return False, "Nonce expired"

        # Check wallet address matches
        if nonce_data['wallet_address'] != wallet_address:
            return False, "Wallet address mismatch"

        # Reconstruct the message that was signed
        message = f"Sign this message to authenticate with MYKOBO DAPP.\n\nNonce: {nonce}\nTimestamp: {nonce_data['expires_at'] - 300}"

        # Verify signature using ed25519
        verify_key = VerifyKey(wallet_address.encode("utf-8"), encoder=Base64Encoder)
        verify_key.verify(
            message.encode('utf-8'),
            base64.b64decode(signature)
        )

        # Mark nonce as used
        nonce_store[nonce]['used'] = True

        return True, None

    except Exception as e:
        return False, f"Signature verification failed: {str(e)}"

def cleanup_expired_nonces():
    """Remove expired nonces from store."""
    current_time = time.time()
    expired = [
        nonce for nonce, data in nonce_store.items()
        if current_time > data['expires_at']
    ]
    for nonce in expired:
        del nonce_store[nonce]

@auth_bp.route('/auth/challenge', methods=['POST'])
@limiter.limit("5 per minute")
def get_auth_challenge():
    """
    Request an authentication challenge.

    Payload: {"wallet_address": "base58_address"}
    """
    data = request.get_json()
    wallet_address = data.get('wallet_address')

    if not wallet_address:
        return jsonify({'error': 'Wallet address required'}), 400

    challenge = generate_auth_challenge(wallet_address)

    return jsonify({
        'challenge': challenge,
        'expires_in': TTL_IN_SECONDS
    }), 200

@auth_bp.route('/auth/verify', methods=['POST'])
def verify_signature():
    """
    Verify wallet signature and issue session token.

    Payload: {
        "wallet_address": "base58_address",
        "signature": "base64_signature",
        "nonce": "challenge_nonce"
    }
    """
    data = request.get_json()
    wallet_address = data.get('wallet_address')
    signature = data.get('signature')
    nonce = data.get('nonce')

    if not all([wallet_address, signature, nonce]):
        return jsonify({'error': 'Missing required fields'}), 400

    # Verify the signature
    is_valid, error = verify_wallet_signature(wallet_address, signature, nonce)

    if not is_valid:
        return jsonify({'error': error}), 401

    # Generate JWT token
    token = jwt.encode(
        {
            'wallet_address': wallet_address,
            'exp': datetime.now(UTC) + timedelta(hours=24),
            'iat': datetime.now(UTC)
        },
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )

    # Store in session as backup
    session['wallet_address'] = wallet_address
    session['authenticated'] = True

    return jsonify({
        'token': token,
        'wallet_address': wallet_address,
        'expires_in': 86400  # 24 hours
    }), 200