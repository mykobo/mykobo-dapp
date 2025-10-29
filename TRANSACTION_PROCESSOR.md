# Transaction Processor - Inbox Pattern

## Overview

The Transaction Processor implements the **inbox pattern** for reliable message processing. The system consists of two independent services:

1. **Inbox Consumer** - Consumes messages from AWS SQS and writes them to the inbox database table
2. **Transaction Processor** - Polls the inbox table and processes withdrawal transactions by creating Solana blockchain transactions

This architecture provides better transactional guarantees, idempotency, and separation of concerns.

## Features

### Inbox Consumer
- **Idempotent Message Consumption**: Duplicate messages are automatically detected and ignored
- **Persistent Storage**: Messages are stored in database before being processed
- **SQS Integration**: Uses the `mykobo-py` SQS client to consume messages
- **Automatic Cleanup**: Deletes messages from SQS after successful persistence

### Transaction Processor
- **Inbox Polling**: Polls inbox table for pending messages (no direct SQS dependency)
- **Automatic Withdrawal Processing**: Detects withdrawal transactions and creates Solana transfers
- **Fee Calculation**: Automatically calculates net amount (value minus fee) in the outgoing currency
- **Multi-Currency Support**: Supports EURC and USDC token transfers
- **Database Integration**: Updates both inbox and transaction status after processing
- **Error Handling**: Marks messages as failed with retry tracking
- **Graceful Shutdown**: Handles SIGINT/SIGTERM signals for clean shutdowns

## Architecture

### Flow Diagram

```
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
│   dApp      │────▶│  SQS Queue   │────▶│ Inbox Consumer     │
│  (Sender)   │     │              │     │                    │
└─────────────┘     └──────────────┘     └────────────────────┘
                                                   │
                                                   ▼
                                         ┌──────────────────────┐
                                         │  Write to Inbox DB   │
                                         │  (Idempotent)        │
                                         │  Delete from SQS     │
                                         └──────────────────────┘
                                                   │
                                                   ▼
                                         ┌──────────────────────┐
                                         │  Inbox Table         │
                                         │  status=pending      │
                                         └──────────────────────┘
                                                   │
                                                   ▼
                                         ┌──────────────────────┐
                                         │ Transaction          │◀──┐
                                         │ Processor            │   │
                                         │ (Polls Inbox)        │   │
                                         └──────────────────────┘   │
                                                   │                 │
                                                   ▼                 │
                                         ┌──────────────────────┐   │
                                         │  Process Message     │   │
                                         │  - Mark processing   │   │
                                         │  - Check status      │   │
                                         │  - Validate data     │   │
                                         └──────────────────────┘   │
                                                   │                 │
                                         ┌─────────┴─────────┐       │
                                         │  Should Process?  │       │
                                         └─────────┬─────────┘       │
                                                   │                 │
                                      ┌────────────┴─────────────┐   │
                                      │                          │   │
                                     YES                         NO  │
                                      │                          │   │
                                      ▼                          ▼   │
                           ┌──────────────────┐      ┌──────────────┐
                           │ Create Solana TX │      │ Mark Complete│
                           │ (value - fee)    │      └──────────────┘
                           └──────────────────┘              │
                                      │                      │
                                      ▼                      │
                           ┌──────────────────┐              │
                           │ Send to Solana   │              │
                           │ Network          │              │
                           └──────────────────┘              │
                                      │                      │
                                      ▼                      │
                           ┌──────────────────┐              │
                           │ Update TX Status │              │
                           │ Mark Complete    │              │
                           └──────────────────┘              │
                                      │                      │
                                      └──────────────────────┘
                                                   │
                                                   │ Poll again
                                                   └──────────────────┘
```

### Components

1. **InboxConsumer** (`app/inbox_consumer.py:18`): Consumes SQS messages and writes to inbox table
2. **Inbox Model** (`app/models.py:140`): Database model for storing consumed messages
3. **TransactionProcessor** (`app/transaction_processor.py:24`): Polls inbox and processes transactions
4. **Transaction Model** (`app/models.py:9`): Database model for transaction records
5. **Solana Client**: Creates and sends token transfer transactions

