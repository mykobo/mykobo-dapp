# Automatic Database Migrations

Your Docker deployment now includes **automatic database migrations** on startup!

## How It Works

When a container starts (web or worker), the `entrypoint.sh` script automatically:

1. Runs `python run_migrations.py`
2. Applies any pending migrations
3. Logs the result
4. Starts the service

```
Container Start
      ↓
Run Migrations
      ↓
   Success? → Start Service
      ↓
   Failure? → Log error + Continue (or Exit based on config)
```

## What This Means

### ✅ Benefits

- **Zero manual intervention** - Just deploy and go
- **Always up-to-date** - Database schema matches code
- **Safe deployments** - Migrations run before app starts
- **Rollback friendly** - Failed migrations logged clearly
- **Version controlled** - Migrations committed with code

### 🔧 Configuration

**Environment Variables:**

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUTO_MIGRATE` | `true` | Enable/disable auto-migrations |
| `AUTO_MIGRATE_FAIL_ON_ERROR` | `false` | Exit if migration fails |

**Example configurations:**

```bash
# Production (strict)
AUTO_MIGRATE=true
AUTO_MIGRATE_FAIL_ON_ERROR=true  # Don't start if migration fails

# Development (lenient)
AUTO_MIGRATE=true
AUTO_MIGRATE_FAIL_ON_ERROR=false  # Start even if migration fails

# Manual migration control
AUTO_MIGRATE=false  # Run migrations manually
```

## Workflow

### First Deployment

```bash
# 1. Build image
docker build -t mykobo-dapp:latest .

# 2. Start services (migrations run automatically)
docker-compose up -d

# 3. Check migration logs
docker-compose logs web | grep Migration
# Output: [Migration] ✓ Migrations completed successfully

# 4. If migrations folder doesn't exist:
docker-compose exec web python manage.py db init
docker-compose exec web python manage.py db migrate -m "Initial migration"

# 5. Restart to apply
docker-compose restart web worker
```

### After Code Changes

```bash
# 1. Make model changes in app/models.py

# 2. Create migration
docker-compose exec web python manage.py db migrate -m "Add user_email column"

# 3. Commit migration to git
git add migrations/versions/xxxx_add_user_email_column.py
git commit -m "Add user email column migration"

# 4. Deploy (migration runs automatically)
git push
# CI/CD builds and deploys
# On startup: [Migration] Running database migrations...
#             [Migration] ✓ Migrations completed successfully
```

### Troubleshooting Migrations

**View migration logs:**
```bash
docker-compose logs web | grep -A 10 Migration
```

**Check what will be applied:**
```bash
docker-compose exec web python manage.py db current
docker-compose exec web python manage.py db heads
```

**Force migration manually:**
```bash
# Disable auto-migration temporarily
docker-compose exec web sh -c "AUTO_MIGRATE=false python manage.py db upgrade"
```

**Rollback migration:**
```bash
docker-compose exec web python manage.py db downgrade
```

## Migration on Startup - Logs

### Successful Migration

```
Starting MYKOBO DAPP service: web
Environment: production
Running database migrations...
[Migration] Environment: production
[Migration] Initializing Flask app...
[Migration] Database URL: postgresql://mykobo_user@postgres/mykobo...
[Migration] Running database migrations...
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> abc123, Initial migration
[Migration] ✓ Migrations completed successfully
Starting web application...
```

### Failed Migration (Continue Mode)

```
Running database migrations...
[Migration] ✗ Migration failed: (psycopg2.OperationalError) connection refused
[Migration] Continuing despite migration failure (set AUTO_MIGRATE_FAIL_ON_ERROR=true to exit on error)
Starting web application...
```

### Failed Migration (Strict Mode)

```
Running database migrations...
[Migration] ✗ Migration failed: (psycopg2.OperationalError) connection refused
[Migration] Exiting due to migration failure (AUTO_MIGRATE_FAIL_ON_ERROR=true)
Migration failed with exit code: 1
Exiting due to migration failure
```

## Production Best Practices

### 1. Commit Migrations to Git

```bash
# Always commit migration files
git add migrations/versions/*.py
git commit -m "Add database migration"
```

### 2. Test Migrations Locally

```bash
# Test migration before deploying
docker-compose exec web python manage.py db upgrade
docker-compose exec web python manage.py db downgrade
docker-compose exec web python manage.py db upgrade
```

### 3. Use Strict Mode in Production

```bash
# .env.production
AUTO_MIGRATE_FAIL_ON_ERROR=true
```

This ensures containers don't start with outdated schema.

### 4. Backup Before Major Changes

```bash
# Backup before migration
docker-compose exec postgres pg_dump -U mykobo_user mykobo > backup-$(date +%Y%m%d).sql
```

### 5. Review Migrations

```bash
# Check what changed
cat migrations/versions/latest_migration.py

# Review before deploying
git diff migrations/
```

## Multi-Instance Deployments

### Kubernetes

When running multiple pods, only one should run migrations:

**Option 1: Init Container**
```yaml
initContainers:
- name: migrate
  image: mykobo-dapp:latest
  command: ["python", "run_migrations.py"]
  env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef:
        name: mykobo-secrets
        key: database-url
```

**Option 2: Job**
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: mykobo-migrate
spec:
  template:
    spec:
      containers:
      - name: migrate
        image: mykobo-dapp:latest
        command: ["python", "run_migrations.py"]
      restartPolicy: Never
```

### Docker Swarm

Migrations run on all instances - handled by database locking (safe).

### Multiple docker-compose Instances

First instance migrates, others skip (migrations are idempotent).

## Disabling Auto-Migration

For manual control:

```bash
# In .env.docker
AUTO_MIGRATE=false

# Run migrations manually
docker-compose exec web python manage.py db upgrade
```

Use cases:
- Testing migration in staging first
- Complex multi-step deployments
- Blue-green deployments

## Migration Files

**Location:** `migrations/versions/`

**Example:**
```python
# migrations/versions/abc123_initial_migration.py
def upgrade():
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(255), nullable=False),
        # ...
        schema='dapp'
    )

def downgrade():
    op.drop_table('transactions', schema='dapp')
```

## Summary

- ✅ **Automatic** - Migrations run on container startup
- ✅ **Safe** - Failed migrations logged and handled
- ✅ **Configurable** - Control via environment variables
- ✅ **Production-ready** - Tested and documented
- ✅ **Version-controlled** - Migrations committed with code

**No more forgetting to run migrations!** 🎉

Your database schema stays in sync with your code automatically.
