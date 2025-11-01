# Transaction Identifiers

## Overview

The Transaction model uses multiple identifiers for different purposes. This document explains each identifier and how they're used.

## Identifier Fields

### 1. `id` (UUID Primary Key)
- **Type**: `String(36)` - UUID v4
- **Example**: `"550e8400-e29b-41d4-a716-446655440000"`
- **Purpose**: Database primary key
- **Generated**: Automatically by SQLAlchemy when record is created
- **Usage**:
  - Internal database operations
  - Used as `external_reference` in ledger payload
  - Links records across systems

```python
id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
```

### 2. `reference` (Business Reference)
- **Type**: `String(255)`, unique, indexed
- **Example**: `"MYK1747799079"`
- **Purpose**: Business-level transaction identifier
- **Generated**: By application using `generate_reference()` function
- **Usage**:
  - Display to users
  - Lookup transactions in inbox processor
  - Track transactions across services
  - Customer support reference

```python
reference = db.Column(db.String(255), unique=True, nullable=False, index=True)
```

### 3. `idempotency_key` (Deduplication)
- **Type**: `String(255)`, unique, indexed
- **Example**: `"750d17bb-5dc1-4649-ac9a-709a6a3a36b1"`
- **Purpose**: Prevent duplicate transaction processing
- **Generated**: UUID v4 at transaction creation
- **Usage**:
  - Ensures idempotent operations
  - Prevents race conditions
  - Safe retries

```python
idempotency_key = db.Column(db.String(255), unique=True, nullable=False, index=True)
```

## Identifier Flow

### Transaction Creation Flow

```
1. Generate reference
   └─> "MYK1747799079"

2. Generate UUID for external_reference
   └─> "550e8400-e29b-41d4-a716-446655440000"

3. Create payload with external_reference
   └─> Payload ready with all identifiers

4. Create transaction record from payload
   └─> id = external_reference from payload
   └─> "550e8400-e29b-41d4-a716-446655440000"

5. Save to database
   └─> db.session.commit()
   └─> transaction.id equals external_reference

6. Send to SQS queue
   └─> Payload includes both reference and external_reference
```

### Code Example

```python
# Step 1: Create payload with external_reference UUID
ledger_payload = {
    "meta_data": {
        "idempotency_key": str(uuid.uuid4()),
        # ... other metadata
    },
    "payload": {
        "external_reference": str(uuid.uuid4()),  # This becomes transaction.id
        "reference": "MYK1747799079",
        # ... other fields
    }
}

# Step 2: Create transaction from payload
# The external_reference from payload is used as the transaction ID
transaction_record = TransactionModel.from_ledger_payload(
    ledger_payload=ledger_payload,
    wallet_address=wallet_address
)
# transaction_record.id = ledger_payload["payload"]["external_reference"]

# Step 3: Save to database with pre-set ID
db.session.add(transaction_record)
db.session.commit()

# Step 4: Send to queue (external_reference already set correctly)
queue_response = message_bus.send_message(ledger_payload, queue_name, source)
```

## Ledger Payload Structure

### Outgoing to Ledger

```json
{
  "meta_data": {
    "source": "DAPP",
    "instruction_type": "Transaction",
    "idempotency_key": "750d17bb-5dc1-4649-ac9a-709a6a3a36b1",
    "created_at": "2024-08-10T16:00:50Z"
  },
  "payload": {
    "external_reference": "550e8400-e29b-41d4-a716-446655440000",  // ← transaction.id
    "reference": "MYK1747799079",                                   // ← transaction.reference
    "transaction_type": "WITHDRAWAL",
    "status": "pending_payee",
    "value": "100.00",
    "fee": "2.50",
    // ... other fields
  }
}
```

### Incoming from Ledger

```json
{
  "meta_data": {
    "created_at": "2024-08-10T16:00:50Z",
    "event": "NEW_CHAIN_PAYMENT",
    "source": "MYKOBO_LEDGER",
    "idempotency_key": "750d17bb-5dc1-4649-ac9a-709a6a3a36b1"
  },
  "payload": {
    "reference": "MYK1747799079",     // ← Used to lookup transaction
    "status": "APPROVED",
    "transaction_id": "ledger-tx-id"
  }
}
```

## Database vs Payload

