# Transaction Retry CLI Tool

A command-line tool for managing and retrying failed transaction queue sends.

## Overview

When transactions are created, they are saved to the database **before** being sent to the SQS queue. If the queue send fails (network issue, SQS unavailable, etc.), the transaction remains in the database with `message_id = NULL`.

This tool helps you:
- List unsent transactions
- View statistics about transaction send status
- Retry individual transactions
- Batch retry all unsent transactions

## Commands

### List Unsent Transactions

View all transactions that haven't been sent to the queue:

```bash
poetry run python retry_transactions.py list
```

**Output:**
```
ID       Reference            Type         Status               Amount       Created
====================================================================================================
123      TX123456789          deposit      pending_payer        100.00       2025-10-24 10:30:00
124      TX987654321          withdrawal   pending_payee        50.00        2025-10-24 10:31:15

Total unsent: 2
```

### Show Statistics

Display summary statistics:

```bash
poetry run python retry_transactions.py stats
```

**Output:**
```
=== Transaction Statistics ===
Total transactions:  1250
Sent to queue:       1248
Unsent (pending):    2

=== By Status ===
  pending_payer             850
  pending_payee             250
  completed                 150
```

### Retry Single Transaction

Retry a specific transaction by its database ID:

```bash
poetry run python retry_transactions.py retry 123
```

**Output:**
```
Retrying transaction [TX123456789] (ID: 123)...
✓ Successfully sent to queue - Message ID: abc-def-ghi-123
```

### Retry All Unsent Transactions

Batch retry all transactions with `message_id = NULL`:

```bash
poetry run python retry_transactions.py retry-all
```

**Output:**
```
Retrying all unsent transactions...

=== Retry Summary ===
Total processed: 5
Succeeded:       4
Failed:          1

=== Failed Transactions ===
  ID 127 (TX555555555): Connection timeout
```

## How It Works

### Transaction States

1. **Created** - Transaction saved to database (`message_id = NULL`)
2. **Sent** - Successfully sent to queue (`message_id` set, `queue_sent_at` timestamp)
3. **Failed** - Queue send failed but transaction saved (`message_id = NULL`)

### Retry Logic

When you retry a transaction:

1. Tool queries database for transactions where `message_id IS NULL`
2. Reconstructs the ledger payload from the transaction record
3. Attempts to send to SQS queue
4. On success: Updates `message_id` and `queue_sent_at`
5. On failure: Logs error, transaction remains unsent

### Idempotency

The system prevents duplicate sends using:
- Unique constraints on `reference`, `external_reference`, and `idempotency_key`
- Queue deduplication via `idempotency_key` in message
- Transaction status tracking

## Usage Scenarios

### Scenario 1: SQS Outage

During an AWS SQS outage, transactions pile up unsent:

```bash
# Check the damage
poetry run python retry_transactions.py stats
# Output: Unsent (pending): 45

# After SQS recovers, retry all
poetry run python retry_transactions.py retry-all
# Output: Total processed: 45, Succeeded: 45, Failed: 0
```

### Scenario 2: Network Blip

A single transaction failed due to network issue:

```bash
# User reports transaction not processing
# Find the transaction in logs or database
poetry run python retry_transactions.py list

# Retry specific transaction
poetry run python retry_transactions.py retry 123
```

### Scenario 3: Monitoring Alert

Your monitoring system alerts "10 unsent transactions":

```bash
# Investigate
poetry run python retry_transactions.py list

# Check if it's a pattern (all same time = outage)
# Check if it's specific users/types

# Retry
poetry run python retry_transactions.py retry-all
```

## Automation

### Cron Job Setup

Automatically retry failed transactions every 5 minutes:

```bash
# Edit crontab
crontab -e

# Add this line
*/5 * * * * cd /path/to/dapp && ENV=production DATABASE_URL="postgresql://..." poetry run python retry_transactions.py retry-all >> /var/log/transaction-retry.log 2>&1
```

### Systemd Timer (Alternative to Cron)

Create `/etc/systemd/system/transaction-retry.service`:

```ini
[Unit]
Description=Retry Failed Transactions
After=network.target

[Service]
Type=oneshot
User=mykobo
WorkingDirectory=/path/to/dapp
Environment="ENV=production"
Environment="DATABASE_URL=postgresql://..."
ExecStart=/path/to/poetry run python retry_transactions.py retry-all
StandardOutput=journal
StandardError=journal
```

Create `/etc/systemd/system/transaction-retry.timer`:

```ini
[Unit]
Description=Run transaction retry every 5 minutes
Requires=transaction-retry.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
sudo systemctl enable transaction-retry.timer
sudo systemctl start transaction-retry.timer
```

## Monitoring Integration

### Prometheus Metrics

Export metrics for monitoring:

```python
from prometheus_client import Gauge

unsent_transactions = Gauge('unsent_transactions', 'Number of unsent transactions')

def update_metrics():
    stats = get_transaction_stats()
    unsent_transactions.set(stats['unsent'])
```

### Slack Alerts

Send alerts when unsent count is high:

```python
import requests

def check_and_alert():
    stats = get_transaction_stats()
    if stats['unsent'] > 10:
        requests.post(SLACK_WEBHOOK_URL, json={
            'text': f"⚠️ {stats['unsent']} transactions pending retry"
        })
```

## API Reference

### Python Functions

```python
from app.transaction_retry import (
    get_unsent_transactions,
    retry_transaction,
    retry_unsent_transactions,
    get_transaction_stats
)

# Get unsent transactions
unsent = get_unsent_transactions(limit=100)  # Returns: List[Transaction]

# Retry single transaction
result = retry_transaction(transaction)  # Returns: Dict[success, message_id, error]

# Retry all unsent
results = retry_unsent_transactions(limit=100)  # Returns: Dict[total, succeeded, failed, results]

# Get statistics
stats = get_transaction_stats()  # Returns: Dict[total, sent, unsent, by_status]
```

## Troubleshooting

### No transactions found but user reports failure

Check the database directly:

```sql
SELECT id, reference, transaction_type, status, message_id, created_at
FROM dapp.transactions
WHERE message_id IS NULL
ORDER BY created_at DESC;
```

### Retry keeps failing

1. Check SQS queue exists and is accessible
2. Verify AWS credentials are valid
3. Check network connectivity
4. Review application logs for specific errors

### Transaction stuck in retry loop

If a transaction continuously fails to send:

```python
# Mark as failed manually in database
UPDATE dapp.transactions
SET status = 'failed', message_id = 'MANUAL_FAILURE'
WHERE id = 123;
```

## Best Practices

1. **Monitor regularly** - Set up alerts for high unsent counts
2. **Automate retry** - Use cron/systemd for automatic retry
3. **Log everything** - Keep logs of retry attempts
4. **Set limits** - Don't retry infinitely (consider max attempt count)
5. **Alert on patterns** - If many transactions fail, investigate root cause
6. **Review regularly** - Check old unsent transactions periodically

## Security Notes

- Ensure DATABASE_URL is not exposed in logs
- Restrict access to retry CLI tool (production)
- Use read-only database user for monitoring queries
- Audit retry operations for compliance

## Support

For issues or questions:
- Check logs: `/var/log/transaction-retry.log`
- Review database: `SELECT * FROM dapp.transactions WHERE message_id IS NULL`
- Contact: support@mykobo.com