### Inbox Pattern Benefits

1. **Idempotency**: Messages with duplicate `message_id` are automatically rejected
2. **Decoupling**: SQS consumption and processing are independent services
3. **Visibility**: All messages are stored in database for auditing and monitoring
4. **Retry Logic**: Failed messages can be retried without re-consuming from SQS
5. **Transactional Safety**: Inbox writes and processing use database transactions
6. **Independent Scaling**: Consumer and processor can scale separately

## Configuration

### Environment Variables

Required variables (must be set):

```bash
# Flask & Database
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:pass@host:port/dbname

# AWS SQS
SQS_QUEUE_URL=https://sqs.region.amazonaws.com/account-id
TRANSACTION_QUEUE_NAME=transaction-queue-name
AWS_REGION=eu-west-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# Solana
SOLANA_RPC_URL=https://api.devnet.solana.com
SOLANA_DISTRIBUTION_PRIVATE_KEY=base58-encoded-private-key
EURC_TOKEN_MINT=HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr

# Optional
USDC_TOKEN_MINT=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
LOGLEVEL=INFO  # DEBUG in development
```

### Inbox Consumer Settings

Configurable in `InboxConsumer.__init__()`:

- `poll_interval`: 5 seconds (time between SQS polls)

### Transaction Processor Settings

Configurable in `TransactionProcessor.__init__()`:

- `poll_interval`: 5 seconds (time between inbox polls)
- `batch_size`: 10 (number of messages to process per batch)
- `actionable_statuses`: `['pending_payee', 'processing']` (statuses that trigger Solana transactions)

## Usage

**IMPORTANT**: You need to run **BOTH** services for the system to work:
1. Inbox Consumer - consumes from SQS and writes to database
2. Transaction Processor - reads from database and processes transactions

### Database Migration

First, run the migration to create the inbox table:

```bash
source .venv/bin/activate
ENV=development flask --app "app:create_app('development')" db upgrade
```

### Starting the Services

#### Development Mode

Terminal 1 - Start Inbox Consumer:
```bash
ENV=development ./run_inbox_consumer.sh
```

Terminal 2 - Start Transaction Processor:
```bash
ENV=development ./run_transaction_processor.sh
```

Or run directly with Python:

```bash
# Terminal 1
ENV=development python -m app.inbox_consumer

# Terminal 2
ENV=development python -m app.transaction_processor
```

#### Production Mode

```bash
# Start both services
ENV=production ./run_inbox_consumer.sh &
ENV=production ./run_transaction_processor.sh &
```

### Running as a Service

#### Systemd Service (Linux)

Create `/etc/systemd/system/inbox-consumer.service`:

```ini
[Unit]
Description=MYKOBO Inbox Consumer
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=mykobo
WorkingDirectory=/opt/mykobo/dapp
Environment="ENV=production"
EnvironmentFile=/opt/mykobo/dapp/.env
ExecStart=/opt/mykobo/dapp/run_inbox_consumer.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Create `/etc/systemd/system/transaction-processor.service`:

```ini
[Unit]
Description=MYKOBO Transaction Processor
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=mykobo
WorkingDirectory=/opt/mykobo/dapp
Environment="ENV=production"
EnvironmentFile=/opt/mykobo/dapp/.env
ExecStart=/opt/mykobo/dapp/run_transaction_processor.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Start both services:

```bash
sudo systemctl daemon-reload

# Enable and start inbox consumer
sudo systemctl enable inbox-consumer
sudo systemctl start inbox-consumer
sudo systemctl status inbox-consumer

# Enable and start transaction processor
sudo systemctl enable transaction-processor
sudo systemctl start transaction-processor
sudo systemctl status transaction-processor
```

View logs:

```bash
# Inbox consumer logs
sudo journalctl -u inbox-consumer -f

# Transaction processor logs
sudo journalctl -u transaction-processor -f

# Both services
sudo journalctl -u inbox-consumer -u transaction-processor -f
```

