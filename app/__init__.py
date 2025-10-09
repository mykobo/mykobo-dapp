import os

from dotenv import load_dotenv, find_dotenv
from flask import Flask

from app.config import CONFIG_MAP

def create_app(env):
    from app.mod_common import common_bp
    app = Flask(__name__)
    if env == "development":
        load_dotenv(find_dotenv())

    configuration = CONFIG_MAP[env]
    app.config.from_object(configuration)
    app.register_blueprint(common_bp)
    return app




