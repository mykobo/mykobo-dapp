import os

from dotenv import load_dotenv, find_dotenv
from flask import Flask

from app.config import CONFIG_MAP
from app.mod_solana import bp as transaction_bp
from app.mod_common import common_bp, auth_bp
from app.mod_user import user_bp
from app.mod_common.auth import limiter
from mykobo_py.identity.identity import IdentityServiceClient
from mykobo_py.wallets.wallets import WalletServiceClient
def create_app(env):
    app = Flask(__name__)
    if env in ["development", "local"]:
        load_dotenv(find_dotenv())

    configuration = CONFIG_MAP[env]
    app.config.from_object(configuration)

    # Initialize limiter with app
    limiter.init_app(app)

    identity_service = IdentityServiceClient(os.getenv("IDENTITY_SERVICE_HOST"), app.logger)
    app.config["IDENTITY_SERVICE_CLIENT"] = identity_service

    wallet_service = WalletServiceClient(os.getenv("WALLET_SERVICE_HOST"), app)
    app.config["WALLET_SERVICE_CLIENT"] = wallet_service

    app.register_blueprint(common_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(user_bp)

    return app