#### Supervisor (Alternative)

Create `/etc/supervisor/conf.d/mykobo-services.conf`:

```ini
[program:inbox-consumer]
command=/opt/mykobo/dapp/run_inbox_consumer.sh production
directory=/opt/mykobo/dapp
autostart=true
autorestart=true
stderr_logfile=/var/log/inbox-consumer.err.log
stdout_logfile=/var/log/inbox-consumer.out.log
environment=ENV="production"
user=mykobo

[program:transaction-processor]
command=/opt/mykobo/dapp/run_transaction_processor.sh production
directory=/opt/mykobo/dapp
autostart=true
autorestart=true
stderr_logfile=/var/log/transaction-processor.err.log
stdout_logfile=/var/log/transaction-processor.out.log
environment=ENV="production"
user=mykobo

[group:mykobo]
programs=inbox-consumer,transaction-processor
```

Control both services:

```bash
# Start all
sudo supervisorctl start mykobo:*

# Stop all
sudo supervisorctl stop mykobo:*

# Restart all
sudo supervisorctl restart mykobo:*

# View status
sudo supervisorctl status
```

### Docker Deployment

Create separate services in `docker-compose.yml`:

```yaml
services:
  inbox-consumer:
    build: .
    command: ./run_inbox_consumer.sh production
    env_file:
      - .env
    environment:
      - ENV=production
    depends_on:
      - db
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs

  transaction-processor:
    build: .
    command: ./run_transaction_processor.sh production
    env_file:
      - .env
    environment:
      - ENV=production
    depends_on:
      - db
      - inbox-consumer  # Ensure inbox consumer starts first
    restart: unless-stopped
    volumes:
      - ./logs:/app/logs
```

## Transaction Processing Logic

### Withdrawal Flow

1. **Message Received**: Processor receives message from SQS queue
2. **Validation**: Checks if transaction type is `WITHDRAWAL` and status is actionable
3. **Fee Calculation**: Calculates net amount = `value - fee`
4. **Solana Transaction**:
   - Gets recipient wallet address from transaction record
   - Determines token mint based on `outgoing_currency`
   - Creates associated token account if needed
   - Transfers net amount in the outgoing currency
5. **Status Update**: Updates transaction status to `completed` in database
6. **Message Deletion**: Deletes message from SQS queue

### Example Message Processing

**Input Message** (SQS):
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

**Processing**:
1. Message stored in inbox table (idempotent by `idempotency_key`)
2. Transaction processor looks up `reference` in transactions table
3. Finds transaction: Type=WITHDRAWAL, value=100.00, fee=2.50, outgoing_currency=EURC
4. Status check: `APPROVED` ✓
5. Calculate: **Net Amount = 100.00 - 2.50 = 97.50 EURC**
6. Create Solana transaction for 97.50 EURC

**Output** (Solana Transaction):
- Transfer: 97.50 EURC to user's wallet address (from transactions table)
- Transaction signature recorded
- Database transaction status updated to `completed`
- Inbox message marked as `completed`

## Error Handling

### Retry Logic

The processor uses SQS's built-in retry mechanism:

1. **Visibility Timeout**: Messages become invisible for 300 seconds (5 minutes) after being received
2. **Processing Failure**: If an error occurs, the message is NOT deleted
3. **Automatic Retry**: After visibility timeout expires, the message becomes available again
4. **Dead Letter Queue**: Consider configuring a DLQ for messages that fail repeatedly

### Error Scenarios

| Error | Behavior | Recovery |
|-------|----------|----------|
| Invalid message format | Log error, delete message | Manual investigation |
| Missing wallet address | Log error, don't delete | Fix data, retry automatically |
| Solana RPC failure | Log error, don't delete | Retry after visibility timeout |
| Insufficient funds | Log error, don't delete | Add funds, retry automatically |
| Database error | Log error, don't delete | Fix DB, retry automatically |
| Network timeout | Log error, don't delete | Retry after visibility timeout |

