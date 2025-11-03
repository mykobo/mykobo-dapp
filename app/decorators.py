from functools import wraps
from flask import request, jsonify, current_app, make_response, render_template, redirect, url_for
import jwt
import logging

logger = logging.getLogger(__name__)

def require_wallet_auth(f):
    """
    Decorator to protect routes requiring wallet authentication.
    Checks for token in the following order:
    1. Authorization header
    2. Cookies
    3. GET parameters
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        token_source = None

        # 1. Check Authorization header first
        auth_header = request.headers.get('Authorization')
        if auth_header:
            # Remove 'Bearer ' prefix if present
            token = auth_header[7:] if auth_header.startswith('Bearer ') else auth_header
            token_source = 'header'

        # 2. Check cookies if header didn't have token
        if not token:
            token = request.cookies.get('auth_token')
            if token:
                token_source = 'cookie'

        # 3. Check GET parameters if neither header nor cookies had token
        if not token:
            token = request.args.get('token')
            if token:
                token_source = 'query_parameter'

        # Fail if token not found in any location
        if not token:
            logger.warning(
                f"Authentication failed: No token provided - "
                f"Path: {request.path}, Method: {request.method}, IP: {request.remote_addr}"
            )
            return jsonify({'error': 'No authorization token provided'}), 401

        try:
            # Verify JWT token
            payload = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256'],
                verify=True
            )

            # Check if wallet_address is in payload
            if 'wallet_address' not in payload:
                logger.warning(
                    f"Authentication failed: Token missing wallet_address - "
                    f"Source: {token_source}, Path: {request.path}, IP: {request.remote_addr}"
                )
                return jsonify({'error': 'Invalid token'}), 401

            # Add wallet address to request context
            request.wallet_address = payload['wallet_address']

            # Log successful authentication
            logger.info(
                f"Authentication successful - "
                f"Wallet: {payload['wallet_address']}, Source: {token_source}, "
                f"Path: {request.path}, Method: {request.method}, IP: {request.remote_addr}"
            )

        except jwt.ExpiredSignatureError:
            logger.warning(
                f"Authentication failed: Token expired - "
                f"Source: {token_source}, Path: {request.path}, IP: {request.remote_addr}"
            )
            return redirect(url_for("common.home")), 301
        except jwt.InvalidTokenError:
            logger.warning(
                f"Authentication failed: Invalid token - "
                f"Source: {token_source}, Path: {request.path}, IP: {request.remote_addr}"
            )
            return jsonify({'error': 'Invalid token'}), 401

        return f(*args, **kwargs)

    return decorated_function