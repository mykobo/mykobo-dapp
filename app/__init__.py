import os

import jinja2
import jinja_partials
from dotenv import load_dotenv, find_dotenv
from flask import Flask

from app.config import CONFIG_MAP
from app.mod_solana import bp as transaction_bp
from app.mod_common import common_bp, auth_bp
from app.mod_user import user_bp
from app.mod_common.auth import limiter
from mykobo_py.identity.identity import IdentityServiceClient
from mykobo_py.wallets.wallets import WalletServiceClient
from mykobo_py.message_bus.sqs.SQS import SQS
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

    wallet_service = WalletServiceClient(os.getenv("WALLET_SERVICE_HOST"), app.logger)
    app.config["WALLET_SERVICE_CLIENT"] = wallet_service
    app.config["MESSAGE_BUS"] = SQS(app.config["SQS_QUEUE_URL"])

    app.register_blueprint(common_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(transaction_bp)
    app.register_blueprint(user_bp)

    from app import filters as template_filters

    jinja_filters = {
        "currency": template_filters.currency,
        "transaction_status": template_filters.transaction_status,
        "status_to_label": template_filters.transaction_status_to_label,
        "to_human_date": template_filters.format_datetime_human,
        "truncated_account": template_filters.truncated_account,
        "asset": template_filters.asset,
    }

    jinja2.filters.FILTERS.update(jinja_filters)
    jinja_partials.register_extensions(app)

    return app




