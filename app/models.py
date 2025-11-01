"""
Database models for the Flask application.
"""
from datetime import datetime, UTC
from decimal import Decimal
from typing import Dict, Any
import json
import uuid
from app.database import db


class Transaction(db.Model):
    """
    Model for storing transaction records sent to the ledger.

    This stores a local copy of all transactions created through the dApp
    before they are sent to the ledger service.

    Note: The 'dapp' schema is used for PostgreSQL in production.
    For SQLite (used in tests), no schema is specified as SQLite doesn't support schemas.
    The test configuration overrides this by using SQLite's in-memory database.
    """
    __tablename__ = 'transactions'
    # For PostgreSQL, tables are in the 'dapp' schema
    # For SQLite tests, this is ignored via metadata.schema override
    __table_args__ = {'schema': 'dapp'}

    # Primary key
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Transaction identifiers
    reference = db.Column(db.String(255), unique=True, nullable=False, index=True)
    idempotency_key = db.Column(db.String(255), unique=True, nullable=False, index=True)

    # Transaction details
    transaction_type = db.Column(db.String(50), nullable=False)  # DEPOSIT, WITHDRAW
    status = db.Column(db.String(50), nullable=False, index=True)  # PENDING_PAYER, PENDING_PAYEE, etc.
    incoming_currency = db.Column(db.String(10), nullable=False)
    outgoing_currency = db.Column(db.String(10), nullable=False)
    value = db.Column(db.Numeric(precision=20, scale=6), nullable=False)
    fee = db.Column(db.Numeric(precision=20, scale=6), nullable=False)

    # User information
    payer_id = db.Column(db.String(255), nullable=True, index=True)
    payee_id = db.Column(db.String(255), nullable=True, index=True)
    first_name = db.Column(db.String(255), nullable=True)
    last_name = db.Column(db.String(255), nullable=True)
    wallet_address = db.Column(db.String(255), nullable=False, index=True)

    # Source and metadata
    source = db.Column(db.String(50), nullable=False)  # ANCHOR_SOLANA, etc.
    instruction_type = db.Column(db.String(50), nullable=False)  # Transaction
    ip_address = db.Column(db.String(45), nullable=True)  # IPv4 or IPv6

    # Message queue tracking
    message_id = db.Column(db.String(255), nullable=True)  # SQS Message ID
    queue_sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def __repr__(self):
        return f'<Transaction {self.reference} - {self.transaction_type} - {self.status}>'

    def to_dict(self):
        """Convert transaction to dictionary format."""
        return {
            'id': self.id,
            'reference': self.reference,
            'idempotency_key': self.idempotency_key,
            'transaction_type': self.transaction_type,
            'status': self.status,
            'incoming_currency': self.incoming_currency,
            'outgoing_currency': self.outgoing_currency,
            'value': str(self.value),
            'fee': str(self.fee),
            'payer_id': self.payer_id,
            'payee_id': self.payee_id,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'wallet_address': self.wallet_address,
            'source': self.source,
            'instruction_type': self.instruction_type,
            'ip_address': self.ip_address,
            'message_id': self.message_id,
            'queue_sent_at': self.queue_sent_at.isoformat() if self.queue_sent_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_ledger_payload(cls, ledger_payload, wallet_address, message_id=None):
        """
        Create a Transaction instance from a ledger payload.

        Args:
            ledger_payload: The payload dict being sent to the ledger
            wallet_address: The wallet address of the user creating the transaction
            message_id: Optional SQS message ID if already sent

        Returns:
            Transaction instance
        """
        meta_data = ledger_payload.get('meta_data', {})
        payload = ledger_payload.get('payload', {})

        # Convert string values to Decimal for proper numeric handling
        value = payload.get('value')
        fee = payload.get('fee')
        if isinstance(value, str):
            value = Decimal(value)
        if isinstance(fee, str):
            fee = Decimal(fee)

        return cls(
            id=payload.get('external_reference'),
            reference=payload.get('reference'),
            idempotency_key=meta_data.get('idempotency_key'),
            transaction_type=payload.get('transaction_type'),
            status=payload.get('status'),
            incoming_currency=payload.get('incoming_currency'),
            outgoing_currency=payload.get('outgoing_currency'),
            value=value,
            fee=fee,
            payer_id=payload.get('payer'),
            payee_id=payload.get('payee'),
            first_name=payload.get('first_name'),
            last_name=payload.get('last_name'),
            wallet_address=wallet_address,
            source=payload.get('source'),
            instruction_type=meta_data.get('instruction_type'),
            ip_address=meta_data.get('ip_address'),
            message_id=message_id,
            queue_sent_at=datetime.now(UTC) if message_id else None,
        )


class Inbox(db.Model):
    """
    Inbox pattern implementation for storing consumed SQS messages.

    This table acts as a persistent inbox where the SQS consumer writes all
    incoming messages. The transaction processor then polls this inbox and
    processes messages, providing better transactional guarantees and
    separation of concerns.

    Benefits:
    - Idempotent message consumption (duplicate messages are ignored)
    - Messages are persisted before processing
    - Processing can be retried independently of SQS
    - Better visibility into message processing pipeline
    - Enables transaction processing across both inbox and transaction tables
    """
    __tablename__ = 'inbox'
    __table_args__ = {'schema': 'dapp'}

    # Primary key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Message identifiers (for idempotency)
    message_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    receipt_handle = db.Column(db.Text, nullable=True)  # SQS receipt handle

    # Message content
    message_body = db.Column(db.JSON, nullable=False)  # Full message payload

    # Processing status
    status = db.Column(
        db.String(50),
        nullable=False,
        default='pending',
        index=True
    )  # pending, processing, completed, failed

    # Processing metadata
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    processing_started_at = db.Column(db.DateTime(timezone=True), nullable=True)
    retry_count = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)

    # Message metadata (extracted for quick lookup)
    transaction_reference = db.Column(db.String(255), nullable=True, index=True)

    # Timestamps
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def __repr__(self):
        return f'<Inbox {self.id} - {self.transaction_reference} - {self.status}>'

    def to_dict(self):
        """Convert inbox message to dictionary format."""
        return {
            'id': self.id,
            'message_id': self.message_id,
            'status': self.status,
            'transaction_reference': self.transaction_reference,
            'retry_count': self.retry_count,
            'last_error': self.last_error,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_sqs_message(cls, message_id: str, message_body: Dict[str, Any], receipt_handle: str = None):
        """
        Create an Inbox instance from an SQS message payload.

        Args:
            message_id: SQS Message ID
            message_body: Payload dictionary (flat, already extracted from nested SQS message)
            receipt_handle: SQS receipt handle

        Returns:
            Inbox instance
        """
        # message_body is already the extracted payload (flat structure)
        # The consumer extracts the payload before calling this method
        reference = message_body.get('reference')

        return cls(
            message_id=message_id,
            receipt_handle=receipt_handle,
            message_body=message_body,  # Store the payload as-is
            transaction_reference=reference,
            status='pending'
        )

    def mark_processing(self):
        """Mark message as being processed."""
        self.status = 'processing'
        self.processing_started_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def mark_completed(self):
        """Mark message as successfully processed."""
        self.status = 'completed'
        self.processed_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error_message: str):
        """
        Mark message as failed.

        Args:
            error_message: Error message to store
        """
        self.status = 'failed'
        self.last_error = error_message
        self.retry_count += 1
        self.updated_at = datetime.now(UTC)

    def reset_for_retry(self):
        """Reset message status to pending for retry."""
        self.status = 'pending'
        self.processing_started_at = None
        self.updated_at = datetime.now(UTC)


