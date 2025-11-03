# Docker Services - Entrypoint Usage

The `entrypoint.sh` script has been updated to support running different MYKOBO DAPP services from the same Docker image.

## Available Services

### 1. Web Application (default)
```bash
docker run mykobo-dapp ./entrypoint.sh web
```
Runs the Flask/Gunicorn web server.

### 2. Retry Worker
```bash
docker run mykobo-dapp ./entrypoint.sh worker
```
Runs the retry worker for failed queue sends.

### 3. Inbox Consumer
```bash
docker run mykobo-dapp ./entrypoint.sh inbox-consumer
```
Consumes messages from SQS and writes them to the inbox database table.

**Required Environment Variables:**
- `DATABASE_URL`
- `SQS_QUEUE_URL`
- `TRANSACTION_QUEUE_NAME`
- `AWS_REGION`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

### 4. Transaction Processor
```bash
docker run mykobo-dapp ./entrypoint.sh transaction-processor
```
Polls the inbox table and processes withdrawal transactions by creating Solana transactions.

**Required Environment Variables:**
- `DATABASE_URL`
- `SOLANA_RPC_URL`
- `SOLANA_DISTRIBUTION_PRIVATE_KEY`
- `EURC_TOKEN_MINT`
- `USDC_TOKEN_MINT` (optional)

## Running Multiple Services

To run the complete system, you need to run multiple containers from the same image:

```bash
# Terminal 1: Web application
docker run --env-file .env -p 8000:8000 mykobo-dapp ./entrypoint.sh web

# Terminal 2: Inbox consumer
docker run --env-file .env mykobo-dapp ./entrypoint.sh inbox-consumer

# Terminal 3: Transaction processor
docker run --env-file .env mykobo-dapp ./entrypoint.sh transaction-processor
```

## Database Migrations

By default, the entrypoint script runs database migrations before starting any service.

Control this behavior with environment variables:
- `AUTO_MIGRATE=true` (default) - Run migrations automatically
- `AUTO_MIGRATE=false` - Skip migrations
- `AUTO_MIGRATE_FAIL_ON_ERROR=true` - Exit if migrations fail

**Recommendation**: Only enable `AUTO_MIGRATE=true` for the web service to avoid race conditions:

```bash
# Web service - runs migrations
docker run --env-file .env -e AUTO_MIGRATE=true mykobo-dapp ./entrypoint.sh web

# Other services - skip migrations
docker run --env-file .env -e AUTO_MIGRATE=false mykobo-dapp ./entrypoint.sh inbox-consumer
docker run --env-file .env -e AUTO_MIGRATE=false mykobo-dapp ./entrypoint.sh transaction-processor
```

## Building the Image

```bash
docker build -t mykobo-dapp .
```

## Environment Variables File

Create a `.env` file with all required variables:

```bash
# Flask
ENV=production
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# SQS (for inbox consumer)
SQS_QUEUE_URL=https://sqs.region.amazonaws.com/account-id
TRANSACTION_QUEUE_NAME=transaction-queue-name
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# Solana (for transaction processor)
SOLANA_RPC_URL=https://api.devnet.solana.com
SOLANA_DISTRIBUTION_PRIVATE_KEY=your-base58-private-key
EURC_TOKEN_MINT=HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr
USDC_TOKEN_MINT=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v

# Other services
IDENTITY_SERVICE_HOST=https://identity.example.com
WALLET_SERVICE_HOST=https://wallet.example.com
LEDGER_SERVICE_HOST=https://ledger.example.com
BUSINESS_SERVER_HOST=https://business.example.com
IDENFY_SERVICE_HOST=https://idenfy.example.com
```

## Dockerfile Changes

The Dockerfile has been updated to include the inbox consumer and transaction processor scripts:
- `run_inbox_consumer.sh`
- `run_transaction_processor.sh`

Both scripts are automatically copied and made executable during the Docker build.
