import os

from dotenv import load_dotenv, find_dotenv
from flask import Flask

from app.config import CONFIG_MAP
from app.mod_solana import transaction_bp
from app.mod_common import common_bp, auth_bp
from app.mod_user import user_bp
from app.mod_common.auth import limiter

def create_app(env):
    app = Flask(__name__)
    if env == "development":
        load_dotenv(find_dotenv())

    configuration = CONFIG_MAP[env]
    app.config.from_object(configuration)

    # Initialize limiter with app
    limiter.init_app(app)

    app.register_blueprint(common_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(user_bp)

    return app




