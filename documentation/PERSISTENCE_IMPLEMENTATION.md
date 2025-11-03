# Transaction Persistence Layer Implementation

This document summarizes the implementation of the PostgreSQL persistence layer for storing transaction records in the MYKOBO DAPP.

## Overview

A complete persistence layer has been added to store all transactions created through the dApp **before** they are sent to the ledger service. This provides:

- **Audit trail**: Complete record of all transactions
- **Debugging**: Ability to trace transaction history
- **Recovery**: Transactions saved BEFORE queue send - can retry failed sends
- **Analytics**: Query transaction data for reporting
- **Reliability**: Guaranteed no data loss even if queue/network fails

## Transaction Flow

The new transaction flow ensures data safety:

```
1. User submits transaction
   ↓
2. Create Transaction record
   ↓
3. Save to database (COMMIT)
   ↓
4. Send to SQS queue
   ↓
   ├─ Success → Update message_id & queue_sent_at
   │            └─ COMMIT
   │
   └─ Failure → Log error (transaction still in DB)
                └─ Can retry later using CLI tools
```

**Key Benefits**:
- ✅ Transaction never lost (saved before queue send)
- ✅ Can query unsent transactions: `WHERE message_id IS NULL`
- ✅ Easy retry with CLI tool or custom scripts
- ✅ Automatic tracking of send timestamp
- ✅ Idempotency protection via unique constraints

## Changes Made

### 1. Dependencies Added (`pyproject.toml`)

```toml
flask-sqlalchemy = "^3.1.1"    # ORM for database operations
flask-migrate = "^4.1.0"       # Database migrations (Alembic)
psycopg2-binary = "^2.9.11"    # PostgreSQL driver
```

### 2. Database Configuration

#### Files Created:
- **`app/database.py`** - Database initialization and Flask extension setup
- **`app/models.py`** - SQLAlchemy models (Transaction model)
- **`manage.py`** - CLI tool for database migrations
- **`DATABASE_SETUP.md`** - Complete database setup instructions

#### Configuration Added (`app/config.py`):
```python
SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
SQLALCHEMY_TRACK_MODIFICATIONS = False
SQLALCHEMY_ECHO = False  # True in development for SQL query logging
```

#### Environment Variable (`.env`):
```bash
# Important: Include search_path to use dapp schema by default
DATABASE_URL="postgresql://localhost/mykobo?options=-csearch_path%3Ddapp"
```

**Why `search_path`?**
- Sets PostgreSQL to use the `dapp` schema by default
- Without it, tables would need full qualification: `dapp.transactions`
- With it, you can simply use: `transactions`
- SQLAlchemy respects this setting for all operations

### 3. Database Schema

**Database**: `mykobo`
**Schema**: `dapp`
**Table**: `dapp.transactions`

#### Transaction Model Fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer (PK) | Primary key (auto-increment) |
| `reference` | String(255) | Unique transaction reference |
| `external_reference` | String(255) | External system reference |
| `idempotency_key` | String(255) | Prevents duplicate transactions |
| `transaction_type` | String(50) | Type: deposit, withdrawal |
| `status` | String(50) | Status: pending_payer, pending_payee, etc. |
| `incoming_currency` | String(10) | Currency being received |
| `outgoing_currency` | String(10) | Currency being sent |
| `value` | Numeric(20,6) | Transaction amount |
| `fee` | Numeric(20,6) | Transaction fee |
| `payer_id` | String(255) | ID of paying user |
| `payee_id` | String(255) | ID of receiving user |
| `first_name` | String(255) | User's first name |
| `last_name` | String(255) | User's last name |
| `wallet_address` | String(255) | User's wallet address |
| `source` | String(50) | Source: ANCHOR_SOLANA, etc. |
| `instruction_type` | String(50) | Instruction type: Transaction |
| `ip_address` | String(45) | IP address of request |
| `message_id` | String(255) | SQS message ID |
| `queue_sent_at` | DateTime | When sent to queue |
| `created_at` | DateTime | Record creation timestamp |
| `updated_at` | DateTime | Record update timestamp |

**Indexes**: Created on `reference`, `external_reference`, `idempotency_key`, `status`, `payer_id`, `payee_id`, and `wallet_address` for efficient querying.

### 4. Transaction Endpoint Updates

**File**: `app/mod_solana/transaction.py`

#### Changes:
1. **Import database components**:
   ```python
   from app.database import db
   from app.models import Transaction as TransactionModel
   ```

2. **Create and save transaction record BEFORE sending to queue**:
   ```python
   transaction_record = TransactionModel.from_ledger_payload(
       ledger_payload=ledger_payload,
       wallet_address=wallet_address
   )

   # Save to database FIRST
   db.session.add(transaction_record)
   db.session.commit()
   ```

