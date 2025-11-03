# Test Documentation - Inbox Pattern & Transaction Processing

## Overview

Comprehensive test suite for the inbox pattern implementation and transaction processing system with Solana blockchain integration.

## Test Files

### 1. `tests/test_transaction_persistence.py`
**Purpose**: Tests for the Transaction model with UUID primary key implementation

**Test Coverage**:
- ✅ Creating transactions from ledger payloads
- ✅ UUID as primary key (external_reference becomes id)
- ✅ Transaction persistence and retrieval
- ✅ Unique constraints on reference and idempotency_key
- ✅ Timestamp management
- ✅ Dictionary conversion (to_dict)
- ✅ String representation

**Key Test Cases**:
```python
test_create_transaction_from_ledger_payload()  # Verifies external_reference -> id mapping
test_transaction_uuid_as_id()                   # Tests UUID primary key strategy
test_transaction_persistence()                  # Database operations
test_transaction_unique_constraints()           # Idempotency enforcement
```

### 2. `tests/test_inbox_model.py`
**Purpose**: Tests for the Inbox model and inbox pattern functionality

**Test Coverage**:
- ✅ Creating inbox messages from SQS messages
- ✅ Idempotency (duplicate message_id rejection)
- ✅ Status transitions (pending → processing → completed/failed)
- ✅ Retry count management
- ✅ Error tracking
- ✅ Transaction reference indexing
- ✅ Timestamp management

**Key Test Cases**:
```python
test_create_inbox_from_sqs_message()     # Message ingestion
test_inbox_idempotency()                 # Duplicate prevention
test_mark_processing()                   # Status: pending → processing
test_mark_completed()                    # Status: processing → completed
test_mark_failed()                       # Status: processing → failed, increment retry
test_reset_for_retry()                   # Reset to pending for retry
test_query_pending_messages()            # Efficient inbox polling
```

### 3. `tests/test_inbox_consumer.py`
**Purpose**: Tests for the InboxConsumer service (SQS → Database)

