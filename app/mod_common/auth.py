import secrets
import time
from datetime import datetime, UTC, timedelta
from typing import Dict, Optional

import jwt
from flask import session, Blueprint, request, jsonify, current_app, make_response
from nacl.signing import VerifyKey
from nacl.encoding import Base64Encoder
import base64
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import base58

from app.database import db
from app.models import Nonce

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

TTL_IN_SECONDS = 300 # 5 minutes

def generate_auth_challenge(wallet_address: str, ttl_in_seconds: int = TTL_IN_SECONDS) -> Dict[str, str]:
    """
    Generate a challenge for wallet authentication.

    Args:
        wallet_address: The wallet address requesting authentication
        ttl_in_seconds: Time-to-live for the nonce in seconds (default: 300)

    Returns:
        Dict with nonce and message to sign
    """
    # Generate cryptographically secure nonce
    nonce_value = secrets.token_urlsafe(32)
    timestamp = int(time.time())

    # Create nonce record in database
    expires_at = datetime.fromtimestamp(timestamp + ttl_in_seconds, tz=UTC)
    nonce_record = Nonce(
        nonce=nonce_value,
        wallet_address=wallet_address,
        expires_at=expires_at,
        used=False
    )

    db.session.add(nonce_record)
    db.session.commit()

    # Message to sign - includes timestamp to prevent replay attacks
    message = f"Sign this message to authenticate with MYKOBO DAPP.\n\nNonce: {nonce_value}\nTimestamp: {timestamp}"

    return {
        'nonce': nonce_value,
        'message': message,
        'timestamp': timestamp
    }

def verify_wallet_signature(
        wallet_address: str,
        signature: str,
        nonce: str
) -> tuple[bool, Optional[str]]:
    """
    Verify wallet signature (supports both Ethereum and Solana).

    Returns:
        (is_valid, error_message)
    """
    try:
        # Check nonce exists in database
        nonce_record = Nonce.query.filter_by(nonce=nonce).first()

        if not nonce_record:
            return False, "Invalid or expired nonce"

        # Check if already used (prevent replay attacks)
        if nonce_record.used:
            return False, "Nonce already used"

        # Check expiration
        if nonce_record.is_expired():
            db.session.delete(nonce_record)
            db.session.commit()
            return False, "Nonce expired"

        # Check wallet address matches
        if nonce_record.wallet_address != wallet_address:
            return False, "Wallet address mismatch"

        # Reconstruct the message that was signed
        # Calculate timestamp from expires_at (expires_at = timestamp + TTL)
        original_timestamp = int(nonce_record.expires_at.timestamp()) - TTL_IN_SECONDS
        message = f"Sign this message to authenticate with MYKOBO DAPP.\n\nNonce: {nonce}\nTimestamp: {original_timestamp}"

        # Detect wallet type based on address format
        is_solana = not wallet_address.startswith('0x')

        if is_solana:
            # Solana address: base58 encoded, need to decode to get 32-byte public key
            try:
                public_key_bytes = base58.b58decode(wallet_address)
                if len(public_key_bytes) != 32:
                    return False, f"Invalid Solana public key length: {len(public_key_bytes)} bytes"

                verify_key = VerifyKey(public_key_bytes)
                verify_key.verify(
                    message.encode('utf-8'),
                    base64.b64decode(signature)
                )
            except Exception as e:
                return False, f"Solana signature verification failed: {str(e)}"
        else:
            # Ethereum address: use Base64Encoder for the address
            verify_key = VerifyKey(wallet_address.encode("utf-8"), encoder=Base64Encoder)
            verify_key.verify(
                message.encode('utf-8'),
                base64.b64decode(signature)
            )

        # Mark nonce as used
        nonce_record.mark_used()
        db.session.commit()

        return True, None

    except Exception as e:
        db.session.rollback()
        return False, f"Signature verification failed: {str(e)}"

def cleanup_expired_nonces():
    """
    Remove expired nonces from database.

    Returns:
        int: Number of nonces removed
    """
    # Get all nonces and check expiry using the model's is_expired method
    all_nonces = Nonce.query.all()
    expired_nonces = [n for n in all_nonces if n.is_expired()]
    count = len(expired_nonces)

    # Delete expired nonces
    for nonce in expired_nonces:
        db.session.delete(nonce)

    if count > 0:
        db.session.commit()

    return count

@auth_bp.route('/auth/challenge', methods=['POST'])
@limiter.limit("5 per minute")
def get_auth_challenge():
    """
    Request an authentication challenge.

    Payload: {"wallet_address": "base58_address"}
    """
    # Clean up expired nonces before generating new challenge
    cleanup_expired_nonces()

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
    # Clean up expired nonces before verifying
    cleanup_expired_nonces()

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
            'exp': datetime.now(UTC) + timedelta(minutes=30),
            'iat': datetime.now(UTC)
        },
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )

    # Store in session as backup
    session['wallet_address'] = wallet_address
    session['authenticated'] = True

    response = make_response(jsonify({
        'token': token,
        'wallet_address': wallet_address,
        'expires_in': 86400  # 24 hours
    }), 200)

    response.set_cookie('auth_token', token, max_age=86400)
    response.set_cookie('wallet_address', token, max_age=86400)
    return response

@auth_bp.route('/logout', methods=['POST', 'GET'])
def logout():
    """
    Logout user by clearing session data and redirecting to home.
    """
    from flask import redirect, url_for, make_response

    # Clear session data
    session.clear()

    # Create response with redirect
    response = make_response(redirect('/'))

    # Clear any cookies
    response.set_cookie('auth_token', '', expires=0)
    response.set_cookie('wallet_address', '', expires=0)

    return response

@auth_bp.route('/auth/stats', methods=['GET'])
def get_auth_stats():
    """
    Get authentication statistics and trigger cleanup.
    Useful for monitoring and debugging.

    Returns nonce store statistics before and after cleanup.
    """
    # Get stats before cleanup
    total_nonces = Nonce.query.count()
    used_nonces = Nonce.query.filter_by(used=True).count()
    unused_nonces = total_nonces - used_nonces

    # Count expired nonces using the model's is_expired method
    all_nonces = Nonce.query.all()
    expired_nonces = sum(1 for n in all_nonces if n.is_expired())

    # Perform cleanup
    cleaned = cleanup_expired_nonces()

    current_time = datetime.now(UTC)
    return jsonify({
        'before_cleanup': {
            'total': total_nonces,
            'used': used_nonces,
            'unused': unused_nonces,
            'expired': expired_nonces
        },
        'after_cleanup': {
            'total': Nonce.query.count(),
            'cleaned': cleaned
        },
        'timestamp': current_time.timestamp()
    }), 200