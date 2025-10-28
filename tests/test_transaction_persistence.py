"""
Tests for transaction persistence functionality
"""
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from app.models import Transaction
from app.database import db


class TestTransactionModel:
    """Tests for the Transaction model"""

    def test_create_transaction_from_ledger_payload(self, app):
        """Test creating a Transaction from a ledger payload"""
        with app.app_context():
            # Sample ledger payload
            ledger_payload = {
                "meta_data": {
                    "source": "DAPP",
                    "instruction_type": "Transaction",
                    "created_at": "2025-10-24T10:00:00Z",
                    "token": "sample_token",
                    "idempotency_key": str(uuid.uuid4()),
                    "ip_address": "192.168.1.1",
                },
                "payload": {
                    "external_reference": str(uuid.uuid4()),
                    "source": "ANCHOR_SOLANA",
                    "reference": "TX123456",
                    "first_name": "John",
                    "last_name": "Doe",
                    "transaction_type": "deposit",
                    "status": "pending_payer",
                    "incoming_currency": "USD",
                    "outgoing_currency": "USDC",
                    "value": "100.50",
                    "fee": "2.50",
                    "payer": "user_123",
                    "payee": None,
                },
            }

            wallet_address = "ABC123XYZ789"

            # Create transaction from payload
            transaction = Transaction.from_ledger_payload(
                ledger_payload=ledger_payload,
                wallet_address=wallet_address
            )

            # Verify fields
            assert transaction.reference == "TX123456"
            assert transaction.external_reference == ledger_payload["payload"]["external_reference"]
            assert transaction.idempotency_key == ledger_payload["meta_data"]["idempotency_key"]
            assert transaction.transaction_type == "deposit"
            assert transaction.status == "pending_payer"
            assert transaction.incoming_currency == "USD"
            assert transaction.outgoing_currency == "USDC"
            assert transaction.value == Decimal("100.50")
            assert transaction.fee == Decimal("2.50")
            assert transaction.payer_id == "user_123"
            assert transaction.payee_id is None
            assert transaction.first_name == "John"
            assert transaction.last_name == "Doe"
            assert transaction.wallet_address == wallet_address
            assert transaction.source == "ANCHOR_SOLANA"
            assert transaction.instruction_type == "Transaction"
            assert transaction.ip_address == "192.168.1.1"
            assert transaction.message_id is None
            assert transaction.queue_sent_at is None

    def test_transaction_to_dict(self, app):
        """Test converting transaction to dictionary"""
        with app.app_context():
            transaction = Transaction(
                reference="TX123",
                external_reference="EXT123",
                idempotency_key="KEY123",
                transaction_type="withdrawal",
                status="pending_payee",
                incoming_currency="USDC",
                outgoing_currency="USD",
                value=Decimal("50.00"),
                fee=Decimal("1.50"),
                payer_id=None,
                payee_id="user_456",
                first_name="Jane",
                last_name="Smith",
                wallet_address="XYZ789",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                ip_address="10.0.0.1",
            )

            # Convert to dict
            tx_dict = transaction.to_dict()

            # Verify dict structure
            assert tx_dict['reference'] == "TX123"
            assert tx_dict['transaction_type'] == "withdrawal"
            assert tx_dict['value'] == "50.00"
            assert tx_dict['fee'] == "1.50"
            assert tx_dict['wallet_address'] == "XYZ789"
            assert 'created_at' in tx_dict
            assert 'updated_at' in tx_dict

    def test_transaction_repr(self, app):
        """Test transaction string representation"""
        with app.app_context():
            transaction = Transaction(
                reference="TX999",
                external_reference="EXT999",
                idempotency_key="KEY999",
                transaction_type="deposit",
                status="completed",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("75.00"),
                fee=Decimal("2.00"),
                wallet_address="WALLET123",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            repr_str = repr(transaction)
            assert "TX999" in repr_str
            assert "deposit" in repr_str
            assert "completed" in repr_str

    def test_transaction_persistence(self, app):
        """Test saving and retrieving transaction from database"""
        with app.app_context():
            # Create transaction
            transaction = Transaction(
                reference=f"TX{uuid.uuid4().hex[:8]}",
                external_reference=str(uuid.uuid4()),
                idempotency_key=str(uuid.uuid4()),
                transaction_type="deposit",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                payer_id="user_789",
                payee_id=None,
                first_name="Test",
                last_name="User",
                wallet_address="TESTWALLET",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                ip_address="127.0.0.1",
                message_id="MSG123",
            )

            # Save to database
            db.session.add(transaction)
            db.session.commit()

            # Verify it was saved
            assert transaction.id is not None

            # Retrieve from database
            retrieved = db.session.query(Transaction).filter_by(
                reference=transaction.reference
            ).first()

            # Verify retrieved transaction
            assert retrieved is not None
            assert retrieved.id == transaction.id
            assert retrieved.reference == transaction.reference
            assert retrieved.value == Decimal("100.00")
            assert retrieved.wallet_address == "TESTWALLET"

    def test_transaction_unique_constraints(self, app):
        """Test that unique constraints are enforced"""
        with app.app_context():
            reference = f"TX{uuid.uuid4().hex[:8]}"
            external_ref = str(uuid.uuid4())
            idempotency_key = str(uuid.uuid4())

            # Create first transaction
            transaction1 = Transaction(
                reference=reference,
                external_reference=external_ref,
                idempotency_key=idempotency_key,
                transaction_type="deposit",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="WALLET1",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            db.session.add(transaction1)
            db.session.commit()

            # Try to create duplicate with same reference
            transaction2 = Transaction(
                reference=reference,  # Duplicate reference
                external_reference=str(uuid.uuid4()),
                idempotency_key=str(uuid.uuid4()),
                transaction_type="deposit",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("50.00"),
                fee=Decimal("1.50"),
                wallet_address="WALLET2",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            db.session.add(transaction2)

            # Should raise integrity error
            with pytest.raises(Exception):  # Will be IntegrityError
                db.session.commit()

            db.session.rollback()

    def test_transaction_timestamps(self, app):
        """Test that timestamps are automatically set"""
        with app.app_context():
            transaction = Transaction(
                reference=f"TX{uuid.uuid4().hex[:8]}",
                external_reference=str(uuid.uuid4()),
                idempotency_key=str(uuid.uuid4()),
                transaction_type="deposit",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="WALLET123",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            # Timestamps should be None before saving
            assert transaction.id is None

            db.session.add(transaction)
            db.session.commit()

            # Timestamps should be set after saving
            assert transaction.created_at is not None
            assert transaction.updated_at is not None
            assert isinstance(transaction.created_at, datetime)
            assert isinstance(transaction.updated_at, datetime)
