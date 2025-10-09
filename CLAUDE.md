# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MYKOBO DAPP is a Flask-based web application that integrates with multiple microservices including Identity, Wallet, Ledger, and Business Server. The application uses Stellar blockchain for handling cryptocurrency transactions (EURC).

## Development Commands

### Running the Application

Development mode (uses Flask development server):
```bash
ENV=development flask --app "app:create_app('development')" run
```

Production mode (uses Gunicorn):
```bash
ENV=production gunicorn -w 4 -b :8000 "app:create_app('production')"
```

Using boot.sh (auto-selects based on ENV):
```bash
ENV=development ./boot.sh  # Runs Flask dev server
ENV=production WORKER_COUNT=4 SERVICE_PORT=8000 ./boot.sh  # Runs Gunicorn
```

### Dependency Management

This project uses `uv` for dependency management. Install dependencies:
```bash
uv sync
```

## Architecture

### Application Factory Pattern

The app uses the Flask application factory pattern via `create_app(env)` in `app/__init__.py:8`. The factory:
- Loads environment-specific configuration from `CONFIG_MAP` in `app/config.py:39`
- Loads `.env` file only in development mode (`app/__init__.py:11-12`)
- Registers blueprints (currently only `common_bp` from `app/mod_common`)

### Configuration System

Environment-based configurations in `app/config.py`:
- **Base Config**: Contains shared settings for all external services (Identity, Wallet, Ledger, Business Server, iDenfy, Stellar)
- **Development**: DEBUG enabled, LOGLEVEL defaults to DEBUG
- **Production**: DEBUG disabled, LOGLEVEL defaults to INFO

Access config via `app.config` after initialization.

### Module Structure (Blueprints)

The app uses Flask blueprints organized under `app/mod_*` directories:
- **mod_common**: Basic routes (currently just hello world at `/`)

Each module has an `__init__.py` that exports its blueprint (e.g., `common_bp`).

### Logging

Custom colored logging system in `app/logger.py`:
- Color-coded output based on log level (blue=DEBUG, green=INFO, yellow=WARNING, red=ERROR)
- Automatically includes request IP address in logs when in request context
- IP retrieved via `retrieve_ip_address()` helper in `app/util.py:1` (handles X-Forwarded-For)
- Get handler via `get_stream_handler()` in `app/logger.py:101`

### External Service Integration

The application integrates with multiple services configured via environment variables:
- **Identity Service**: Authentication/authorization (`IDENTITY_SERVICE_HOST`, requires `IDENTITY_ACCESS_KEY` and `IDENTITY_SECRET_KEY`)
- **Wallet Service**: Manages user wallets (`WALLET_SERVICE_HOST`)
- **Ledger Service**: Transaction ledger (`LEDGER_SERVICE_HOST`)
- **Business Server**: Handles fees endpoint at `/fees` (`BUSINESS_SERVER_HOST`)
- **iDenfy Service**: KYC verification (`IDENFY_SERVICE_HOST`)

## Environment Variables

Required environment variables are defined in `app/config.py:5-25`. Key variables:
- `ENV`: "development" or "production" (determines which config class to use)
- `SECRET_KEY`: Flask secret key
- `SERVICE_PORT`, `WORKER_COUNT`: Used by boot.sh for Gunicorn
- Service endpoints: `*_SERVICE_HOST` variables
- Stellar configuration: `STELLAR_*` variables and `CIRCLE_EURC_ASSET_ISSUER`

Store these in `.env` file for development (automatically loaded).