### Not Stored in Database
- `external_reference` - Only exists in the ledger payload
- Generated from `transaction.id` when sending to queue

### Stored in Database
- `id` - UUID primary key
- `reference` - Business reference
- `idempotency_key` - Deduplication key

### Why This Design?

1. **Simplicity**: UUID is generated once and used everywhere
2. **Consistency**: `transaction.id` always equals `external_reference` in payload
3. **No Updates Needed**: No need to update payload after database save
4. **Predictability**: Know the transaction ID before saving to database
5. **Compatibility**: Matches ledger's expected payload structure

## Usage Examples

### Creating a Transaction

```python
from app.models import Transaction
from app.util import generate_reference
import uuid

# Generate reference
tx_ref = generate_reference()  # "MYK1747799079"

# Create transaction
tx = Transaction(
    reference=tx_ref,
    idempotency_key=str(uuid.uuid4()),
    transaction_type="WITHDRAWAL",
    status="pending_payee",
    incoming_currency="USD",
    outgoing_currency="EURC",
    value=100.00,
    fee=2.50,
    wallet_address="SolanaWalletAddress",
    source="ANCHOR_SOLANA"
)

# Save (UUID generated automatically)
db.session.add(tx)
db.session.commit()

print(f"ID: {tx.id}")                    # 550e8400-e29b-41d4-a716-446655440000
print(f"Reference: {tx.reference}")       # MYK1747799079
print(f"Idempotency: {tx.idempotency_key}")  # 750d17bb-5dc1-4649-ac9a-709a6a3a36b1
```

### Looking Up a Transaction

```python
# By reference (from message payload)
tx = Transaction.query.filter_by(reference="MYK1747799079").first()

# By ID (from external_reference in response)
tx = Transaction.query.get("550e8400-e29b-41d4-a716-446655440000")

# By idempotency key (prevent duplicates)
tx = Transaction.query.filter_by(idempotency_key="750d17bb...").first()
```

### Retry Logic

When retrying a transaction, use the database record to reconstruct the payload:

```python
def retry_transaction(transaction: Transaction):
    ledger_payload = {
        "meta_data": {
            "idempotency_key": transaction.idempotency_key,
            # ... other metadata
        },
        "payload": {
            "external_reference": transaction.id,  # ← Use transaction.id
            "reference": transaction.reference,
            # ... reconstruct from transaction record
        }
    }

    message_bus.send_message(ledger_payload, queue_name, source)
```

## Inbox Processor Usage

The inbox processor looks up transactions by `reference`:

```python
# Message from ledger contains reference
payload = message_body.get('payload', {})
reference = payload.get('reference')  # "MYK1747799079"

# Look up transaction in database
transaction = Transaction.query.filter_by(reference=reference).first()

# Process using transaction details
if transaction:
    amount = transaction.value - transaction.fee
    create_solana_transaction(transaction.wallet_address, amount)
```

## Summary

| Field | Stored in DB | Used in Payload | Purpose |
|-------|--------------|-----------------|---------|
| `id` | ✅ Yes (PK) | ✅ Yes (as external_reference) | Database primary key & external identifier |
| `reference` | ✅ Yes (unique) | ✅ Yes | Business transaction reference |
| `idempotency_key` | ✅ Yes (unique) | ✅ Yes (in meta_data) | Prevent duplicate processing |
| `external_reference` | ❌ No | ✅ Yes (= transaction.id) | Links to external systems |

## Benefits

1. **Single Source of Truth**: `id` serves dual purpose (PK + external reference)
2. **No Redundancy**: Don't store the same value twice
3. **Flexibility**: Can modify external reference format without DB changes
4. **Clean Schema**: Fewer columns to maintain
5. **Clear Intent**: Obvious which field serves which purpose

## Migration Notes

This design requires the UUID migration (`9dcea3da199d`) to be applied first, which changes `id` from integer to UUID.

**Migration order**:
1. `59bdae19f453` - Add inbox table
2. `9dcea3da199d` - Change id to UUID
3. No migration needed for external_reference (not stored in DB)

## Related Files

- `app/models.py:29` - Transaction model with UUID id
- `app/mod_solana/transaction.py:145` - Sets external_reference = transaction.id
- `app/transaction_retry.py:79` - Uses transaction.id as external_reference
- `app/transaction_processor.py:157` - Looks up by reference
