"""
Tests for the InboxConsumer service
"""
import uuid
from unittest.mock import Mock, MagicMock, patch
import pytest
from app.inbox_consumer import InboxConsumer
from app.models import Inbox
from app.database import db


class TestInboxConsumer:
    """Tests for the InboxConsumer service"""

    @pytest.fixture
    def mock_identity_service(self):
        """Create a mock identity service client"""
        mock = Mock()
        mock_token = Mock()
        mock_token.token = "test-consumer-token-abc123"
        mock.acquire_token = Mock(return_value=mock_token)

        # Mock check_scope to return authorized response by default
        mock_check_scope_response = Mock()
        mock_check_scope_response.ok = True
        mock_check_scope_response.json = Mock(return_value={
            "authorised": True,
            "message": "Authorized"
        })
        mock.check_scope = Mock(return_value=mock_check_scope_response)

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
        """Create an InboxConsumer instance for testing"""
        app.config["MESSAGE_BUS"] = mock_sqs_client
        app.config["TRANSACTION_QUEUE_NAME"] = "test-queue"
        app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
        return InboxConsumer(app)

    def test_consumer_initialization(self, consumer, mock_sqs_client):
        """Test that consumer initializes correctly"""
        assert consumer.app is not None
        assert consumer.sqs_client == mock_sqs_client
        assert consumer.transaction_queue_name == "test-queue"
        assert consumer.running is False
        assert consumer.poll_interval == 5

    def test_store_in_inbox_new_message(self, consumer, app):
        """Test storing a new message in the inbox"""
        with app.app_context():
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": str(uuid.uuid4()),
                    "event": "NEW_CHAIN_PAYMENT",
                    "source": "MYKOBO_LEDGER",
                },
                "payload": {
                    "reference": "MYK1234567890",
                    "status": "APPROVED",
                    "transaction_id": "tx-123",
                }
            }
            receipt_handle = "receipt-123"

            # Store in inbox - _store_in_inbox expects the payload, not the nested structure
            # (the consumer extracts payload before calling _store_in_inbox)
            consumer._store_in_inbox(message_id, message_body["payload"], receipt_handle)

            # Verify it was stored
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message is not None
            assert inbox_message.message_id == message_id
            # message_body should be the payload only
            assert inbox_message.message_body == message_body["payload"]
            assert inbox_message.transaction_reference == "MYK1234567890"
            assert inbox_message.receipt_handle == receipt_handle
            assert inbox_message.status == "pending"

    def test_store_in_inbox_duplicate_message(self, consumer, app):
        """Test that duplicate messages are rejected (idempotency)"""
        with app.app_context():
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {"idempotency_key": str(uuid.uuid4())},
                "payload": {"reference": "MYK1111111111", "status": "APPROVED"}
            }
            receipt_handle = "receipt-123"

            # Store first time
            consumer._store_in_inbox(message_id, message_body, receipt_handle)

            # Count messages before duplicate attempt
            count_before = Inbox.query.count()

            # Try to store duplicate
            consumer._store_in_inbox(message_id, message_body, receipt_handle)

            # Count should be the same (duplicate not added)
            count_after = Inbox.query.count()
            assert count_after == count_before

    def test_extract_message_id_from_idempotency_key(self, consumer, app):
        """Test extracting message_id from idempotency_key"""
        with app.app_context():
            idempotency_key = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": idempotency_key,
                },
                "payload": {}
            }
            receipt_handle = "receipt-456"

            message_id = consumer._extract_message_id(message_body, receipt_handle)

            # Should use idempotency_key as message_id
            assert message_id == idempotency_key

    def test_extract_message_id_fallback_to_receipt_handle(self, consumer, app):
        """Test fallback to receipt_handle when idempotency_key is missing"""
        with app.app_context():
            message_body = {
                "meta_data": {},
                "payload": {}
            }
            receipt_handle = "receipt-789"

            message_id = consumer._extract_message_id(message_body, receipt_handle)

            # Should fall back to receipt_handle
            assert message_id == receipt_handle

    def test_delete_from_sqs(self, consumer, mock_sqs_client, app):
        """Test deleting message from SQS"""
        with app.app_context():
            receipt_handle = "receipt-delete-test"

            # Delete from SQS
            consumer._delete_from_sqs(receipt_handle)

            # Verify delete was called
            mock_sqs_client.delete_message.assert_called_once_with(
                "test-queue",
                receipt_handle
            )

    def test_consume_messages_no_messages(self, consumer, mock_sqs_client, app):
        """Test consuming when no messages are available"""
        with app.app_context():
            # Configure mock to return empty response
            mock_sqs_client.receive_message.return_value = {}

            # Consume messages
            consumer._consume_messages()

            # Verify no inbox entries created
            assert Inbox.query.count() == 0

    def test_consume_messages_with_message(self, consumer, mock_sqs_client, app):
        """Test consuming a message successfully"""
        with app.app_context():
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                    "event": "NEW_CHAIN_PAYMENT",
                    "token": "test-token-consume"
                },
                "payload": {
                    "reference": "MYK9999999999",
                    "status": "APPROVED",
                }
            }
            receipt_handle = "receipt-consume-test"

            # Configure mock to return a message
            mock_sqs_client.receive_message.return_value = {
                receipt_handle: message_body
            }

            # Consume messages
            consumer._consume_messages()

            # Verify message was stored in inbox
            inbox_message = Inbox.query.filter_by(message_id=message_id).first()
            assert inbox_message is not None
            assert inbox_message.transaction_reference == "MYK9999999999"

            # Verify message was deleted from SQS
            mock_sqs_client.delete_message.assert_called_once_with(
                "test-queue",
                receipt_handle
            )

    def test_consume_messages_multiple_messages(self, consumer, mock_sqs_client, app):
        """Test consuming multiple messages in one batch"""
        with app.app_context():
            message_id_1 = str(uuid.uuid4())
            message_id_2 = str(uuid.uuid4())

            message_body_1 = {
                "meta_data": {
                    "idempotency_key": message_id_1,
                    "token": "test-token-multi-1"
                },
                "payload": {"reference": "MYK1111111111", "status": "APPROVED"}
            }
            message_body_2 = {
                "meta_data": {
                    "idempotency_key": message_id_2,
                    "token": "test-token-multi-2"
                },
                "payload": {"reference": "MYK2222222222", "status": "APPROVED"}
            }

            receipt_handle_1 = "receipt-1"
            receipt_handle_2 = "receipt-2"

            # Configure mock to return multiple messages
            mock_sqs_client.receive_message.return_value = {
                receipt_handle_1: message_body_1,
                receipt_handle_2: message_body_2,
            }

            # Consume messages
            consumer._consume_messages()

            # Verify both messages were stored
            assert Inbox.query.count() == 2
            assert Inbox.query.filter_by(message_id=message_id_1).first() is not None
            assert Inbox.query.filter_by(message_id=message_id_2).first() is not None

            # Verify both were deleted from SQS
            assert mock_sqs_client.delete_message.call_count == 2

    def test_consume_messages_error_handling(self, consumer, mock_sqs_client, app):
        """Test that errors in message storage don't delete from SQS"""
        with app.app_context():
            message_body = {
                "meta_data": {
                    "idempotency_key": str(uuid.uuid4()),
                    "token": "test-token-error"
                },
                "payload": {"reference": "MYK3333333333", "status": "APPROVED"}
            }
            receipt_handle = "receipt-error-test"

            # Configure mock to return a message
            mock_sqs_client.receive_message.return_value = {
                receipt_handle: message_body
            }

            # Mock _store_in_inbox to raise an error
            with patch.object(consumer, '_store_in_inbox', side_effect=Exception("Test error")):
                # Consume messages
                consumer._consume_messages()

                # Verify message was NOT deleted from SQS
                mock_sqs_client.delete_message.assert_not_called()

    def test_stop_consumer(self, consumer):
        """Test stopping the consumer"""
        consumer.running = True
        consumer.stop()
        assert consumer.running is False

    def test_handle_shutdown(self, consumer):
        """Test shutdown signal handling"""
        consumer.running = True
        consumer._handle_shutdown(2, None)  # signum, frame
        assert consumer.running is False

    def test_consumer_with_reference_extraction(self, consumer, app):
        """Test that transaction reference is correctly extracted and indexed"""
        with app.app_context():
            message_id = str(uuid.uuid4())
            reference = "MYK5555555555"
            message_body = {
                "meta_data": {
                    "idempotency_key": message_id,
                },
                "payload": {
                    "reference": reference,
                    "status": "APPROVED",
                }
            }
            receipt_handle = "receipt-ref-test"

            # Store message - _store_in_inbox expects payload only
            consumer._store_in_inbox(message_id, message_body["payload"], receipt_handle)

            # Verify we can query by transaction_reference
            inbox_message = Inbox.query.filter_by(transaction_reference=reference).first()
            assert inbox_message is not None
            assert inbox_message.message_id == message_id

    def test_consumer_logs_duplicate_skip(self, consumer, app, caplog):
        """Test that duplicate messages are logged appropriately"""
        with app.app_context():
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {"idempotency_key": message_id},
                "payload": {"reference": "MYK6666666666", "status": "APPROVED"}
            }
            receipt_handle = "receipt-log-test"

            # Store first time
            consumer._store_in_inbox(message_id, message_body, receipt_handle)

            # Try to store duplicate and check logs
            with caplog.at_level("INFO"):
                consumer._store_in_inbox(message_id, message_body, receipt_handle)
                assert "already exists" in caplog.text.lower() or "duplicate" in caplog.text.lower()
