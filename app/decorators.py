from functools import wraps
from flask import request, jsonify, current_app
import jwt

def require_wallet_auth(f):
    """
    Decorator to protect routes requiring wallet authentication.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'error': 'No authorization token provided'}), 401

        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]

        try:
            # Verify JWT token
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256']
            )

            # Check if wallet_address is in payload
            if 'wallet_address' not in payload:
                return jsonify({'error': 'Invalid token'}), 401

            # Add wallet address to request context
            request.wallet_address = payload['wallet_address']

        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)

    return decorated_function