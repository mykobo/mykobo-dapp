"""
SQS Inbox Consumer - Consumes messages from SQS and writes them to the inbox table.

This service implements the inbox pattern by:
1. Consuming messages from SQS queue
2. Writing messages to the inbox table (with idempotency)
3. Deleting messages from SQS after successful persistence
4. Allowing the transaction processor to poll the inbox independently
"""
import time
import signal
import sys
from typing import Dict, Any
from flask import Flask
from requests import HTTPError
from sqlalchemy.exc import IntegrityError
from app.database import db
from app.models import Inbox


class InboxConsumer:
    """
    Background service that consumes SQS messages and writes to inbox table.
    """

    def __init__(self, app: Flask):
        """
        Initialize the inbox consumer.

        Args:
            app: Flask application instance
        """
        self.app = app
        self.running = False
        self.logger = app.logger

        # Get SQS client from app config
        self.sqs_client = app.config.get("MESSAGE_BUS")
        self.incoming_queue_name = app.config.get("NOTIFICATIONS_QUEUE_NAME")
        self.identity_client = app.config.get("IDENTITY_SERVICE_CLIENT")

        # Polling configuration
        self.poll_interval = 5  # seconds between polls

    def start(self):
        """Start the inbox consumer."""
        self.running = True
        self.logger.info("Starting Inbox Consumer...")
        self.logger.info(f"Queue: {self.incoming_queue_name}")
        self.logger.info(f"Poll interval: {self.poll_interval}s")

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Main processing loop
        try:
            while self.running:
                self._consume_messages()
                if self.running:
                    time.sleep(self.poll_interval)
        except Exception as e:
            self.logger.exception(f"Fatal error in inbox consumer: {e}")
            sys.exit(1)

    def stop(self):
        """Stop the inbox consumer gracefully."""
        self.logger.info("Stopping Inbox Consumer...")
        self.running = False

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()

    def _consume_messages(self):
        """Poll SQS and write messages to inbox table."""
        try:
            # Receive message using mykobo-py SQS client
            message_data = self.sqs_client.receive_message(self.incoming_queue_name)

            if not message_data:
                self.logger.debug("No messages received")
                return

            # mykobo-py returns {receipt_handle: message_body}
            for receipt_handle, message_body in message_data.items():
                try:
                    # Generate a message_id if not present (use receipt_handle as fallback)
                    # In real SQS, message_id would be in the response
                    message_id = self._extract_message_id(message_body, receipt_handle)
                    payload = message_body["payload"]
                    meta_data = message_body["meta_data"]
                    service_token = self.identity_client.acquire_token()

                    # Verify message source authorization
                    authorized = False
                    try:
                        check_scope_response = self.identity_client.check_scope(
                            service_token,
                            meta_data.get("token"),
                            "transaction:admin"
                        )
                        if check_scope_response.ok:
                            scope_check_payload = check_scope_response.json()
                            if "authorised" in scope_check_payload and scope_check_payload["authorised"]:
                                authorized = True
                                self.logger.info(
                                    f"Source [{meta_data.get('source')}] verified, can proceed!")
                            else:
                                self.logger.warning(scope_check_payload.get("message", "Unauthorized"))
                                self.logger.info("Discarding unauthorized message...")
                                self._delete_from_sqs(receipt_handle)
                                continue  # Skip storing this message

                        else:
                            self.logger.error(
                                f"Source [{meta_data.get('source')}] could not be verified")
                            self.logger.error(f"CHECK SCOPE RESPONSE {check_scope_response.json()}")
                            self._delete_from_sqs(receipt_handle)
                            continue  # Skip storing this message
                    except HTTPError as e:
                        self.logger.error(f"Could not verify source of message: {e}")
                        self._delete_from_sqs(receipt_handle)
                        continue  # Skip storing this message

                    # Only store if authorized
                    if authorized:
                        self._store_in_inbox(message_id, payload, receipt_handle)
                        self._delete_from_sqs(receipt_handle)

                except Exception as e:
                    self.logger.exception(f"Error storing message in inbox: {e}")
                    # Don't delete from SQS - let it retry

        except Exception as e:
            self.logger.exception(f"Error in message consumption: {e}")

    def _extract_message_id(self, message_body: Dict[str, Any], receipt_handle: str) -> str:
        """
        Extract or generate a message ID for idempotency.

        Args:
            message_body: Message body dictionary
            receipt_handle: SQS receipt handle

        Returns:
            Message ID string
        """
        # Try to use idempotency_key from message as message_id
        meta_data = message_body.get('meta_data', {})
        idempotency_key = meta_data.get('idempotency_key')

        if idempotency_key:
            return idempotency_key

        # Fallback to using receipt handle (not ideal but works)
        # In production, you should modify the SQS receive to get the actual MessageId
        return receipt_handle[:255]  # Truncate to fit column size

    def _store_in_inbox(self, message_id: str, message_body: Dict[str, Any], receipt_handle: str):
        """
        Store message in inbox table with idempotency.

        Args:
            message_id: Unique message identifier
            message_body: Parsed message body
            receipt_handle: SQS receipt handle
        """
        with self.app.app_context():
            try:
                # Check if message already exists (idempotency)
                existing = Inbox.query.filter_by(message_id=message_id).first()

                if existing:
                    self.logger.info(
                        f"Message {message_id} already exists in inbox (id={existing.id}), "
                        f"skipping duplicate"
                    )
                    return

                # Create inbox record
                inbox_message = Inbox.from_sqs_message(
                    message_id=message_id,
                    message_body=message_body,
                    receipt_handle=receipt_handle
                )

                db.session.add(inbox_message)
                db.session.commit()

                self.logger.info(
                    f"Stored message in inbox: id={inbox_message.id}, "
                    f"reference={inbox_message.transaction_reference}"
                )

            except IntegrityError as e:
                # Handle race condition where message was inserted by another process
                db.session.rollback()
                self.logger.warning(
                    f"Message {message_id} was already inserted by another process"
                )
            except Exception as e:
                db.session.rollback()
                self.logger.exception(f"Error storing message in inbox: {e}")
                raise

    def _delete_from_sqs(self, receipt_handle: str):
        """
        Delete message from SQS queue after successful persistence.

        Args:
            receipt_handle: SQS receipt handle
        """
        try:
            self.sqs_client.delete_message(
                self.incoming_queue_name,
                receipt_handle
            )
            self.logger.debug(f"Deleted message from SQS: {receipt_handle[:20]}...")
        except Exception as e:
            self.logger.exception(f"Error deleting message from SQS: {e}")
            # This is not critical - message will reappear and be deduplicated


def create_inbox_consumer(env: str = 'development') -> InboxConsumer:
    """
    Create and initialize an inbox consumer.

    Args:
        env: Environment name (development, production)

    Returns:
        InboxConsumer instance
    """
    from app import create_app

    # Create Flask app
    app = create_app(env)

    # Create consumer
    with app.app_context():
        consumer = InboxConsumer(app)
        return consumer


if __name__ == '__main__':
    """
    Run the inbox consumer as a standalone process.

    Usage:
        ENV=development python -m app.inbox_consumer
        ENV=production python -m app.inbox_consumer
    """
    import os

    env = os.getenv('ENV', 'development')
    print(f"Starting Inbox Consumer in {env} mode...")

    consumer = create_inbox_consumer(env)
    consumer.start()
