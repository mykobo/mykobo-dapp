"""
Integration tests for the complete inbox pattern flow
"""
import uuid
from decimal import Decimal
from unittest.mock import Mock, patch
import pytest
from app.inbox_consumer import InboxConsumer
from app.transaction_processor import TransactionProcessor
from app.models import Transaction, Inbox
from app.database import db


class TestInboxIntegration:
    """Integration tests for inbox pattern end-to-end flow"""

    @pytest.fixture
    def mock_identity_service(self):
        """Create a mock identity service client"""
        mock = Mock()
        mock_token = Mock()
        mock_token.token = "test-integration-token-abc123"
        mock.acquire_token = Mock(return_value=mock_token)

        # Mock check_scope to return authorized response
        mock_check_scope_response = Mock()
        mock_check_scope_response.ok = True
        mock_check_scope_response.json = Mock(return_value={
            "authorised": True,
            "message": "Authorized"
        })
        mock.check_scope = Mock(return_value=mock_check_scope_response)

        return mock

    @pytest.fixture
    def mock_message_bus(self):
        """Create a mock message bus for status updates"""
        mock = Mock()
        mock.send_message = Mock(return_value={"MessageId": "test-msg-id-integration"})
        return mock

    @pytest.fixture
    def mock_sqs_client(self):
        """Create a mock SQS client"""
        mock = Mock()
        mock.receive_message = Mock(return_value={})
        mock.delete_message = Mock(return_value=True)
        return mock

    @pytest.fixture
    def consumer(self, app, mock_sqs_client, mock_identity_service):
        """Create an InboxConsumer instance"""
        app.config["MESSAGE_BUS"] = mock_sqs_client
        app.config["TRANSACTION_QUEUE_NAME"] = "test-queue"
        app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
        return InboxConsumer(app)

    @pytest.fixture
    def processor(self, app, mock_identity_service, mock_message_bus):
        """Create a TransactionProcessor instance"""
        app.config["SOLANA_RPC_URL"] = "https://api.devnet.solana.com"
        app.config["SOLANA_DISTRIBUTION_PRIVATE_KEY"] = "test-key"
        app.config["EURC_TOKEN_MINT"] = "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"
        app.config["USDC_TOKEN_MINT"] = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
        app.config["MESSAGE_BUS"] = mock_message_bus
        app.config["TRANSACTION_STATUS_UPDATE_QUEUE_NAME"] = "test-status-update-queue"
        return TransactionProcessor(app)

    def test_complete_inbox_flow(self, app, consumer, processor, mock_sqs_client, mock_identity_service):
        """Test complete flow: SQS -> Inbox -> Transaction Processing"""
        with app.app_context():
            # Step 1: Create a transaction in database (simulates transaction creation)
            tx_id = str(uuid.uuid4())
            reference = "MYK1234567890"
            transaction = Transaction(
                id=tx_id,
                reference=reference,
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="PENDING_ANCHOR",  # Must be PENDING_ANCHOR to be processed
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="SolanaWallet123",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Step 2: Simulate SQS message from ledger
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "event": "NEW_CHAIN_PAYMENT",
                    "source": "MYKOBO_LEDGER",
                    "token": "sender-token-123"
                },
                "payload": {
                    "reference": reference,
                    "status": "APPROVED",
                    "transaction_id": "ledger-tx-123"
                }
            }
            receipt_handle = "receipt-integration-test"

            # Configure mock SQS to return the message
            mock_sqs_client.receive_message.return_value = {
                receipt_handle: message_body
            }

            # Step 3: Consumer polls SQS and stores in inbox
            consumer._consume_messages()

            # Verify message stored in inbox
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message is not None
            assert inbox_message.status == "pending"
            assert inbox_message.transaction_reference == reference

            # Verify identity service was called for authentication
            mock_identity_service.acquire_token.assert_called()
            mock_identity_service.check_scope.assert_called_once()

            # Verify check_scope was called with correct parameters
            check_scope_call = mock_identity_service.check_scope.call_args
            assert check_scope_call[0][1] == "sender-token-123"  # Token from message meta_data
            assert check_scope_call[0][2] == "transaction:admin"  # Scope being checked

            # Verify message deleted from SQS
            mock_sqs_client.delete_message.assert_called_once()

            # Step 4: Processor polls inbox and processes transaction
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "mock_signature_abc123"
                }

                processor._process_messages()

                # Verify Solana transaction created
                mock_solana.assert_called_once()
                call_args = mock_solana.call_args[1]
                assert call_args['recipient_address'] == "SolanaWallet123"
                assert call_args['amount'] == float(Decimal("97.50"))  # 100 - 2.5
                assert call_args['currency'] == "EURC"

            # Step 5: Verify final state
            # Inbox message should be completed
            db.session.refresh(inbox_message)
            assert inbox_message.status == "completed"
            assert inbox_message.processed_at is not None

            # Transaction should be completed
            db.session.refresh(transaction)
            assert transaction.status == "completed"

    def test_idempotency_in_inbox_flow(self, app, consumer, processor, mock_sqs_client):
        """Test that duplicate messages are handled idempotently"""
        with app.app_context():
            # Create transaction
            tx_id = str(uuid.uuid4())
            reference = "MYK5555555555"
            transaction = Transaction(
                id=tx_id,
                reference=reference,
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="PENDING_ANCHOR",  # Must be PENDING_ANCHOR to be processed
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("50.00"),
                fee=Decimal("1.00"),
                wallet_address="TestWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Same message delivered twice
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": "sender-token-456"
                },
                "payload": {"reference": reference, "status": "APPROVED"}
            }

            # First delivery
            mock_sqs_client.receive_message.return_value = {
                "receipt-1": message_body
            }
            consumer._consume_messages()

            inbox_count_1 = Inbox.query.count()

            # Second delivery (duplicate)
            mock_sqs_client.receive_message.return_value = {
                "receipt-2": message_body
            }
            consumer._consume_messages()

            inbox_count_2 = Inbox.query.count()

            # Verify only one inbox entry created
            assert inbox_count_1 == 1
            assert inbox_count_2 == 1

    def test_multiple_transactions_flow(self, app, consumer, processor, mock_sqs_client):
        """Test processing multiple transactions through the inbox"""
        with app.app_context():
            # Create multiple transactions
            transactions = []
            message_bodies = []

            for i in range(3):
                tx_id = str(uuid.uuid4())
                reference = f"MYK{2000000000 + i}"

                transaction = Transaction(
                    id=tx_id,
                    reference=reference,
                    idempotency_key=str(uuid.uuid4()),
                    transaction_type="WITHDRAWAL",
                    status="PENDING_ANCHOR",  # Must be PENDING_ANCHOR to be processed
                    incoming_currency="EUR",
                    outgoing_currency="EURC",
                    value=Decimal("75.00"),
                    fee=Decimal("2.00"),
                    wallet_address=f"Wallet{i}",
                    source="ANCHOR_SOLANA",
                    instruction_type="Transaction",
                )
                db.session.add(transaction)
                transactions.append(transaction)

                message_id = str(uuid.uuid4())
                message_body = {
                    "meta_data": {
                        "idempotency_key": message_id,
                        "token": f"sender-token-{i}"
                    },
                    "payload": {"reference": reference, "status": "APPROVED"}
                }
                message_bodies.append((f"receipt-{i}", message_body))

            db.session.commit()

            # Simulate SQS returning multiple messages
            mock_sqs_client.receive_message.return_value = dict(message_bodies)

            # Consumer processes all messages
            consumer._consume_messages()

            # Verify all stored in inbox
            assert Inbox.query.filter_by(status="pending").count() == 3

            # Processor processes all
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "mock_sig"
                }

                processor._process_messages()

                # Verify all processed
                assert mock_solana.call_count == 3
                assert Inbox.query.filter_by(status="completed").count() == 3

                # Verify all transactions completed
                for transaction in transactions:
                    db.session.refresh(transaction)
                    assert transaction.status == "completed"

    def test_failed_transaction_not_completed(self, app, consumer, processor, mock_sqs_client):
        """Test that failed Solana transactions don't mark inbox as completed"""
        with app.app_context():
            # Create transaction
            tx_id = str(uuid.uuid4())
            reference = "MYK7777777777"
            transaction = Transaction(
                id=tx_id,
                reference=reference,
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="PENDING_ANCHOR",  # Must be PENDING_ANCHOR to be processed
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("30.00"),
                fee=Decimal("0.50"),
                wallet_address="FailWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Message from ledger
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": "sender-token-fail"
                },
                "payload": {"reference": reference, "status": "APPROVED"}
            }

            mock_sqs_client.receive_message.return_value = {
                "receipt-fail": message_body
            }

            # Consumer stores message
            consumer._consume_messages()

            # Processor attempts to process but Solana fails
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "error",
                    "message": "Insufficient balance"
                }

                processor._process_messages()

            # Verify inbox message marked as failed
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message.status == "failed"
            assert inbox_message.last_error is not None
            assert inbox_message.retry_count > 0

    def test_non_withdrawal_not_processed(self, app, consumer, processor, mock_sqs_client):
        """Test that non-withdrawal transactions are not processed for Solana"""
        with app.app_context():
            # Create DEPOSIT transaction
            tx_id = str(uuid.uuid4())
            reference = "MYK8888888888"
            transaction = Transaction(
                id=tx_id,
                reference=reference,
                idempotency_key=str(uuid.uuid4()),
                transaction_type="DEPOSIT",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("100.00"),
                fee=Decimal("2.00"),
                wallet_address="DepositWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Message from ledger
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": "sender-token-deposit"
                },
                "payload": {"reference": reference, "status": "APPROVED"}
            }

            mock_sqs_client.receive_message.return_value = {
                "receipt-deposit": message_body
            }

            # Consumer stores message
            consumer._consume_messages()

            # Processor attempts to process
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                processor._process_messages()

                # Solana transaction should NOT be called for deposit
                mock_solana.assert_not_called()

            # Inbox message should be completed (no action needed)
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message.status == "completed"

    def test_transaction_not_found_handling(self, app, consumer, processor, mock_sqs_client):
        """Test handling when transaction doesn't exist for reference"""
        with app.app_context():
            # No transaction created - only inbox message
            message_id = str(uuid.uuid4())
            reference = "MYK_NONEXISTENT"
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": "sender-token-notfound"
                },
                "payload": {"reference": reference, "status": "APPROVED"}
            }

            mock_sqs_client.receive_message.return_value = {
                "receipt-notfound": message_body
            }

            # Consumer stores message
            consumer._consume_messages()

            # Processor attempts to process
            processor._process_messages()

            # Inbox message should be marked as failed
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message.status == "failed"
            assert "not found" in inbox_message.last_error.lower()

    def test_check_scope_mock_is_called(self, app, consumer, mock_sqs_client, mock_identity_service):
        """Test that check_scope mock is properly called with correct parameters"""
        with app.app_context():
            # Create a message with a token
            message_id = str(uuid.uuid4())
            reference = "MYK_SCOPE_TEST"
            sender_token = "test-sender-token-789"
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": sender_token,
                    "source": "MYKOBO_LEDGER"
                },
                "payload": {
                    "reference": reference,
                    "status": "APPROVED"
                }
            }
            receipt_handle = "receipt-scope-test"

            mock_sqs_client.receive_message.return_value = {
                receipt_handle: message_body
            }

            # Consumer processes the message
            consumer._consume_messages()

            # Verify check_scope was called with correct parameters
            mock_identity_service.acquire_token.assert_called()
            mock_identity_service.check_scope.assert_called_once()

            # Verify the exact parameters passed to check_scope
            check_scope_args = mock_identity_service.check_scope.call_args[0]
            assert check_scope_args[0].token == "test-integration-token-abc123"  # service_token
            assert check_scope_args[1] == sender_token  # token from message meta_data
            assert check_scope_args[2] == "transaction:admin"  # scope being verified

            # Verify message was stored (mock returns authorized by default)
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message is not None
            assert inbox_message.transaction_reference == reference

    def test_unauthorized_message_not_stored(self, app, consumer, mock_sqs_client, mock_identity_service):
        """Test that unauthorized messages are rejected and NOT stored in inbox"""
        with app.app_context():
            # Configure mock to reject authorization
            mock_check_scope_response = Mock()
            mock_check_scope_response.ok = True
            mock_check_scope_response.json = Mock(return_value={
                "authorised": False,
                "message": "Unauthorized - invalid token"
            })
            mock_identity_service.check_scope = Mock(return_value=mock_check_scope_response)

            # Create a message with an invalid token
            message_id = str(uuid.uuid4())
            reference = "MYK_UNAUTHORIZED"
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": "invalid-token-123",
                    "source": "UNKNOWN_SOURCE"
                },
                "payload": {
                    "reference": reference,
                    "status": "APPROVED"
                }
            }
            receipt_handle = "receipt-unauthorized"

            mock_sqs_client.receive_message.return_value = {
                receipt_handle: message_body
            }

            # Consumer processes the message
            consumer._consume_messages()

            # Verify check_scope was called
            mock_identity_service.check_scope.assert_called_once()

            # Verify message was NOT stored in inbox (rejected)
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message is None

            # Verify message was deleted from queue (discarded)
            mock_sqs_client.delete_message.assert_called_once_with(
                consumer.incoming_queue_name,
                receipt_handle
            )

    def test_fee_calculation_in_flow(self, app, consumer, processor, mock_sqs_client):
        """Test that fee is correctly deducted from transaction value"""
        with app.app_context():
            # Create transaction with specific value and fee
            tx_id = str(uuid.uuid4())
            reference = "MYK3333333333"
            value = Decimal("150.00")
            fee = Decimal("7.50")
            expected_net = Decimal("142.50")

            transaction = Transaction(
                id=tx_id,
                reference=reference,
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAWAL",
                status="PENDING_ANCHOR",  # Must be PENDING_ANCHOR to be processed
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=value,
                fee=fee,
                wallet_address="FeeTestWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Message from ledger
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "token": "sender-token-fee"
                },
                "payload": {"reference": reference, "status": "APPROVED"}
            }

            mock_sqs_client.receive_message.return_value = {
                "receipt-fee": message_body
            }

            # Consumer stores message
            consumer._consume_messages()

            # Processor processes with fee calculation
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "sig_fee_test"
                }

                processor._process_messages()

                # Verify Solana called with net amount (value - fee)
                call_args = mock_solana.call_args[1]
                assert call_args['amount'] == float(expected_net)
