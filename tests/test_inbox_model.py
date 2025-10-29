"""
Tests for the Inbox model and inbox pattern functionality
"""
import uuid
from datetime import datetime, UTC
import pytest
from app.models import Inbox
from app.database import db


class TestInboxModel:
    """Tests for the Inbox model"""

    def test_create_inbox_from_sqs_message(self, app):
        """Test creating an Inbox record from SQS message"""
        with app.app_context():
            message_id = str(uuid.uuid4())
            message_body = {
                "meta_data": {
                    "idempotency_key": str(uuid.uuid4()),
                    "event": "NEW_CHAIN_PAYMENT",
                    "source": "MYKOBO_LEDGER",
                },
                "payload": {
                    "reference": "MYK1747799079",
                    "status": "APPROVED",
                    "transaction_id": "ledger-tx-id-123",
                }
            }
            receipt_handle = "receipt-handle-123"

            # Create inbox message from SQS message
            # from_sqs_message expects the payload, not the nested structure
            inbox_message = Inbox.from_sqs_message(
                message_id=message_id,
                message_body=message_body["payload"],  # Pass payload only
                receipt_handle=receipt_handle
            )

            # Verify fields
            assert inbox_message.message_id == message_id
            assert inbox_message.receipt_handle == receipt_handle
            # message_body should be the payload
            assert inbox_message.message_body == message_body["payload"]
            assert inbox_message.transaction_reference == "MYK1747799079"
            assert inbox_message.status == "pending"
            # retry_count and last_error get defaults from database, not set in constructor
            assert inbox_message.last_error is None

    def test_inbox_persistence(self, app):
        """Test saving and retrieving inbox message from database"""
        with app.app_context():
            message_id = f"msg-{uuid.uuid4()}"
            inbox_message = Inbox(
                message_id=message_id,
                message_body={"test": "data"},
                transaction_reference="TEST_REF_001",
                status="pending"
            )

            # Save to database
            db.session.add(inbox_message)
            db.session.commit()

            # Verify it was saved
            assert inbox_message.id is not None

            # Retrieve from database
            retrieved = Inbox.query.filter_by(message_id=message_id).first()

            # Verify retrieved inbox message
            assert retrieved is not None
            assert retrieved.message_id == message_id
            assert retrieved.transaction_reference == "TEST_REF_001"
            assert retrieved.status == "pending"

    def test_inbox_idempotency(self, app):
        """Test that duplicate message_id is rejected"""
        with app.app_context():
            message_id = f"msg-{uuid.uuid4()}"

            # Create first inbox message
            inbox1 = Inbox(
                message_id=message_id,
                message_body={"test": "data1"},
                transaction_reference="REF_001",
                status="pending"
            )

            db.session.add(inbox1)
            db.session.commit()

            # Try to create duplicate with same message_id
            inbox2 = Inbox(
                message_id=message_id,  # Duplicate
                message_body={"test": "data2"},
                transaction_reference="REF_002",
                status="pending"
            )

            db.session.add(inbox2)

            # Should raise integrity error
            with pytest.raises(Exception):  # Will be IntegrityError
                db.session.commit()

            db.session.rollback()

    def test_mark_processing(self, app):
        """Test marking inbox message as processing"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF",
                status="pending"
            )

            db.session.add(inbox_message)
            db.session.commit()

            # Mark as processing
            inbox_message.mark_processing()
            db.session.commit()

            # Verify status changed
            assert inbox_message.status == "processing"
            assert inbox_message.processing_started_at is not None
            assert isinstance(inbox_message.processing_started_at, datetime)

    def test_mark_completed(self, app):
        """Test marking inbox message as completed"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF",
                status="processing"
            )

            db.session.add(inbox_message)
            db.session.commit()

            # Mark as completed
            inbox_message.mark_completed()
            db.session.commit()

            # Verify status changed
            assert inbox_message.status == "completed"
            assert inbox_message.processed_at is not None
            assert isinstance(inbox_message.processed_at, datetime)

    def test_mark_failed(self, app):
        """Test marking inbox message as failed"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF",
                status="processing"
            )

            db.session.add(inbox_message)
            db.session.commit()

            # Mark as failed
            error_message = "Test error occurred"
            inbox_message.mark_failed(error_message)
            db.session.commit()

            # Verify status changed
            assert inbox_message.status == "failed"
            assert inbox_message.last_error == error_message
            assert inbox_message.retry_count == 1

    def test_reset_for_retry(self, app):
        """Test resetting inbox message for retry"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF",
                status="failed"
            )
            inbox_message.retry_count = 2
            inbox_message.last_error = "Previous error"
            inbox_message.processing_started_at = datetime.now(UTC)

            db.session.add(inbox_message)
            db.session.commit()

            # Reset for retry
            inbox_message.reset_for_retry()
            db.session.commit()

            # Verify reset
            assert inbox_message.status == "pending"
            assert inbox_message.processing_started_at is None
            assert inbox_message.retry_count == 2  # Not reset, keeps count

    def test_inbox_to_dict(self, app):
        """Test converting inbox message to dictionary"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF_123",
                status="completed",
                retry_count=0,
                last_error=None
            )

            db.session.add(inbox_message)
            db.session.commit()

            # Convert to dict
            inbox_dict = inbox_message.to_dict()

            # Verify dict structure
            assert inbox_dict['message_id'] == inbox_message.message_id
            assert inbox_dict['transaction_reference'] == "TEST_REF_123"
            assert inbox_dict['status'] == "completed"
            assert inbox_dict['retry_count'] == 0
            assert inbox_dict['last_error'] is None
            assert 'created_at' in inbox_dict
            assert 'updated_at' in inbox_dict

    def test_inbox_repr(self, app):
        """Test inbox message string representation"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF_999",
                status="pending"
            )

            db.session.add(inbox_message)
            db.session.commit()

            repr_str = repr(inbox_message)
            assert "TEST_REF_999" in repr_str
            assert "pending" in repr_str

    def test_inbox_timestamps(self, app):
        """Test that timestamps are automatically set"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF",
                status="pending"
            )

            db.session.add(inbox_message)
            db.session.commit()

            # Timestamps should be set after saving
            assert inbox_message.created_at is not None
            assert inbox_message.updated_at is not None
            assert inbox_message.received_at is not None
            assert isinstance(inbox_message.created_at, datetime)
            assert isinstance(inbox_message.updated_at, datetime)
            assert isinstance(inbox_message.received_at, datetime)

    def test_query_pending_messages(self, app):
        """Test querying for pending messages"""
        with app.app_context():
            # Create multiple messages with different statuses
            pending1 = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data1"},
                transaction_reference="REF_001",
                status="pending"
            )
            pending2 = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data2"},
                transaction_reference="REF_002",
                status="pending"
            )
            completed = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data3"},
                transaction_reference="REF_003",
                status="completed"
            )

            db.session.add_all([pending1, pending2, completed])
            db.session.commit()

            # Query for pending messages
            pending_messages = Inbox.query.filter_by(status="pending").all()

            # Verify only pending messages returned
            assert len(pending_messages) == 2
            assert all(msg.status == "pending" for msg in pending_messages)

    def test_retry_count_increment(self, app):
        """Test that retry count increments on failure"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=f"msg-{uuid.uuid4()}",
                message_body={"test": "data"},
                transaction_reference="TEST_REF",
                status="processing"
            )

            db.session.add(inbox_message)
            db.session.commit()

            # Mark as failed multiple times
            initial_count = inbox_message.retry_count
            inbox_message.mark_failed("Error 1")
            db.session.commit()
            assert inbox_message.retry_count == initial_count + 1

            inbox_message.mark_failed("Error 2")
            db.session.commit()
            assert inbox_message.retry_count == initial_count + 2

            inbox_message.mark_failed("Error 3")
            db.session.commit()
            assert inbox_message.retry_count == initial_count + 3