3. **Update with message ID after successful queue send**:
   ```python
   transaction_record.message_id = queue_response['MessageId']
   transaction_record.queue_sent_at = datetime.now()
   db.session.commit()
   ```

4. **Error handling**: Transaction saved BEFORE queue send, allowing retry on failure

### 5. Model Helper Methods

#### `Transaction.from_ledger_payload()`
Creates a Transaction instance from the ledger payload structure:
```python
transaction = Transaction.from_ledger_payload(
    ledger_payload=ledger_payload,
    wallet_address=wallet_address,
    message_id=optional_message_id
)
```

#### `Transaction.to_dict()`
Converts transaction to dictionary format for API responses:
```python
tx_dict = transaction.to_dict()
# Returns: {'id': 1, 'reference': 'TX123', 'value': '100.00', ...}
```

### 6. Transaction Retry Utilities

**Files**:
- `app/transaction_retry.py` - Retry utility functions
- `retry_transactions.py` - CLI tool for managing failed transactions

#### Retry Functions:

1. **`get_unsent_transactions(limit)`** - Get transactions where `message_id` is NULL
2. **`retry_transaction(transaction)`** - Retry sending a single transaction
3. **`retry_unsent_transactions(limit)`** - Retry all unsent transactions
4. **`get_transaction_stats()`** - Get statistics about sent/unsent transactions

#### CLI Usage:

```bash
# List all unsent transactions
poetry run python retry_transactions.py list

# Show statistics
poetry run python retry_transactions.py stats

# Retry specific transaction by database ID
poetry run python retry_transactions.py retry 123

# Retry all unsent transactions
poetry run python retry_transactions.py retry-all
```

### 7. Tests Created

**File**: `tests/test_transaction_persistence.py`

Test coverage includes:
- ✅ Creating transactions from ledger payloads
- ✅ Converting transactions to dictionaries
- ✅ String representation
- ✅ Saving and retrieving from database
- ✅ Unique constraint enforcement
- ✅ Automatic timestamp setting

## Database Setup Steps

### Prerequisites
1. PostgreSQL installed and running
2. Access to create databases and schemas

### Quick Setup

```bash
# 1. Create database and schema
psql -U postgres
CREATE DATABASE mykobo;
\c mykobo
CREATE SCHEMA IF NOT EXISTS dapp;
\q

# 2. Set environment variable
echo 'DATABASE_URL="postgresql://localhost/mykobo"' >> .env

# 3. Initialize migrations
ENV=development DATABASE_URL="postgresql://localhost/mykobo" poetry run python manage.py db init

# 4. Create migration
ENV=development DATABASE_URL="postgresql://localhost/mykobo" poetry run python manage.py db migrate -m "Initial migration: add transactions table"

# 5. Apply migration
ENV=development DATABASE_URL="postgresql://localhost/mykobo" poetry run python manage.py db upgrade
```

For detailed setup instructions, see `DATABASE_SETUP.md`.

## Usage Examples

### Creating a Transaction Record

```python
from app.models import Transaction
from app.database import db

# Create from ledger payload
transaction = Transaction.from_ledger_payload(
    ledger_payload=ledger_payload,
    wallet_address="ABC123XYZ789"
)

# Save to database
db.session.add(transaction)
db.session.commit()
```

### Querying Transactions

```python
# Get by reference
tx = Transaction.query.filter_by(reference="TX123456").first()

# Get by wallet address
user_txs = Transaction.query.filter_by(wallet_address="ABC123").all()

# Get pending transactions
pending = Transaction.query.filter_by(status="pending_payer").all()

# Get recent transactions
recent = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()

# Get unsent transactions (not sent to queue yet)
unsent = Transaction.query.filter(Transaction.message_id.is_(None)).all()

# Get transactions sent in last hour
from datetime import datetime, timedelta
recent_sent = Transaction.query.filter(
    Transaction.queue_sent_at >= datetime.now() - timedelta(hours=1)
).all()
```

### Retrying Failed Transactions

```python
from app.transaction_retry import retry_transaction, get_unsent_transactions

# Get all unsent transactions
unsent = get_unsent_transactions(limit=100)

# Retry a specific transaction
transaction = Transaction.query.get(123)
result = retry_transaction(transaction)

if result['success']:
    print(f"Sent with message ID: {result['message_id']}")
else:
    print(f"Failed: {result['error']}")
```

### Using the CLI Tool

