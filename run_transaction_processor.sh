#!/bin/bash
#
# Script to run the Transaction Processor background service
#
# This script starts the SQS consumer that processes withdrawal transactions
# and creates Solana blockchain transactions.
#
# Usage:
#   ./run_transaction_processor.sh [environment]
#
# Examples:
#   ./run_transaction_processor.sh development
#   ./run_transaction_processor.sh production
#
# Environment Variables Required:
#   ENV                              - Environment (development/production)
#   SECRET_KEY                       - Flask secret key
#   DATABASE_URL                     - PostgreSQL database URL
#   SOLANA_RPC_URL                   - Solana RPC endpoint
#   SOLANA_DISTRIBUTION_PRIVATE_KEY  - Private key for distribution wallet
#   EURC_TOKEN_MINT                  - EURC token mint address
#   USDC_TOKEN_MINT                  - USDC token mint address (optional)
#

set -e  # Exit on error

# Get environment from argument or default to development
ENV="${1:-${ENV:-development}}"

echo "=========================================="
echo "Transaction Processor Startup"
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
    "SOLANA_RPC_URL"
    "SOLANA_DISTRIBUTION_PRIVATE_KEY"
    "EURC_TOKEN_MINT"
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
echo "  Database: ${DATABASE_URL%%\?*}"  # Hide connection params
echo "  Solana RPC: $SOLANA_RPC_URL"
echo "  Log Level: $LOGLEVEL"
echo ""

# Run the transaction processor
echo "Starting Transaction Processor..."
echo "Press Ctrl+C to stop"
echo ""

# Use uv to run if available, otherwise use python directly
if command -v uv &> /dev/null; then
    exec uv run python -m app.transaction_processor
else
    exec python -m app.transaction_processor
fi
