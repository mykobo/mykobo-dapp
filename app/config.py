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
    SQS_QUEUE_URL = os.environ.get("SQS_QUEUE_URL")
    TRANSACTION_QUEUE_NAME = os.environ.get("TRANSACTION_QUEUE_NAME")  # will be deprecated once we move to kafka
    TRANSACTION_STATUS_UPDATE_QUEUE_NAME = os.environ.get("TRANSACTION_STATUS_UPDATE_QUEUE_NAME")
    NOTIFICATIONS_QUEUE_NAME = os.environ.get("NOTIFICATIONS_QUEUE_NAME")

    # Solana configuration
    SOLANA_RPC_URL = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    SOLANA_DISTRIBUTION_PRIVATE_KEY = os.environ.get("SOLANA_DISTRIBUTION_PRIVATE_KEY")
    USDC_TOKEN_MINT = os.environ.get("USDC_TOKEN_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")  # USDC mainnet mint
    EURC_TOKEN_MINT = os.environ.get("EURC_TOKEN_MINT", "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr")  # USDC mainnet mint

    # Database configuration
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ECHO = False

class Development(Config):
    LOGLEVEL = os.environ.get("LOGLEVEL", "DEBUG")
    DEBUG = True
    FLASK_ENV = "development"
    FLASK_DEBUG = 1
    SQLALCHEMY_ECHO = True  # Log SQL queries in development


class Production(Config):
    LOGLEVEL = os.environ.get("LOGLEVEL", "INFO")
    FLASK_ENV = "production"


CONFIG_MAP = {"local": Development, "development": Development, "production": Production}