```bash
# Check how many transactions need retry
poetry run python retry_transactions.py stats

# List unsent transactions
poetry run python retry_transactions.py list

# Retry specific transaction
poetry run python retry_transactions.py retry 123

# Retry all unsent transactions (batch)
poetry run python retry_transactions.py retry-all
```

### Running Migrations

```bash
# Create a new migration after model changes
poetry run python manage.py db migrate -m "Add new field to transactions"

# Apply migrations
poetry run python manage.py db upgrade

# Rollback migration
poetry run python manage.py db downgrade

# See migration history
poetry run python manage.py db history
```

## Production Considerations

1. **Connection Pooling**: SQLAlchemy handles connection pooling automatically
2. **SSL Connections**: Use `?sslmode=require` in DATABASE_URL for production
3. **Backup Strategy**: Implement regular database backups
4. **Monitoring**: Monitor database connections and query performance
5. **Indexes**: Current indexes support common queries; add more as needed
6. **Data Retention**: Consider archiving old transactions

## Monitoring and Automation

### Monitoring Unsent Transactions

You can set up monitoring to alert when transactions fail to send:

```python
# Example monitoring script
from app.transaction_retry import get_transaction_stats

stats = get_transaction_stats()

if stats['unsent'] > 10:
    # Send alert via email/Slack/etc
    alert(f"Warning: {stats['unsent']} transactions pending in database")
```

### Automated Retry with Cron

Set up a cron job to automatically retry failed transactions:

```bash
# Edit crontab
crontab -e

# Add line to retry every 5 minutes
*/5 * * * * cd /path/to/dapp && ENV=production poetry run python retry_transactions.py retry-all >> /var/log/transaction-retry.log 2>&1
```

### Health Check Endpoint

You can create an endpoint to check transaction health:

```python
@app.route('/health/transactions')
def transaction_health():
    stats = get_transaction_stats()
    return jsonify({
        'status': 'healthy' if stats['unsent'] < 100 else 'warning',
        'unsent_count': stats['unsent'],
        'total_count': stats['total']
    })
```

## Future Enhancements

Potential improvements:
- ✅ **Automated retry** - Background worker to retry failed transactions
- Add transaction status update endpoints
- Implement transaction search/filter API
- Add database-level constraints for business logic
- Create views for common transaction queries
- Add soft delete functionality
- Implement transaction history/audit log
- Add retry attempt counter and max retry limit
- Create dashboard for transaction monitoring

## Troubleshooting

### Common Issues

1. **"No module named 'flask_sqlalchemy'"**
   - Run: `uv pip install flask-sqlalchemy flask-migrate psycopg2-binary`

2. **"fe_sendauth: no password supplied"**
   - Add password to DATABASE_URL or configure PostgreSQL peer authentication

3. **"permission denied for schema dapp"**
   - Grant schema privileges: `GRANT ALL ON SCHEMA dapp TO your_user`

4. **Migration conflicts**
   - Reset migrations: Remove `migrations/` folder and reinitialize

For more troubleshooting tips, see `DATABASE_SETUP.md`.

## Docker Deployment

The application includes a complete Docker setup with background retry worker:

### Quick Start

```bash
# Start all services (web + worker + postgres)
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py db upgrade

# View worker logs
docker-compose logs -f worker
```

### Services

1. **Web Service** - Flask/Gunicorn on port 8000
2. **Worker Service** - Background retry worker (checks every 5 minutes)
3. **PostgreSQL** - Database with `dapp` schema

The same Docker image runs both services, controlled by the entrypoint:
- `./entrypoint.sh web` - Runs web application
- `./entrypoint.sh worker` - Runs retry worker

### Configuration

```bash
# .env.docker
RETRY_INTERVAL=300    # Check every 5 minutes
MAX_RETRIES=100       # Process up to 100 per cycle
```

See `DOCKER_QUICKSTART.md` and `DOCKER_DEPLOYMENT.md` for complete details.

## Summary

The persistence layer is now fully implemented and production-ready. All transactions created through the `/new` endpoint will be automatically saved to the `dapp.transactions` table in the `mykobo` database **before** being sent to the queue.

**Key Features**:
- ✅ Zero data loss (save before queue send)
- ✅ Automatic retry via background worker
- ✅ Docker deployment with docker-compose
- ✅ Comprehensive error handling
- ✅ Complete test suite
- ✅ CLI tools for manual intervention
- ✅ Monitoring and statistics

**Next Steps**:
1. **Local Development**: Set up PostgreSQL following `DATABASE_SETUP.md`
2. **Docker Deployment**: Use `docker-compose up -d` (see `DOCKER_QUICKSTART.md`)
3. **Run Migrations**: Create the database schema
4. **Monitor**: Check worker logs and transaction stats
5. **Scale**: Add more worker instances as needed
