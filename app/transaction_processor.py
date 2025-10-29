"""
Transaction processor for processing inbox messages and creating Solana transactions.

This background process implements the inbox pattern by:
1. Polling the inbox table for pending messages
2. Processing transaction status updates
3. Constructing and sending Solana transactions for approved withdrawals
4. Handling value minus fee calculations based on outgoing currency
5. Updating inbox message status after processing
6. Sending status update messages to queue after successful Solana transactions
"""
import json
import time
import signal
import sys
import uuid
from datetime import datetime, UTC
from typing import Dict, Any
from flask import Flask
from app.database import db
from app.models import Transaction, Inbox


class TransactionProcessor:
    """
    Background process that polls inbox table and processes transactions.
    """

    def __init__(self, app: Flask):
        """
        Initialize the transaction processor.

        Args:
            app: Flask application instance
        """
        self.app = app
        self.running = False
        self.logger = app.logger

        # Identity service for acquiring tokens
        self.identity_service = app.config.get("IDENTITY_SERVICE_CLIENT")

        # SQS configuration for status updates
        self.message_bus = app.config.get("MESSAGE_BUS")
        self.status_update_queue_name = app.config.get("TRANSACTION_STATUS_UPDATE_QUEUE_NAME")

        # Solana configuration
        self.solana_rpc_url = app.config.get("SOLANA_RPC_URL")
        self.distribution_private_key = app.config.get("SOLANA_DISTRIBUTION_PRIVATE_KEY")
        self.eurc_mint = app.config.get("EURC_TOKEN_MINT")
        self.usdc_mint = app.config.get("USDC_TOKEN_MINT")

        # Polling configuration
        self.poll_interval = 5  # seconds between polls
        self.batch_size = 10  # number of messages to process per batch

        # Status transitions that trigger Solana transactions
        # APPROVED means the ledger has approved the transaction for payout
        self.actionable_statuses = ['APPROVED']

    def start(self):
        """Start the processor background process."""
        self.running = True
        self.logger.info("Starting Transaction Processor...")
        self.logger.info(f"Polling inbox table for pending messages")
        self.logger.info(f"Poll interval: {self.poll_interval}s")
        self.logger.info(f"Batch size: {self.batch_size}")

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Main processing loop
        try:
            while self.running:
                self._process_messages()
                if self.running:
                    time.sleep(self.poll_interval)
        except Exception as e:
            self.logger.exception(f"Fatal error in processor: {e}")
            sys.exit(1)

    def stop(self):
        """Stop the processor gracefully."""
        self.logger.info("Stopping Transaction Processor...")
        self.running = False

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()

    def _process_messages(self):
        """Poll inbox table and process pending messages."""
        with self.app.app_context():
            try:
                # Get pending messages from inbox
                pending_messages = Inbox.query.filter_by(
                    status='pending'
                ).order_by(
                    Inbox.created_at.asc()
                ).limit(self.batch_size).all()

                if not pending_messages:
                    self.logger.debug("No pending messages in inbox")
                    return

                self.logger.info(f"Found {len(pending_messages)} pending message(s) in inbox")

                # Process each message
                for inbox_message in pending_messages:
                    try:
                        self._process_inbox_message(inbox_message)
                    except Exception as e:
                        self.logger.exception(
                            f"Error processing inbox message {inbox_message.id}: {e}"
                        )
                        # Mark as failed but continue processing other messages
                        inbox_message.mark_failed(str(e))
                        db.session.commit()

            except Exception as e:
                self.logger.exception(f"Error in inbox polling: {e}")

    def _process_inbox_message(self, inbox_message: Inbox):
        """
        Process a single inbox message.

        Args:
            inbox_message: Inbox model instance
        """
        self.logger.info(
            f"Processing inbox message: id={inbox_message.id}, "
            f"reference={inbox_message.transaction_reference}"
        )

        try:
            # Mark as processing
            inbox_message.mark_processing()
            db.session.commit()

            message_body = inbox_message.message_body
            self.logger.debug(f"Message body: {json.dumps(message_body, indent=2)}")

            # message_body IS the payload (flat structure)
            reference = message_body.get('reference')
            status = message_body.get('status')
            transaction_id = message_body.get('transaction_id')

            if not reference:
                self.logger.warning(f"Message has no reference, marking as failed")
                inbox_message.mark_failed("Message has no reference")
                db.session.commit()
                return

            self.logger.info(
                f"Transaction [{reference}] - Status: {status}, ID: {transaction_id}"
            )

            # Look up the transaction in the database
            transaction = Transaction.query.filter_by(reference=reference).first()

            if not transaction:
                error_msg = f"Transaction not found in database for reference: {reference}"
                self.logger.error(error_msg)
                inbox_message.mark_failed(error_msg)
                db.session.commit()
                return

            self.logger.info(
                f"Found transaction in DB: type={transaction.transaction_type}, "
                f"status={transaction.status}, "
                f"outgoing_currency={transaction.outgoing_currency}"
            )

            # Handle FUNDS_RECEIVED status - update transaction to PENDING_ANCHOR
            if status == 'FUNDS_RECEIVED':
                self.logger.info(
                    f"Transaction [{reference}] received FUNDS_RECEIVED status, "
                    f"updating to PENDING_ANCHOR"
                )
                transaction.status = 'PENDING_ANCHOR'
                transaction.updated_at = datetime.now(UTC)
                db.session.commit()
                self.logger.info(
                    f"Updated transaction [{reference}] status to PENDING_ANCHOR"
                )

            # Check if this is a withdrawal that needs Solana transaction
            if self._should_process_transaction(transaction, status):
                self._handle_transaction(transaction)
            else:
                self.logger.info(
                    f"Transaction [{reference}] does not require Solana processing "
                    f"(type={transaction.transaction_type}, status={status})"
                )

            # Mark as completed after successful processing
            inbox_message.mark_completed()
            db.session.commit()
            self.logger.info(
                f"Successfully processed inbox message {inbox_message.id} for [{reference}]"
            )

        except Exception as e:
            self.logger.exception(f"Error processing inbox message {inbox_message.id}: {e}")
            raise

    def _should_process_transaction(self, transaction: Transaction, message_status: str) -> bool:
        """
        Determine if a transaction should trigger Solana processing.

        Args:
            transaction: Transaction model instance
            message_status: Status from the message payload

        Returns:
            True if transaction should be processed
        """
        transaction_status = transaction.status.upper()
        if transaction_status == 'PENDING_ANCHOR':
            # Check if message status indicates the transaction is approved and ready
            return message_status in self.actionable_statuses

        return False

    def _handle_transaction(
            self,
            transaction: Transaction
    ):
        """
        Handle withdrawal transaction by creating and sending Solana transaction.

        Args:
            transaction: Transaction model instance from database
        """
        reference = transaction.reference

        try:
            # Extract transaction details from the database record
            wallet_address = transaction.wallet_address
            value = transaction.value
            fee = transaction.fee
            outgoing_currency = transaction.outgoing_currency
            incoming_currency = transaction.incoming_currency

            self.logger.info(
                f"Processing withdraw [{reference}]: "
                f"{value} {incoming_currency} -> {outgoing_currency}, "
                f"Fee: {fee}, Net: {value - fee}"
            )

            # Validate required fields
            if not wallet_address:
                raise ValueError("No wallet address found for transaction")

            if not outgoing_currency:
                raise ValueError("No outgoing currency specified")

            if value <= 0:
                raise ValueError(f"Invalid value: {value}")

            # Calculate net amount (value minus fee)
            net_amount = value - fee

            if net_amount <= 0:
                raise ValueError(f"Net amount is zero or negative: {net_amount}")

            # Determine token mint based on outgoing currency
            token_mint = self._get_token_mint(outgoing_currency)

            # Create and send Solana transaction
            tx_result = self._create_and_send_solana_transaction(
                recipient_address=wallet_address,
                amount=float(net_amount),
                token_mint=token_mint,
                currency=outgoing_currency
            )

            if tx_result['status'] == 'success':
                solana_signature = tx_result.get('transaction_signature')
                self.logger.info(
                    f"Solana transaction created for [{reference}]: "
                    f"Signature: {solana_signature}"
                )

                # Update transaction record in database (already in app context)
                transaction.status = 'completed'
                transaction.updated_at = datetime.now(UTC)
                # TODO: Add a field to store Solana transaction signature
                # transaction.solana_tx_signature = solana_signature
                db.session.commit()
                self.logger.info(f"Updated transaction [{reference}] status to completed")

                # Send status update message to queue
                self._send_status_update(transaction, solana_signature)
            else:
                raise Exception(f"Failed to create Solana transaction: {tx_result.get('message')}")

        except Exception as e:
            self.logger.exception(f"Error handling withdraw [{reference}]: {e}")
            raise

    def _get_token_mint(self, currency: str) -> str:
        """
        Get Solana token mint address for currency.

        Args:
            currency: Currency code (EURC, USDC, etc.)

        Returns:
            Token mint address

        Raises:
            ValueError: If currency not supported
        """
        currency_upper = currency.upper()

        if currency_upper == 'EURC':
            return self.eurc_mint
        elif currency_upper == 'USDC':
            return self.usdc_mint
        else:
            raise ValueError(f"Unsupported currency: {currency}")

    def _create_and_send_solana_transaction(
            self,
            recipient_address: str,
            amount: float,
            token_mint: str,
            currency: str
    ) -> Dict[str, Any]:
        """
        Create and send a Solana token transfer transaction.

        Args:
            recipient_address: Recipient's Solana wallet address
            amount: Amount to transfer (in token units)
            token_mint: Token mint address
            currency: Currency code for logging

        Returns:
            Dict with transaction result
        """
        try:
            from solana.rpc.api import Client
            from solders.keypair import Keypair
            from solders.pubkey import Pubkey
            from solders.transaction import Transaction as SolanaTransaction
            from spl.token.instructions import (
                get_associated_token_address,
                create_associated_token_account,
                transfer_checked,
                TransferCheckedParams,
            )
            from spl.token.constants import TOKEN_PROGRAM_ID

            self.logger.info(
                f"Creating Solana transaction: {amount} {currency} to {recipient_address}"
            )

            # Initialize Solana client
            client = Client(self.solana_rpc_url)

            # Parse keypairs and addresses
            distribution_keypair = Keypair.from_base58_string(self.distribution_private_key)
            distribution_pubkey = distribution_keypair.pubkey()
            recipient_pubkey = Pubkey.from_string(recipient_address)
            mint_pubkey = Pubkey.from_string(token_mint)

            # Token has 6 decimals
            decimals = 6
            amount_in_smallest_unit = int(amount * (10 ** decimals))

            # Get associated token accounts
            distribution_token_account = get_associated_token_address(
                distribution_pubkey,
                mint_pubkey
            )
            recipient_token_account = get_associated_token_address(
                recipient_pubkey,
                mint_pubkey
            )

            # Create transaction
            transaction = SolanaTransaction()

            # Check if recipient token account exists
            recipient_account_info = client.get_account_info(recipient_token_account)

            # If recipient doesn't have a token account, create it
            if not recipient_account_info.value:
                self.logger.info(
                    f"Creating token account for recipient: {recipient_token_account}"
                )
                create_account_ix = create_associated_token_account(
                    payer=distribution_pubkey,
                    owner=recipient_pubkey,
                    mint=mint_pubkey,
                )
                transaction.add(create_account_ix)

            # Add transfer instruction
            transfer_ix = transfer_checked(
                TransferCheckedParams(
                    program_id=TOKEN_PROGRAM_ID,
                    source=distribution_token_account,
                    mint=mint_pubkey,
                    dest=recipient_token_account,
                    owner=distribution_pubkey,
                    amount=amount_in_smallest_unit,
                    decimals=decimals,
                )
            )
            transaction.add(transfer_ix)

            # Get recent blockhash
            recent_blockhash = client.get_latest_blockhash().value.blockhash
            transaction.recent_blockhash = recent_blockhash
            transaction.fee_payer = distribution_pubkey

            # Sign transaction
            transaction.sign(distribution_keypair)

            # Send transaction
            result = client.send_raw_transaction(transaction.serialize())

            self.logger.info(f"Solana transaction sent: {result.value}")

            return {
                "status": "success",
                "transaction_signature": str(result.value),
                "message": "Transaction sent successfully",
                "details": {
                    "from_address": str(distribution_pubkey),
                    "to_address": recipient_address,
                    "amount": amount,
                    "currency": currency,
                    "token_mint": token_mint,
                }
            }

        except Exception as e:
            self.logger.exception(f"Error creating Solana transaction: {e}")
            return {
                "status": "error",
                "message": str(e),
                "transaction_signature": None,
                "details": None
            }

    def _send_status_update(self, transaction: Transaction, solana_signature: str):
        """
        Send transaction status update message to queue.

        Args:
            transaction: Transaction model instance
            solana_signature: Solana transaction signature
        """
        try:
            if not self.message_bus or not self.status_update_queue_name:
                self.logger.warning(
                    f"Status update queue not configured, skipping status update for [{transaction.reference}]"
                )
                return

            # Acquire service token for authentication - REQUIRED
            if not self.identity_service:
                error_msg = f"Identity service not configured, cannot send status update for [{transaction.reference}]"
                self.logger.error(error_msg)
                raise ValueError(error_msg)

            try:
                service_token = self.identity_service.acquire_token()
                self.logger.debug("Acquired service token for status update")
            except Exception as e:
                error_msg = f"Failed to acquire service token for [{transaction.reference}]: {e}"
                self.logger.error(error_msg)
                raise ValueError(error_msg) from e

            # Construct status update message
            status_update_message = {
                "meta_data": {
                    "idempotency_key": str(uuid.uuid4()),
                    "source": "DAPP",
                    "event": "STATUS_UPDATE",
                    "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "token": service_token.token
                },
                "payload": {
                    "reference": transaction.reference,
                    "status": "FULFILLED",
                    "message": "Transaction has been executed on chain successfully"
                }
            }

            # Send message to status update queue
            self.logger.info(
                f"Sending status update for [{transaction.reference}] to queue: {self.status_update_queue_name}"
            )

            response = self.message_bus.send_message(
                status_update_message,
                self.status_update_queue_name,
                "DAPP"
            )

            self.logger.info(
                f"Status update sent for [{transaction.reference}]: Message ID: {response.get('MessageId')}"
            )

        except ValueError as e:
            # ValueError indicates a configuration or authentication issue (missing identity service or token)
            # These are critical errors that should fail the transaction processing
            self.logger.exception(
                f"Critical error sending status update for [{transaction.reference}]: {e}"
            )
            raise
        except Exception as e:
            # Other exceptions (network errors, etc.) shouldn't fail the transaction processing
            self.logger.exception(
                f"Error sending status update for [{transaction.reference}]: {e}"
            )
            # Don't raise - non-critical status update failures shouldn't fail the transaction processing


def create_processor(env: str = 'development') -> TransactionProcessor:
    """
    Create and initialize a transaction processor.

    Args:
        env: Environment name (development, production)

    Returns:
        TransactionProcessor instance
    """
    from app import create_app

    # Create Flask app
    app = create_app(env)

    # Create processor
    with app.app_context():
        processor = TransactionProcessor(app)
        return processor


if __name__ == '__main__':
    """
    Run the transaction processor as a standalone process.

    Usage:
        ENV=development python -m app.transaction_processor
        ENV=production python -m app.transaction_processor
    """
    import os

    env = os.getenv('ENV', 'development')
    print(f"Starting Transaction Processor in {env} mode...")

    processor = create_processor(env)
    processor.start()
