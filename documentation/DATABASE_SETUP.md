# Database Setup Guide

This document provides instructions for setting up the PostgreSQL database for the MYKOBO DAPP.

## Prerequisites

- PostgreSQL installed on your system
- Database user with appropriate permissions

## Setup Steps

### 1. Create the Database

```bash
# Login to PostgreSQL
psql -U postgres

# Create the database (if it doesn't exist)
CREATE DATABASE mykobo;

# Create a user (optional, or use existing user)
CREATE USER mykobo_user WITH PASSWORD 'your_password';

# Grant privileges
GRANT ALL PRIVILEGES ON DATABASE mykobo TO mykobo_user;

# Connect to the database
\c mykobo

# Create the schema
CREATE SCHEMA IF NOT EXISTS dapp;

# Grant schema privileges
GRANT ALL PRIVILEGES ON SCHEMA dapp TO mykobo_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA dapp TO mykobo_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA dapp TO mykobo_user;

# Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA dapp GRANT ALL ON TABLES TO mykobo_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA dapp GRANT ALL ON SEQUENCES TO mykobo_user;

# Exit psql
\q
```

### 2. Update Environment Variables

Add or update the following in your `.env` file:

**Important:** Include `search_path` to use the `dapp` schema by default:

```bash
# For username/password authentication
DATABASE_URL="postgresql://mykobo_user:your_password@localhost:5432/mykobo?options=-csearch_path%3Ddapp"

# OR for peer authentication (macOS/Linux)
DATABASE_URL="postgresql:///mykobo?options=-csearch_path%3Ddapp"

# OR for socket-based authentication with your system user
DATABASE_URL="postgresql://your_system_username@localhost/mykobo?options=-csearch_path%3Ddapp"
```

**What is `search_path`?**
- Sets the default schema for database operations
- `search_path=dapp` means all tables use the `dapp` schema by default
- Without this, you'd need to qualify all table names: `dapp.transactions`
- With this, you can just use: `transactions`
- SQLAlchemy will create and query tables in the `dapp` schema automatically

### 3. Run Database Migrations

```bash
# Initialize migrations (already done)
ENV=development DATABASE_URL="your_database_url" poetry run python manage.py db init

# Create initial migration
ENV=development DATABASE_URL="your_database_url" poetry run python manage.py db migrate -m "Initial migration: add transactions table"

# Apply migration to database
ENV=development DATABASE_URL="your_database_url" poetry run python manage.py db upgrade
```

Or set the DATABASE_URL in your `.env` file and run:

```bash
poetry run python manage.py db migrate -m "Initial migration"
poetry run python manage.py db upgrade
```

## Database Schema

All tables are created in the `dapp` schema within the `mykobo` database for better organization and separation from other application data.

### Transactions Table

The `dapp.transactions` table stores all transaction records created through the dApp:

- `id` - Primary key (auto-increment)
- `reference` - Unique transaction reference
- `external_reference` - External system reference
- `idempotency_key` - Idempotency key for preventing duplicates
- `transaction_type` - Type of transaction (deposit, withdrawal)
- `status` - Transaction status (pending_payer, pending_payee, etc.)
- `incoming_currency` - Currency being received
- `outgoing_currency` - Currency being sent
- `value` - Transaction amount
- `fee` - Transaction fee
- `payer_id` - ID of the paying user
- `payee_id` - ID of the receiving user
- `first_name` - User's first name
- `last_name` - User's last name
- `wallet_address` - User's wallet address
- `source` - Transaction source (ANCHOR_SOLANA, etc.)
- `instruction_type` - Type of instruction (Transaction)
- `ip_address` - IP address of the request
- `message_id` - SQS message ID (if sent to queue)
- `queue_sent_at` - Timestamp when sent to queue
- `created_at` - Record creation timestamp
- `updated_at` - Record update timestamp

## Production Setup

For production, ensure:

1. Use a strong password for the database user
2. Enable SSL connections:
   ```
   DATABASE_URL="postgresql://user:password@host:5432/dbname?sslmode=require"
   ```
3. Set appropriate firewall rules
4. Regular database backups
5. Monitor database performance and connections

## Troubleshooting

### Connection Issues

If you get "fe_sendauth: no password supplied":
- Ensure your DATABASE_URL includes the password
- Or configure PostgreSQL for peer/trust authentication in `pg_hba.conf`

### Permission Issues

If you get "permission denied":
```sql
GRANT ALL PRIVILEGES ON DATABASE mykobo TO your_user;
GRANT ALL PRIVILEGES ON SCHEMA dapp TO your_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA dapp TO your_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA dapp TO your_user;
```

### Migration Issues

To reset migrations:
```bash
# Drop all tables
poetry run python manage.py db downgrade base

# Remove migrations folder
rm -rf migrations/

# Reinitialize
poetry run python manage.py db init
poetry run python manage.py db migrate
poetry run python manage.py db upgrade
```
