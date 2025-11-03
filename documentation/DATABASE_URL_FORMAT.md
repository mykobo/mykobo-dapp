# Database URL Format Reference

Quick reference for configuring the `DATABASE_URL` environment variable.

## Standard Format

```
postgresql://[user[:password]@][host][:port]/database[?options]
```

## MYKOBO DAPP Format

**Important:** Always include `search_path=dapp` to use the dapp schema by default.

### With Username/Password

```bash
DATABASE_URL="postgresql://mykobo_user:password@localhost:5432/mykobo?options=-csearch_path%3Ddapp"
```

### Peer Authentication (macOS/Linux)

```bash
DATABASE_URL="postgresql:///mykobo?options=-csearch_path%3Ddapp"
```

### With System User

```bash
DATABASE_URL="postgresql://your_username@localhost/mykobo?options=-csearch_path%3Ddapp"
```

### Docker Compose

```bash
DATABASE_URL="postgresql://mykobo_user:changeme@postgres:5432/mykobo?options=-csearch_path%3Ddapp"
```

## URL Components Explained

| Component | Description | Example |
|-----------|-------------|---------|
| `postgresql://` | Protocol/driver | Required |
| `user` | Database username | `mykobo_user` |
| `password` | Database password | `changeme` |
| `host` | Database hostname | `localhost`, `postgres`, IP |
| `port` | Database port | `5432` (default) |
| `database` | Database name | `mykobo` |
| `?options=` | Additional options | See below |

## Options Parameter

### search_path (Required)

Sets the default schema for all database operations.

```bash
?options=-csearch_path%3Ddapp
```

**URL Encoding:**
- `%3D` = `=` (equals sign)
- `-c` = PostgreSQL command-line option prefix
- `search_path=dapp` = Set search path to dapp schema

**What it does:**
- Tables in `dapp` schema don't need qualification
- Use `transactions` instead of `dapp.transactions`
- SQLAlchemy creates and queries tables in `dapp` schema automatically

### Additional Options

You can add multiple options separated by commas:

```bash
?options=-csearch_path%3Ddapp,-cstatement_timeout%3D30000
```

Common options:
- `search_path=dapp` - Default schema
- `statement_timeout=30000` - Query timeout (30 seconds)
- `connect_timeout=10` - Connection timeout

## SSL/TLS Configuration

### Require SSL

```bash
DATABASE_URL="postgresql://user:pass@host/mykobo?sslmode=require&options=-csearch_path%3Ddapp"
```

### SSL Modes

| Mode | Description |
|------|-------------|
| `disable` | No SSL (not recommended for production) |
| `allow` | Try SSL, fall back to non-SSL |
| `prefer` | Try SSL first, fall back if needed |
| `require` | Require SSL (recommended for production) |
| `verify-ca` | Require SSL and verify certificate |
| `verify-full` | Require SSL, verify cert and hostname |

### Production Example (AWS RDS)

```bash
DATABASE_URL="postgresql://user:pass@rds-host.region.rds.amazonaws.com:5432/mykobo?sslmode=require&options=-csearch_path%3Ddapp"
```

## Environment-Specific Examples

### Development (.env)

```bash
DATABASE_URL="postgresql://localhost/mykobo?options=-csearch_path%3Ddapp"
```

### Docker Compose (.env.docker)

```bash
DATABASE_URL="postgresql://mykobo_user:changeme@postgres:5432/mykobo?options=-csearch_path%3Ddapp"
```

### Production (Kubernetes Secret)

```bash
DATABASE_URL="postgresql://prod_user:strong_password@prod-db.internal:5432/mykobo?sslmode=require&options=-csearch_path%3Ddapp"
```

### Heroku/Cloud

```bash
# Heroku sets this automatically, but you may need to add search_path
DATABASE_URL="postgresql://user:pass@host:5432/dbname?sslmode=require&options=-csearch_path%3Ddapp"
```

## Connection Pooling

SQLAlchemy handles connection pooling automatically. You can configure it in `app/config.py`:

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 10,           # Number of connections in pool
    'pool_recycle': 3600,      # Recycle connections after 1 hour
    'pool_pre_ping': True,     # Verify connections before using
    'max_overflow': 20,        # Max connections beyond pool_size
}
```

## Troubleshooting

### Connection Refused

```bash
# Check host and port
psql -h localhost -p 5432 -U mykobo_user -d mykobo
```

### Authentication Failed

```bash
# Verify username/password
psql "postgresql://mykobo_user:password@localhost/mykobo"
```

### Schema Not Found

```bash
# Verify schema exists
psql -U mykobo_user -d mykobo -c "\dn"

# Create if missing
psql -U mykobo_user -d mykobo -c "CREATE SCHEMA IF NOT EXISTS dapp;"
```

### SSL Error

```bash
# Try without SSL first
DATABASE_URL="postgresql://user:pass@host/mykobo?sslmode=disable&options=-csearch_path%3Ddapp"
```

## Testing Your URL

### Python Test

```python
from sqlalchemy import create_engine

url = "postgresql://user:pass@host/mykobo?options=-csearch_path%3Ddapp"
engine = create_engine(url)

try:
    with engine.connect() as conn:
        result = conn.execute("SELECT current_schema()")
        print(f"Current schema: {result.scalar()}")  # Should print: dapp
        print("✓ Connection successful!")
except Exception as e:
    print(f"✗ Connection failed: {e}")
```

### psql Test

```bash
psql "postgresql://user:pass@host/mykobo?options=-csearch_path%3Ddapp" -c "SHOW search_path;"
# Should output: dapp
```

### Docker Test

```bash
docker run --rm postgres:16 psql "postgresql://user:pass@host/mykobo?options=-csearch_path%3Ddapp" -c "SELECT 1;"
```

## Security Best Practices

1. **Never commit passwords** - Use environment variables
2. **Use strong passwords** - At least 16 characters
3. **Enable SSL in production** - `sslmode=require`
4. **Rotate credentials** - Change passwords regularly
5. **Use secrets management** - AWS Secrets Manager, Vault, etc.
6. **Restrict database access** - Firewall rules, security groups
7. **Use connection pooling** - Avoid connection exhaustion

## Quick Reference

```bash
# Minimal (local development)
postgresql:///mykobo?options=-csearch_path%3Ddapp

# Standard (with auth)
postgresql://user:pass@host:5432/mykobo?options=-csearch_path%3Ddapp

# Production (with SSL)
postgresql://user:pass@host:5432/mykobo?sslmode=require&options=-csearch_path%3Ddapp

# Docker Compose
postgresql://mykobo_user:changeme@postgres:5432/mykobo?options=-csearch_path%3Ddapp
```

## Summary

**Key Points:**
- ✅ Always include `?options=-csearch_path%3Ddapp`
- ✅ Use SSL in production (`sslmode=require`)
- ✅ URL-encode special characters (`=` becomes `%3D`)
- ✅ Test connection before deploying
- ✅ Never commit passwords to git

**Format:**
```
postgresql://user:pass@host:port/database?options=-csearch_path%3Ddapp
```
