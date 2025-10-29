#!/bin/bash
#
# Script to run the Inbox Consumer service
#
# This script starts the SQS consumer that writes messages to the inbox table.
#
# Usage:
#   ./run_inbox_consumer.sh [environment]
#
# Examples:
#   ./run_inbox_consumer.sh development
#   ./run_inbox_consumer.sh production
#

set -e  # Exit on error

# Get environment from argument or default to development
ENV="${1:-${ENV:-development}}"

echo "=========================================="
echo "Inbox Consumer Startup"
echo "=========================================="
echo "Environment: $ENV"
echo "Starting at: $(date)"
echo "=========================================="

# Load environment variables from .env if in development
if [ "$ENV" = "development" ] || [ "$ENV" = "local" ]; then
    if [ -f .env ]; then
        echo "Loading environment variables from .env file..."
        export $(grep -v '^#' .env | xargs)
    else
        echo "Warning: .env file not found"
    fi
fi

# Validate required environment variables
required_vars=(
    "SECRET_KEY"
    "DATABASE_URL"
    "SQS_QUEUE_URL"
    "TRANSACTION_QUEUE_NAME"
)

missing_vars=()
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "Error: Missing required environment variables:"
    printf '  - %s\n' "${missing_vars[@]}"
    echo ""
    echo "Please set these variables in your .env file or environment"
    exit 1
fi

echo "Environment validation passed"
echo ""

# Set defaults for optional variables
export AWS_REGION="${AWS_REGION:-eu-west-1}"
export LOGLEVEL="${LOGLEVEL:-INFO}"

if [ "$ENV" = "development" ] || [ "$ENV" = "local" ]; then
    export LOGLEVEL="${LOGLEVEL:-DEBUG}"
fi

# Export ENV for the Python process
export ENV="$ENV"

echo "Configuration:"
echo "  Queue URL: $SQS_QUEUE_URL"
echo "  Queue Name: $TRANSACTION_QUEUE_NAME"
echo "  AWS Region: $AWS_REGION"
echo "  Log Level: $LOGLEVEL"
echo ""

# Run the inbox consumer
echo "Starting Inbox Consumer..."
echo "Press Ctrl+C to stop"
echo ""

# Use uv to run if available, otherwise use python directly
if command -v uv &> /dev/null; then
    exec uv run python -m app.inbox_consumer
else
    exec python -m app.inbox_consumer
fi