class Nonce(db.Model):
    """
    Model for storing authentication nonces.

    Nonces are used for wallet signature authentication to prevent replay attacks.
    Each nonce is single-use and has an expiration time.
    """
    __tablename__ = 'nonces'
    __table_args__ = {'schema': 'dapp'}

    # Primary key
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Nonce value (unique)
    nonce = db.Column(db.String(255), unique=True, nullable=False, index=True)

    # Associated wallet address
    wallet_address = db.Column(db.String(255), nullable=False, index=True)

    # Expiration timestamp
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)

    # Usage tracking
    used = db.Column(db.Boolean, nullable=False, default=False)
    used_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    def __repr__(self):
        return f'<Nonce {self.nonce[:8]}... - {self.wallet_address[:8]}... - used={self.used}>'

    def is_expired(self) -> bool:
        """Check if nonce has expired."""
        # Ensure both datetimes have timezone info for comparison
        current_time = datetime.now(UTC)
        expires_at = self.expires_at

        # If expires_at is naive (SQLite), make it aware
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        return current_time > expires_at

    def mark_used(self):
        """Mark nonce as used."""
        self.used = True
        self.used_at = datetime.now(UTC)

    def to_dict(self):
        """Convert nonce to dictionary format."""
        return {
            'id': self.id,
            'nonce': self.nonce,
            'wallet_address': self.wallet_address,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'used': self.used,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
