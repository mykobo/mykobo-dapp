# Inbox Pattern Implementation Summary

## Overview

Successfully implemented the **inbox pattern** for reliable message processing with Solana blockchain integration. The system processes withdrawal transactions by consuming messages from SQS, storing them in a database inbox, and creating Solana token transfers.

## Architecture

```
MYKOBO Ledger → SQS Queue → Inbox Consumer → PostgreSQL Inbox Table
                                                        ↓
                                          Transaction Processor
                                                        ↓
                                          Solana Blockchain (EURC/USDC)
```

## Message Flow

### 1. Message Structure (from MYKOBO Ledger)
```json
{
  "meta_data": {
    "created_at": "2024-08-10T16:00:50Z",
    "event": "NEW_CHAIN_PAYMENT",
    "source": "MYKOBO_LEDGER",
    "token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
    "idempotency_key": "750d17bb-5dc1-4649-ac9a-709a6a3a36b1"
  },
  "payload": {
    "reference": "MYK1747799079",
    "status": "APPROVED",
    "transaction_id": "0ef78f19-70fc-481d-bcc3-44d7dc4607ed"
  }
}
```

### 2. Inbox Consumer Process
- Polls SQS queue using `mykobo-py` client
- Extracts `idempotency_key` from `meta_data` as `message_id`
- Writes message to `dapp.inbox` table (idempotent)
- Deletes message from SQS after successful storage
- Handles duplicate messages gracefully

### 3. Transaction Processor Process
- Polls `dapp.inbox` table for `status='pending'` messages
- Extracts `reference` from message payload
- Looks up transaction in `dapp.transactions` table by `reference`
- Checks if `status='APPROVED'` and `transaction_type='WITHDRAWAL'`
- Calculates net amount: `value - fee` in `outgoing_currency`
- Creates Solana SPL token transfer (EURC/USDC)
- Updates transaction status to `completed`
- Marks inbox message as `completed`

## Components Created

### Database Models

#### `Inbox` Model (`app/models.py:140`)
```python
- message_id (unique)        # idempotency_key from message
- receipt_handle             # SQS receipt handle
- message_body (JSON)        # Full message payload
- status                     # pending/processing/completed/failed
- transaction_reference      # Extracted for quick lookup
- retry_count
- last_error
- processed_at
- processing_started_at
- received_at, created_at, updated_at
```

### Services

#### 1. Inbox Consumer (`app/inbox_consumer.py`)
- Consumes from SQS
- Writes to inbox table
- Handles idempotency
- Runs: `python -m app.inbox_consumer`

#### 2. Transaction Processor (`app/transaction_processor.py`)
- Polls inbox table
- Looks up transactions in database
- Processes `APPROVED` withdrawals
- Creates Solana transactions
- Runs: `python -m app.transaction_processor`

### Database Migration

**File**: `migrations/versions/59bdae19f453_add_inbox_table.py`

Creates `dapp.inbox` table with:
- Primary key on `id`
- Unique constraint on `message_id`
- Indexes on `message_id`, `status`, `transaction_reference`

**Run migration**:
```bash
source .venv/bin/activate
ENV=development flask --app "app:create_app('development')" db upgrade
```

### Startup Scripts

#### 1. `run_inbox_consumer.sh`
Validates environment and starts inbox consumer.

**Required env vars**:
- `DATABASE_URL`
- `SQS_QUEUE_URL`
- `TRANSACTION_QUEUE_NAME`
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

#### 2. `run_transaction_processor.sh`
Validates environment and starts transaction processor.

**Required env vars**:
- `DATABASE_URL`
- `SOLANA_RPC_URL`
- `SOLANA_DISTRIBUTION_PRIVATE_KEY`
- `EURC_TOKEN_MINT`

### Docker Integration

#### `entrypoint.sh` (Updated)
Added two new service types:
```bash
./entrypoint.sh inbox-consumer        # Runs inbox consumer
./entrypoint.sh transaction-processor # Runs transaction processor
```

#### `Dockerfile` (Updated)
- Copies new shell scripts
- Makes them executable
- Same image can run all services

**Usage**:
```bash
# Build once
docker build -t mykobo-dapp .

# Run different services
docker run --env-file .env mykobo-dapp ./entrypoint.sh web
docker run --env-file .env mykobo-dapp ./entrypoint.sh inbox-consumer
docker run --env-file .env mykobo-dapp ./entrypoint.sh transaction-processor
```

## Key Features

### ✅ Idempotency
- Uses `idempotency_key` from message as unique `message_id`
- Duplicate messages automatically ignored
- Safe to retry failed operations