### Monitoring Recommendations

1. **CloudWatch Alarms**: Set up alarms for:
   - Queue depth (messages waiting)
   - Processing errors
   - DLQ messages

2. **Log Monitoring**: Watch for:
   - `Fatal error in processor`
   - `Error processing message`
   - `Failed to create Solana transaction`

3. **Database Monitoring**: Track:
   - Transactions stuck in `pending_payee` status
   - Processing time metrics

## Graceful Shutdown

The processor handles shutdown signals gracefully:

```bash
# Send SIGINT (Ctrl+C)
# Or send SIGTERM
kill -TERM <pid>
```

The processor will:
1. Stop polling for new messages
2. Finish processing current message
3. Exit cleanly

## Development & Testing

### Local Testing

1. Set up local SQS (using LocalStack):

```bash
docker run -d -p 4566:4566 localstack/localstack
```

2. Create test queue:

```bash
aws --endpoint-url=http://localhost:4566 sqs create-queue --queue-name test-transactions
```

3. Update `.env`:

```bash
SQS_QUEUE_URL=http://localhost:4566/000000000000
TRANSACTION_QUEUE_NAME=test-transactions
```

4. Run processor:

```bash
ENV=development ./run_transaction_processor.sh
```

### Sending Test Messages

Use the existing transaction creation flow or send directly to SQS:

```python
import boto3
import json

sqs = boto3.client('sqs', endpoint_url='http://localhost:4566')
queue_url = 'http://localhost:4566/000000000000/test-transactions'

message = {
    "payload": {
        "reference": "TEST-001",
        "transaction_type": "WITHDRAWAL",
        "status": "pending_payee",
        "incoming_currency": "USDC",
        "outgoing_currency": "EURC",
        "value": "10.00",
        "fee": "0.50",
        "wallet_address": "YourSolanaAddressHere"
    },
    "meta_data": {
        "source": "DAPP",
        "instruction_type": "Transaction"
    }
}

sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(message)
)
```

## Security Considerations

1. **Private Key Storage**:
   - Never commit private keys to git
   - Use AWS Secrets Manager or similar in production
   - Rotate keys regularly

2. **IAM Permissions**:
   - Processor needs minimal SQS permissions: `ReceiveMessage`, `DeleteMessage`
   - Use least-privilege principle

3. **Network Security**:
   - Run in private subnet with NAT gateway
   - Restrict outbound access to Solana RPC and AWS services only

4. **Logging**:
   - Never log private keys or sensitive data
   - Sanitize logs before storing

## Troubleshooting

### Processor Not Starting

- Check environment variables: `./run_transaction_processor.sh` will validate
- Check database connectivity: `psql $DATABASE_URL`
- Check SQS connectivity: `aws sqs list-queues`

### Messages Not Being Processed

- Check queue has messages: `aws sqs get-queue-attributes --queue-url <url> --attribute-names ApproximateNumberOfMessages`
- Check processor logs for errors
- Verify transaction statuses match `actionable_statuses`

### Solana Transactions Failing

- Check RPC URL is accessible: `curl $SOLANA_RPC_URL`
- Verify private key is valid
- Check distribution wallet has sufficient funds
- Verify token mint addresses are correct

## Future Enhancements

- [ ] Add support for additional currencies (SOL, other SPL tokens)
- [ ] Implement Dead Letter Queue handling
- [ ] Add Prometheus metrics endpoint
- [ ] Support batch processing of multiple messages
- [ ] Add transaction signature tracking in database
- [ ] Implement webhook notifications for completed transactions
- [ ] Add support for priority fees on Solana
- [ ] Implement circuit breaker pattern for Solana RPC failures

## Related Files

- `app/transaction_processor.py` - Main processor implementation
- `app/models.py:9` - Transaction database model
- `app/mod_solana/transaction.py` - Solana transaction utilities
- `run_transaction_processor.sh` - Startup script
- `app/config.py` - Configuration settings