**Test Coverage**:
- ✅ SQS message consumption
- ✅ Writing messages to inbox table
- ✅ Message idempotency
- ✅ SQS message deletion after storage
- ✅ Message ID extraction (from idempotency_key)
- ✅ Error handling (don't delete on failure)
- ✅ Batch message processing
- ✅ Reference extraction and indexing

**Key Test Cases**:
```python
test_store_in_inbox_new_message()              # New message storage
test_store_in_inbox_duplicate_message()        # Duplicate rejection
test_extract_message_id_from_idempotency_key() # ID extraction
test_consume_messages_with_message()           # Full consumption flow
test_consume_messages_multiple_messages()      # Batch processing
test_consume_messages_error_handling()         # Don't delete on error
```

**Mock Usage**:
- Mock SQS client for testing without AWS dependencies
- Verifies correct SQS API calls (receive_message, delete_message)

### 4. `tests/test_transaction_processor.py`
**Purpose**: Tests for the TransactionProcessor service (Database → Solana)

**Test Coverage**:
- ✅ Inbox polling for pending messages
- ✅ Transaction lookup by reference
- ✅ Status validation (APPROVED only)
- ✅ Transaction type filtering (WITHDRAWAL only)
- ✅ Net amount calculation (value - fee)
- ✅ Token mint address resolution (EURC/USDC)
- ✅ Solana transaction creation
- ✅ Status updates (transaction and inbox)
- ✅ Error handling and retry

**Key Test Cases**:
```python
test_should_process_transaction_approved_withdrawal()  # Process APPROVED WITHDRAWAL
test_should_not_process_deposit()                      # Skip DEPOSITs
test_calculate_net_amount()                            # value - fee calculation
test_get_token_mint_eurc()                             # Token mint resolution
test_process_inbox_message_success()                   # Successful processing
test_process_inbox_message_batch()                     # Batch processing
test_process_message_with_solana_error()               # Error handling
test_lookup_transaction_by_reference()                 # Transaction lookup
```

**Mock Usage**:
- Mock `_create_and_send_solana_transaction` to avoid actual blockchain calls
- Verifies correct Solana parameters (recipient, amount, currency)

### 5. `tests/test_inbox_integration.py`
**Purpose**: End-to-end integration tests for complete inbox pattern flow

**Test Coverage**:
- ✅ Complete flow: SQS → Inbox → Processing → Solana
- ✅ Idempotency across the entire pipeline
- ✅ Multiple transaction processing
- ✅ Fee calculation in complete flow
- ✅ Error scenarios (transaction not found, Solana failures)
- ✅ Transaction type filtering (deposits vs withdrawals)
- ✅ Status updates across all components

**Key Test Cases**:
```python
test_complete_inbox_flow()                    # Full end-to-end flow
test_idempotency_in_inbox_flow()              # No duplicate processing
test_multiple_transactions_flow()             # Batch end-to-end
test_failed_transaction_not_completed()       # Error handling
test_non_withdrawal_not_processed()           # Type filtering
test_transaction_not_found_handling()         # Missing transaction error
test_fee_calculation_in_flow()                # Fee deduction verification
```

**Integration Points**:
1. InboxConsumer receives from SQS → stores in inbox
2. TransactionProcessor polls inbox → processes transaction
3. Solana transaction created with net amount (value - fee)
4. Both inbox and transaction status updated to completed

## Running Tests

### Run All Tests
```bash
ENV=development pytest tests/
```

### Run Specific Test File
```bash
ENV=development pytest tests/test_inbox_model.py
ENV=development pytest tests/test_inbox_consumer.py
ENV=development pytest tests/test_transaction_processor.py
ENV=development pytest tests/test_inbox_integration.py
```

### Run Specific Test
```bash
ENV=development pytest tests/test_inbox_model.py::TestInboxModel::test_inbox_idempotency
```

### Run with Coverage
```bash
ENV=development pytest --cov=app --cov-report=html tests/
```

### Run with Verbose Output
```bash
ENV=development pytest -v tests/
```

## Test Configuration

### Fixtures (from `tests/conftest.py`)

**`app`**: Flask application with test configuration
- Uses SQLite in-memory database
- Schema translation for SQLite (dapp → None)
- Automatic database creation and teardown

**`client`**: Flask test client for HTTP requests

**`auth_headers`**: Valid JWT authentication headers

**`mock_sqs_client`**: Mock SQS client (test_inbox_consumer.py)
- Avoids real AWS dependencies
- Simulates receive_message and delete_message

**`consumer`**: InboxConsumer instance with mocked dependencies

**`processor`**: TransactionProcessor instance with test configuration

## Test Data Patterns

### Transaction Creation
```python
transaction = Transaction(
    id=str(uuid.uuid4()),              # UUID primary key
    reference="MYK1234567890",          # Business reference
    idempotency_key=str(uuid.uuid4()),  # Deduplication key
    transaction_type="WITHDRAWAL",      # WITHDRAWAL or DEPOSIT
    status="pending_payee",             # Initial status
    incoming_currency="EUR",
    outgoing_currency="EURC",
    value=Decimal("100.00"),
    fee=Decimal("2.50"),
    wallet_address="SolanaWallet123",
    source="ANCHOR_SOLANA",
    instruction_type="Transaction",
)
```

### Inbox Message Creation
```python
inbox_message = Inbox(
    message_id=str(uuid.uuid4()),       # From idempotency_key
    message_body={
        "meta_data": {
            "idempotency_key": "...",
            "event": "NEW_CHAIN_PAYMENT",
            "source": "MYKOBO_LEDGER"
        },
        "payload": {
            "reference": "MYK1234567890",
            "status": "APPROVED",
            "transaction_id": "ledger-tx-123"
        }
    },
    transaction_reference="MYK1234567890",
    status="pending"
)
```

### Ledger Payload
```python
ledger_payload = {
    "meta_data": {
        "idempotency_key": str(uuid.uuid4()),
        "instruction_type": "Transaction",
        "source": "DAPP",
    },
    "payload": {
        "external_reference": str(uuid.uuid4()),  # Becomes transaction.id
        "reference": "MYK1234567890",
        "transaction_type": "WITHDRAWAL",
        "status": "pending_payee",
        "value": "100.00",
        "fee": "2.50",
        # ... other fields
    }
}
```

## Mock Strategies

### SQS Client Mock
```python
mock_sqs_client = Mock()
mock_sqs_client.receive_message.return_value = {
    "receipt-handle": message_body
}
mock_sqs_client.delete_message.return_value = True
```

### Solana Transaction Mock
```python
with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
    mock_solana.return_value = {
        "status": "success",
        "transaction_signature": "mock_signature_123"
    }

    # Run test...

    # Verify call
    mock_solana.assert_called_once()
    call_args = mock_solana.call_args[1]
    assert call_args['amount'] == 97.50  # value - fee
```

## Key Assertions

### Transaction ID Strategy
```python
# external_reference from payload becomes transaction.id
external_ref = str(uuid.uuid4())
ledger_payload = {"payload": {"external_reference": external_ref, ...}}
transaction = Transaction.from_ledger_payload(ledger_payload, wallet)

assert transaction.id == external_ref
```

### Inbox Idempotency
```python
# First message stored
consumer._store_in_inbox(message_id, body, handle)
count_1 = Inbox.query.count()

# Duplicate message rejected
consumer._store_in_inbox(message_id, body, handle)
count_2 = Inbox.query.count()

assert count_1 == count_2  # No duplicate
```

### Fee Calculation
```python
transaction.value = Decimal("100.00")
transaction.fee = Decimal("2.50")

net_amount = processor._calculate_net_amount(transaction)
assert net_amount == Decimal("97.50")  # value - fee
```

### Status Transitions
```python
inbox_message.status == "pending"
inbox_message.mark_processing()
assert inbox_message.status == "processing"

inbox_message.mark_completed()
assert inbox_message.status == "completed"
assert inbox_message.processed_at is not None
```

## Coverage Goals

### Target Coverage: >90%

**Transaction Model**: 100% coverage
- All fields tested
- All methods tested
- UUID strategy verified

**Inbox Model**: 100% coverage
- Status transitions
- Helper methods
- Queries

**InboxConsumer**: >95% coverage
- Main flow tested
- Error paths tested
- Edge cases covered

**TransactionProcessor**: >95% coverage
- Processing logic tested
- Solana integration mocked
- Error handling verified

**Integration**: >90% coverage
- End-to-end flows
- Multiple scenarios
- Error recovery

## Continuous Integration

### Pre-commit Hook
```bash
#!/bin/bash
ENV=development pytest tests/ || exit 1
```

### CI Pipeline
```yaml
- name: Run Tests
  run: |
    ENV=development pytest tests/ \
      --cov=app \
      --cov-report=xml \
      --cov-fail-under=90
```

## Test Maintenance

### Adding New Tests

1. **For New Models**: Add to appropriate test file or create new one
2. **For New Services**: Create dedicated test file
3. **For Integration**: Add to `test_inbox_integration.py`

### Updating Tests

When modifying code:
1. Update affected test cases
2. Ensure all assertions still valid
3. Add new tests for new functionality
4. Verify coverage remains >90%

### Test Review Checklist

- ✅ All public methods tested
- ✅ Error paths tested
- ✅ Edge cases covered
- ✅ Mocks properly configured
- ✅ Assertions are clear and specific
- ✅ Test names are descriptive
- ✅ Tests are independent
- ✅ Tests clean up after themselves

## Troubleshooting

### SQLite Schema Issues
If tests fail with schema errors, verify `conftest.py` has proper schema translation:
```python
connection.execution_options(schema_translate_map={"dapp": None})
```

### Mock Not Called
Ensure you're patching the correct path:
```python
# Correct: patch where it's used
with patch.object(processor, '_create_and_send_solana_transaction'):

# Wrong: patching the definition
with patch('app.mod_solana.transaction.create_transaction'):
```

### Database State Pollution
Tests should use `db.session.rollback()` in error cases:
```python
try:
    db.session.add(duplicate)
    db.session.commit()
except:
    db.session.rollback()
```

## Documentation References

- [FINAL_IMPLEMENTATION_SUMMARY.md](FINAL_IMPLEMENTATION_SUMMARY.md) - Complete system documentation
- [TRANSACTION_IDENTIFIERS.md](TRANSACTION_IDENTIFIERS.md) - ID strategy
- [INBOX_PATTERN_SUMMARY.md](INBOX_PATTERN_SUMMARY.md) - Inbox pattern details
- [TRANSACTION_PROCESSOR.md](TRANSACTION_PROCESSOR.md) - Processor documentation

## Success Criteria

✅ All tests pass
✅ Coverage >90%
✅ No flaky tests
✅ Fast execution (<30s for full suite)
✅ Clear test names and assertions
✅ Comprehensive error coverage
✅ Integration tests validate end-to-end flow

---

**Test Suite Complete and Ready for Production! ✅**
