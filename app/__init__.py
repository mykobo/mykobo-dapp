import os

from dotenv import load_dotenv, find_dotenv
from flask import Flask

from app.config import CONFIG_MAP

def create_app(env):
    from app.mod_common import common_bp, auth_bp
    from app.mod_common.auth import limiter

    app = Flask(__name__)
    if env == "development":
        load_dotenv(find_dotenv())

    configuration = CONFIG_MAP[env]
    app.config.from_object(configuration)

    # Initialize limiter with app
    limiter.init_app(app)

    app.register_blueprint(common_bp)
    app.register_blueprint(auth_bp)

    return app