### ✅ Separation of Concerns
- SQS consumption decoupled from processing
- Services can scale independently
- Inbox provides visibility and auditing

### ✅ Transaction Lookup
- Messages contain only `reference` and `status`
- Full transaction details retrieved from database
- Supports complex business logic

### ✅ Fee Calculation
- Net amount = `value - fee`
- Calculated in `outgoing_currency`
- Example: 100 USDC - 2.50 fee = 97.50 EURC sent

### ✅ Multi-Currency Support
- EURC: `HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr`
- USDC: `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`
- Automatically creates associated token accounts if needed

### ✅ Error Handling
- Failed messages marked with `retry_count` and `last_error`
- Stuck messages remain in `processing` state
- Manual retry via inbox table status update

### ✅ Graceful Shutdown
- Both services handle SIGINT/SIGTERM
- Complete current operation before exiting
- No message loss

## Configuration

### Processing Settings

**Inbox Consumer** (`app/inbox_consumer.py:38`):
- `poll_interval`: 5 seconds (SQS polling)

**Transaction Processor** (`app/transaction_processor.py:47`):
- `poll_interval`: 5 seconds (inbox polling)
- `batch_size`: 10 messages per batch
- `actionable_statuses`: `['APPROVED']`

## Deployment

### Local Development
```bash
# Terminal 1
ENV=development ./run_inbox_consumer.sh

# Terminal 2
ENV=development ./run_transaction_processor.sh
```

### Production (Systemd)
```bash
sudo systemctl start inbox-consumer
sudo systemctl start transaction-processor
```

### Production (Docker)
```bash
docker run -d --env-file .env mykobo-dapp ./entrypoint.sh inbox-consumer
docker run -d --env-file .env mykobo-dapp ./entrypoint.sh transaction-processor
```

## Monitoring

### Database Queries

**Check inbox status**:
```sql
SELECT status, COUNT(*)
FROM dapp.inbox
GROUP BY status;
```

**Find failed messages**:
```sql
SELECT id, transaction_reference, last_error, retry_count
FROM dapp.inbox
WHERE status = 'failed'
ORDER BY created_at DESC;
```

**Check processing time**:
```sql
SELECT
  transaction_reference,
  received_at,
  processing_started_at,
  processed_at,
  EXTRACT(EPOCH FROM (processed_at - received_at)) as processing_seconds
FROM dapp.inbox
WHERE status = 'completed'
ORDER BY processed_at DESC
LIMIT 10;
```

### Logs

**Inbox Consumer**:
- "Stored message in inbox: id=X, reference=Y"
- "Message X already exists in inbox"

**Transaction Processor**:
- "Found X pending message(s) in inbox"
- "Transaction [REF] - Status: APPROVED"
- "Solana transaction sent: SIGNATURE"
- "Updated transaction [REF] status to completed"

## Files Reference

| File | Purpose |
|------|---------|
| `app/models.py` | Added `Inbox` model |
| `app/inbox_consumer.py` | SQS → DB consumer |
| `app/transaction_processor.py` | DB → Solana processor |
| `migrations/versions/59bdae19f453_add_inbox_table.py` | DB migration |
| `run_inbox_consumer.sh` | Inbox consumer startup script |
| `run_transaction_processor.sh` | Transaction processor startup script |
| `entrypoint.sh` | Updated with new service types |
| `Dockerfile` | Updated to include new scripts |
| `TRANSACTION_PROCESSOR.md` | Complete documentation |
| `DOCKER_SERVICES.md` | Docker usage guide |

## Testing

### Send Test Message to SQS
```python
import boto3
import json

sqs = boto3.client('sqs')
queue_url = 'your-queue-url'

message = {
    "meta_data": {
        "created_at": "2024-08-10T16:00:50Z",
        "event": "NEW_CHAIN_PAYMENT",
        "source": "MYKOBO_LEDGER",
        "idempotency_key": "test-123"
    },
    "payload": {
        "reference": "TEST-001",
        "status": "APPROVED",
        "transaction_id": "test-tx-id"
    }
}

sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(message)
)
```

### Verify Processing
1. Check inbox table for message
2. Check transaction status updated to `completed`
3. Check inbox message status `completed`
4. Verify Solana transaction on explorer

## Next Steps

### Recommended Enhancements
- [ ] Add Solana transaction signature field to `Transaction` model
- [ ] Implement webhook notifications for completed transactions
- [ ] Add Prometheus metrics for monitoring
- [ ] Implement circuit breaker for Solana RPC failures
- [ ] Add support for additional SPL tokens
- [ ] Create admin dashboard for inbox monitoring
- [ ] Implement automatic retry for failed messages
- [ ] Add transaction priority fees support
