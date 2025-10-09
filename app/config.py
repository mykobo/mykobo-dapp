import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config(object):
    SECRET_KEY = os.environ.get("SECRET_KEY")
    LOGLEVEL = os.environ.get("LOGLEVEL", "DEBUG")
    IDENTITY_ACCESS_KEY = os.environ.get("IDENTITY_ACCESS_KEY")
    IDENTITY_SECRET_KEY = os.environ.get("IDENTITY_SECRET_KEY")
    IDENTITY_SERVICE_HOST = os.environ.get("IDENTITY_SERVICE_HOST")
    WALLET_SERVICE_HOST = os.environ.get("WALLET_SERVICE_HOST")
    LEDGER_SERVICE_HOST = os.environ.get("LEDGER_SERVICE_HOST")
    SERVICE_PORT = os.environ.get("SERVICE_PORT")
    GATEWAY_URL = os.environ.get("GATEWAY_URL")
    BUSINESS_SERVER_HOST = os.environ.get("BUSINESS_SERVER_HOST")
    IDENFY_SERVICE_HOST = os.environ.get("IDENFY_SERVICE_HOST")
    FEE_ENDPOINT = f"{BUSINESS_SERVER_HOST}/fees"
    IBAN = os.environ.get("IBAN")
    TRANSACTION_TOPIC = os.environ.get("TRANSACTION_TOPIC")

class Development(Config):
    LOGLEVEL = os.environ.get("LOGLEVEL", "DEBUG")
    DEBUG = True
    FLASK_ENV = "development"
    FLASK_DEBUG = 1


class Production(Config):
    LOGLEVEL = os.environ.get("LOGLEVEL", "INFO")
    FLASK_ENV = "production"


CONFIG_MAP = {"development": Development, "production": Production}
