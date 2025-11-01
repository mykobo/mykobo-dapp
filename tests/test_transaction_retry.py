"""
Tests for transaction retry functionality
"""
import uuid
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, patch
import pytest

from app.transaction_retry import (
    get_unsent_transactions,
    get_failed_transactions_by_status,
    retry_transaction,
    retry_unsent_transactions,
    get_transaction_stats
)
from app.models import Transaction
from app.database import db


class TestTransactionRetry:
    """Tests for transaction retry functionality"""

    @pytest.fixture
    def mock_identity_service(self):
        """Create a mock identity service client"""
        mock = Mock()
        mock_token = Mock()
        mock_token.token = "test-retry-token-abc123"
        mock.acquire_token = Mock(return_value=mock_token)
        return mock

    @pytest.fixture
    def mock_message_bus(self):
        """Create a mock message bus"""
        mock = Mock()
        mock.send_message = Mock(return_value={"MessageId": "test-retry-message-id-456"})
        return mock

    def test_get_unsent_transactions(self, app):
        """Test retrieving unsent transactions"""
        with app.app_context():
            # Create transactions with and without message_id
            sent_tx = Transaction(
                id=str(uuid.uuid4()),
                reference="SENT001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="SentWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id="already-sent-123"
            )

            unsent_tx1 = Transaction(
                id=str(uuid.uuid4()),
                reference="UNSENT001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("50.00"),
                fee=Decimal("1.50"),
                wallet_address="UnsentWallet1",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )

            unsent_tx2 = Transaction(
                id=str(uuid.uuid4()),
                reference="UNSENT002",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="DEPOSIT",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("75.00"),
                fee=Decimal("2.00"),
                wallet_address="UnsentWallet2",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )

            db.session.add_all([sent_tx, unsent_tx1, unsent_tx2])
            db.session.commit()

            # Get unsent transactions
            unsent = get_unsent_transactions(limit=100)

            assert len(unsent) == 2
            assert all(tx.message_id is None for tx in unsent)
            references = [tx.reference for tx in unsent]
            assert "UNSENT001" in references
            assert "UNSENT002" in references
            assert "SENT001" not in references

    def test_get_failed_transactions_by_status(self, app):
        """Test retrieving failed transactions by status"""
        with app.app_context():
            # Create transactions with different statuses
            tx1 = Transaction(
                id=str(uuid.uuid4()),
                reference="FAILED001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="failed",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="FailedWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )

            tx2 = Transaction(
                id=str(uuid.uuid4()),
                reference="PENDING001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("50.00"),
                fee=Decimal("1.50"),
                wallet_address="PendingWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )

            db.session.add_all([tx1, tx2])
            db.session.commit()

            # Get failed transactions
            failed = get_failed_transactions_by_status("failed", limit=100)

            assert len(failed) == 1
            assert failed[0].reference == "FAILED001"
            assert failed[0].status == "failed"
            assert failed[0].message_id is None

    def test_retry_transaction_success(self, app, mock_identity_service, mock_message_bus):
        """Test successful transaction retry"""
        with app.app_context():
            # Configure mocks
            app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
            app.config["MESSAGE_BUS"] = mock_message_bus
            app.config["TRANSACTION_QUEUE_NAME"] = "test-queue"

            # Create unsent transaction
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="RETRY001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="RetryWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None,
                ip_address="192.168.1.1",
                first_name="John",
                last_name="Doe",
                payer_id="payer123",
                payee_id="payee456"
            )
            db.session.add(transaction)
            db.session.commit()

            # Retry the transaction
            result = retry_transaction(transaction)

            print(result)
            # Verify success
            assert result['success'] is True
            assert result['message_id'] == "test-retry-message-id-456"
            assert result['error'] is None

            # Verify token was acquired
            mock_identity_service.acquire_token.assert_called_once()

            # Verify message was sent
            mock_message_bus.send_message.assert_called_once()

            # Verify message content
            call_args = mock_message_bus.send_message.call_args
            message = call_args[0][0].to_dict()
            queue_name = call_args[0][1]
            source = call_args[0][2]

            assert queue_name == "test-queue"
            assert source == "DAPP.transaction_retry"
            assert message["meta_data"]["token"] == "test-retry-token-abc123"
            assert message["meta_data"]["source"] == "DAPP"
            assert message["payload"]["reference"] == "RETRY001"
            assert message["payload"]["external_reference"] == transaction.id

            # Verify transaction was updated
            db.session.refresh(transaction)
            assert transaction.message_id == "test-retry-message-id-456"
            assert transaction.queue_sent_at is not None

    def test_retry_transaction_without_identity_service(self, app, mock_message_bus):
        """Test retry fails when identity service is not configured"""
        with app.app_context():
            # Don't configure identity service (set to None explicitly)
            app.config["IDENTITY_SERVICE_CLIENT"] = None
            app.config["MESSAGE_BUS"] = mock_message_bus
            app.config["TRANSACTION_QUEUE_NAME"] = "test-queue"

            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="NOIDENTITY001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="NoIdentityWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )
            db.session.add(transaction)
            db.session.commit()

            # Retry should fail
            result = retry_transaction(transaction)

            assert result['success'] is False
            assert result['message_id'] is None
            assert "Identity service not configured" in result['error']

            # Verify message was NOT sent
            mock_message_bus.send_message.assert_not_called()

            # Verify transaction was NOT updated
            db.session.refresh(transaction)
            assert transaction.message_id is None

    def test_retry_transaction_token_acquisition_failure(self, app, mock_identity_service, mock_message_bus):
        """Test retry fails when token acquisition fails"""
        with app.app_context():
            # Make token acquisition fail
            mock_identity_service.acquire_token.side_effect = Exception("Token service down")
            app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
            app.config["MESSAGE_BUS"] = mock_message_bus
            app.config["TRANSACTION_QUEUE_NAME"] = "test-queue"

            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="TOKENFAIL001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="TokenFailWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )
            db.session.add(transaction)
            db.session.commit()

            # Retry should fail
            result = retry_transaction(transaction)

            assert result['success'] is False
            assert result['message_id'] is None
            assert "Failed to acquire service token" in result['error']

            # Verify message was NOT sent
            mock_message_bus.send_message.assert_not_called()

    def test_retry_unsent_transactions(self, app, mock_identity_service, mock_message_bus):
        """Test retrying multiple unsent transactions"""
        with app.app_context():
            app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
            app.config["MESSAGE_BUS"] = mock_message_bus
            app.config["TRANSACTION_QUEUE_NAME"] = "test-queue"

            # Create multiple unsent transactions
            for i in range(3):
                tx = Transaction(
                    id=str(uuid.uuid4()),
                    reference=f"BATCH{i:03d}",
                    idempotency_key=str(uuid.uuid4()),
                    transaction_type="WITHDRAW",
                    first_name="John",
                    last_name="Smith",
                    status="PENDING_PAYEE",
                    incoming_currency="EUR",
                    outgoing_currency="EURC",
                    value=Decimal("100.00"),
                    fee=Decimal("2.50"),
                    wallet_address=f"BatchWallet{i}",
                    source="ANCHOR_SOLANA",
                    instruction_type="Transaction",
                    payee_id=str(uuid.uuid4()),
                    message_id=None
                )
                db.session.add(tx)
            db.session.commit()

            # Retry all unsent
            results = retry_unsent_transactions(limit=100)
            print(results)

            assert results['total'] == 3
            assert results['succeeded'] == 3
            assert results['failed'] == 0
            assert len(results['results']) == 3

            # Verify all have message_id now
            for result in results['results']:
                assert result['success'] is True
                assert result['message_id'] is not None

    def test_get_transaction_stats(self, app):
        """Test getting transaction statistics"""
        with app.app_context():
            # Create transactions with various statuses
            tx1 = Transaction(
                id=str(uuid.uuid4()),
                reference="STAT001",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="pending_payee",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="StatWallet1",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id="sent-123"
            )

            tx2 = Transaction(
                id=str(uuid.uuid4()),
                reference="STAT002",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="completed",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("50.00"),
                fee=Decimal("1.50"),
                wallet_address="StatWallet2",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )

            tx3 = Transaction(
                id=str(uuid.uuid4()),
                reference="STAT003",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="DEPOSIT",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("75.00"),
                fee=Decimal("2.00"),
                wallet_address="StatWallet3",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
                message_id=None
            )

            db.session.add_all([tx1, tx2, tx3])
            db.session.commit()

            # Get stats
            stats = get_transaction_stats()

            assert stats['total'] == 3
            assert stats['sent'] == 1
            assert stats['unsent'] == 2
            assert 'by_status' in stats
            assert stats['by_status']['pending_payee'] == 1
            assert stats['by_status']['completed'] == 1
            assert stats['by_status']['pending_payer'] == 1
