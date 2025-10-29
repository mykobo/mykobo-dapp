#!/bin/sh
set -e

# Entrypoint script for running different MYKOBO DAPP services
# Usage:
#   ./entrypoint.sh web               - Run Flask/Gunicorn web server
#   ./entrypoint.sh worker            - Run retry worker service to make sure txs get sent to ledger
#   ./entrypoint.sh inbox-consumer    - Run inbox consumer (SQS → DB)
#   ./entrypoint.sh transaction-processor - Run transaction processor (DB → Solana)

SERVICE_TYPE="${1:-web}"

echo "Starting MYKOBO DAPP service: ${SERVICE_TYPE}"
echo "Environment: ${ENV}"

# Run database migrations before starting the service
# Set AUTO_MIGRATE=false to skip automatic migrations
if [ "${AUTO_MIGRATE:-true}" = "true" ]; then
    echo "Running database migrations..."
    python run_migrations.py
    MIGRATION_EXIT_CODE=$?

    if [ $MIGRATION_EXIT_CODE -ne 0 ]; then
        echo "Migration failed with exit code: ${MIGRATION_EXIT_CODE}"
        # Check if we should fail
        if [ "${AUTO_MIGRATE_FAIL_ON_ERROR:-false}" = "true" ]; then
            echo "Exiting due to migration failure"
            exit $MIGRATION_EXIT_CODE
        else
            echo "Continuing despite migration failure (set AUTO_MIGRATE_FAIL_ON_ERROR=true to exit on error)"
        fi
    fi
else
    echo "Skipping automatic migrations (AUTO_MIGRATE=false)"
fi

case "${SERVICE_TYPE}" in
    web)
        echo "Starting web application..."
        exec ./boot.sh
        ;;
    worker)
        echo "Starting retry worker..."
        # Default interval is 5 minutes (300 seconds)
        RETRY_INTERVAL="${RETRY_INTERVAL:-300}"
        MAX_RETRIES="${MAX_RETRIES:-100}"
        echo "Retry interval: ${RETRY_INTERVAL} seconds"
        echo "Max retries per run: ${MAX_RETRIES}"
        exec python retry_worker.py --interval "${RETRY_INTERVAL}" --max-retries "${MAX_RETRIES}"
        ;;
    inbox-consumer)
        echo "Starting inbox consumer..."
        echo "Polling SQS and writing to inbox table"
        exec python -m app.inbox_consumer
        ;;
    transaction-processor)
        echo "Starting transaction processor..."
        echo "Processing transactions from inbox table"
        exec python -m app.transaction_processor
        ;;
    *)
        echo "ERROR: Unknown service type: ${SERVICE_TYPE}"
        echo "Usage: entrypoint.sh [web|worker|inbox-consumer|transaction-processor]"
        exit 1
        ;;
esac
