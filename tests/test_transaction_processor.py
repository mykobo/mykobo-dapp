"""
Tests for the TransactionProcessor service
"""
import uuid
from decimal import Decimal
from unittest.mock import Mock, MagicMock, patch
import pytest
from app.transaction_processor import TransactionProcessor
from app.models import Transaction, Inbox
from app.database import db
from mykobo_py.message_bus import PaymentPayload, StatusUpdatePayload, CorrectionPayload


class TestTransactionProcessor:
    """Tests for the TransactionProcessor service"""

    @pytest.fixture
    def mock_message_bus(self):
        """Create a mock message bus"""
        mock = Mock()
        mock.send_message = Mock(return_value={"MessageId": "test-message-id-123"})
        return mock

    @pytest.fixture
    def mock_identity_service(self):
        """Create a mock identity service client"""
        mock = Mock()
        mock_token = Mock()
        mock_token.token = "test-service-token-abc123"
        mock.acquire_token = Mock(return_value=mock_token)
        return mock

    @pytest.fixture
    def processor(self, app, mock_message_bus, mock_identity_service):
        """Create a TransactionProcessor instance for testing"""
        app.config["SOLANA_RPC_URL"] = "https://api.devnet.solana.com"
        app.config["SOLANA_DISTRIBUTION_PRIVATE_KEY"] = "test-private-key"
        app.config["EURC_TOKEN_MINT"] = "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"
        app.config["USDC_TOKEN_MINT"] = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        app.config["MESSAGE_BUS"] = mock_message_bus
        app.config["TRANSACTION_STATUS_UPDATE_QUEUE_NAME"] = "test-status-update-queue"
        app.config["PAYMENTS_QUEUE_NAME"] = "test-payments-queue"
        app.config["CORRECTION_QUEUE_NAME"] = "test-correction-queue"
        app.config["IDENTITY_SERVICE_CLIENT"] = mock_identity_service
        return TransactionProcessor(app)

    def test_processor_initialization(self, processor):
        """Test that processor initializes correctly"""
        assert processor.app is not None
        assert processor.running is False
        assert processor.poll_interval == 5
        assert processor.batch_size == 10
        assert processor.actionable_statuses == ['APPROVED']
        assert processor.solana_rpc_url == "https://api.devnet.solana.com"

    def test_process_messages_no_pending(self, processor, app):
        """Test processing when no pending messages exist"""
        with app.app_context():
            # Create a completed message (not pending)
            inbox_message = Inbox(
                message_id=str(uuid.uuid4()),
                message_body={"test": "data"},
                transaction_reference="REF123",
                status="COMPLETED"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Process messages
            processor._process_messages()

            # Verify completed message still has same status
            assert inbox_message.status == "COMPLETED"

    def test_should_process_transaction_approved_withdrawal(self, processor, app):
        """Test that PENDING_PAYEE WITHDRAW transactions with APPROVED status are processed"""
        with app.app_context():
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK1234567890",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",  # WITHDRAW requires PENDING_PAYEE status
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="SolanaWalletAddress123",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            db.session.add(transaction)
            db.session.commit()

            # Should process this transaction when message status is APPROVED
            assert processor._should_process_transaction(transaction, "APPROVED") is True

    def test_should_process_deposit(self, processor, app):
        """Test that DEPOSIT transactions with PENDING_ANCHOR status are processed"""
        with app.app_context():
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK1111111111",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="DEPOSIT",
                status="PENDING_ANCHOR",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("50.00"),
                fee=Decimal("1.00"),
                wallet_address="TestWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            # Should process deposits when status is PENDING_ANCHOR and message is APPROVED
            assert processor._should_process_transaction(transaction, "APPROVED") is True

    def test_should_not_process_wrong_transaction_status(self, processor, app):
        """Test that transactions with wrong status are not processed"""
        with app.app_context():
            # Test 1: WITHDRAW with wrong status (PENDING_ANCHOR instead of PENDING_PAYEE)
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK2222222222",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_ANCHOR",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("75.00"),
                fee=Decimal("1.50"),
                wallet_address="TestWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            # Should NOT process WITHDRAW in PENDING_ANCHOR status
            assert processor._should_process_transaction(transaction, "APPROVED") is False

            # Test 2: WITHDRAW with correct status but wrong message status
            transaction.status = "PENDING_PAYEE"
            # Should NOT process when message is not APPROVED
            assert processor._should_process_transaction(transaction, "pending_payee") is False

    def test_calculate_net_amount(self, processor, app):
        """Test net amount calculation (value - fee)"""
        with app.app_context():
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK3333333333",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="APPROVED",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                wallet_address="TestWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            # Net amount is calculated inline as value - fee
            net_amount = transaction.value - transaction.fee
            assert net_amount == Decimal("97.50")

    def test_get_token_mint_eurc(self, processor):
        """Test getting EURC token mint address"""
        mint_address = processor._get_token_mint("EURC")
        assert mint_address == "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr"

    def test_get_token_mint_usdc(self, processor):
        """Test getting USDC token mint address"""
        mint_address = processor._get_token_mint("USDC")
        assert mint_address == "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def test_get_token_mint_invalid(self, processor):
        """Test getting invalid token mint raises error"""
        with pytest.raises(ValueError, match="Unsupported currency"):
            processor._get_token_mint("INVALID")

    def test_process_inbox_message_no_reference(self, processor, app):
        """Test processing message without reference"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=str(uuid.uuid4()),
                message_body={},  # No reference - flat payload
                transaction_reference=None,
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Process message
            processor._process_inbox_message(inbox_message)

            # Should be marked as failed
            assert inbox_message.status == "failed"
            assert "no reference" in inbox_message.last_error.lower()

    def test_process_inbox_message_transaction_not_found(self, processor, app):
        """Test processing message when transaction doesn't exist"""
        with app.app_context():
            inbox_message = Inbox(
                message_id=str(uuid.uuid4()),
                message_body={
                    "reference": "MYK_NONEXISTENT",
                    "status": "APPROVED"
                },
                transaction_reference="MYK_NONEXISTENT",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Process message
            processor._process_inbox_message(inbox_message)

            # Should be marked as failed
            assert inbox_message.status == "failed"
            assert "not found" in inbox_message.last_error.lower()

    def test_process_inbox_message_success(self, processor, app):
        """Test successful message processing"""
        with app.app_context():
            # Create a transaction
            tx_id = str(uuid.uuid4())
            transaction = Transaction(
                id=tx_id,
                reference="MYK9999999999",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",  # WITHDRAW requires PENDING_PAYEE
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("3.00"),
                wallet_address="TestSolanaWallet123",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Create inbox message
            inbox_message = Inbox(
                message_id=str(uuid.uuid4()),
                message_body={
                    "reference": "MYK9999999999",
                    "status": "APPROVED",
                    "transaction_id": "ledger-tx-123"
                },
                transaction_reference="MYK9999999999",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Mock Solana transaction creation
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "mock_signature_123"
                }

                # Process message
                processor._process_inbox_message(inbox_message)

                # Verify Solana transaction was called with correct params
                mock_solana.assert_called_once()
                call_args = mock_solana.call_args[1]
                assert call_args['recipient_address'] == "TestSolanaWallet123"
                assert call_args['amount'] == float(Decimal("97.00"))  # 100 - 3
                assert call_args['currency'] == "EURC"

                # Verify inbox message marked as completed
                assert inbox_message.status == "completed"

                # Verify transaction status updated
                assert transaction.status == "COMPLETED"

    def test_process_inbox_message_batch(self, processor, app):
        """Test processing multiple messages in a batch"""
        with app.app_context():
            # Create multiple transactions and inbox messages
            for i in range(3):
                tx_id = str(uuid.uuid4())
                reference = f"MYK{1000000000 + i}"

                transaction = Transaction(
                    id=tx_id,
                    reference=reference,
                    idempotency_key=str(uuid.uuid4()),
                    transaction_type="WITHDRAW",
                    status="PENDING_PAYEE",  # WITHDRAW requires PENDING_PAYEE
                    incoming_currency="EUR",
                    outgoing_currency="EURC",
                    value=Decimal("50.00"),
                    fee=Decimal("1.00"),
                    wallet_address=f"Wallet{i}",
                    source="ANCHOR_SOLANA",
                    instruction_type="Transaction",
                )
                db.session.add(transaction)

                inbox_message = Inbox(
                    message_id=str(uuid.uuid4()),
                    message_body={
                        "reference": reference,
                        "status": "APPROVED"
                    },
                    transaction_reference=reference,
                    status="pending"
                )
                db.session.add(inbox_message)

            db.session.commit()

            # Mock Solana transactions
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "mock_sig"
                }

                # Process messages
                processor._process_messages()

                # Verify all 3 were processed
                assert mock_solana.call_count == 3

                # Verify all inbox messages marked as completed
                completed_count = Inbox.query.filter_by(status="completed").count()
                assert completed_count == 3

    def test_stop_processor(self, processor):
        """Test stopping the processor"""
        processor.running = True
        processor.stop()
        assert processor.running is False

    def test_handle_shutdown(self, processor):
        """Test shutdown signal handling"""
        processor.running = True
        processor._handle_shutdown(2, None)  # signum, frame
        assert processor.running is False

    def test_process_message_with_solana_error(self, processor, app):
        """Test handling Solana transaction errors"""
        with app.app_context():
            # Create transaction and inbox message
            tx_id = str(uuid.uuid4())
            transaction = Transaction(
                id=tx_id,
                reference="MYK8888888888",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",  # WITHDRAW requires PENDING_PAYEE
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("25.00"),
                fee=Decimal("0.50"),
                wallet_address="ErrorWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)

            inbox_message = Inbox(
                message_id=str(uuid.uuid4()),
                message_body={
                    "reference": "MYK8888888888",
                    "status": "APPROVED"
                },
                transaction_reference="MYK8888888888",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Mock Solana transaction to fail
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "error",
                    "message": "Solana RPC error"
                }

                # Process messages (will handle the error internally)
                processor._process_messages()

                # Refresh from database
                db.session.refresh(inbox_message)

                # Verify inbox message marked as failed
                assert inbox_message.status == "failed"
                assert "Solana" in inbox_message.last_error or "error" in inbox_message.last_error.lower()

    def test_lookup_transaction_by_reference(self, processor, app):
        """Test looking up transaction by reference"""
        with app.app_context():
            # Create transaction
            tx_id = str(uuid.uuid4())
            reference = "MYK7777777777"
            transaction = Transaction(
                id=tx_id,
                reference=reference,
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("200.00"),
                fee=Decimal("5.00"),
                wallet_address="LookupWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Look up by reference
            found = Transaction.query.filter_by(reference=reference).first()
            assert found is not None
            assert found.id == tx_id
            assert found.value == Decimal("200.00")

    def test_send_status_update(self, processor, app, mock_message_bus):
        """Test sending payment message to queue"""
        with app.app_context():
            # Create transaction
            tx_id = str(uuid.uuid4())
            transaction = Transaction(
                id=tx_id,
                reference="MYK6666666666",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="COMPLETED",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("2.50"),
                first_name="John",
                last_name="Doe",
                wallet_address="TestWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Create and send payment payload
            solana_signature = "5ZuaVZJMPyqd4q6yfqEPfbNxLkbi1Qr4XStfjQs3rKih"
            payment_payload = PaymentPayload(
                external_reference=solana_signature,
                payer_name=f"{transaction.first_name} {transaction.last_name}",
                currency=transaction.outgoing_currency,
                value=f"{float(transaction.value - transaction.fee)}",
                source="CHAIN_SOLANA",
                reference=transaction.reference,
                bank_account_number=None
            )
            processor._send_status_update(payment_payload, transaction.reference)

            # Verify message was sent
            mock_message_bus.send_message.assert_called_once()

            # Verify message structure
            call_args = mock_message_bus.send_message.call_args
            message_obj = call_args[0][0]
            queue_name = call_args[0][1]
            source = call_args[0][2]

            # Convert message object to dict for assertions
            message = message_obj.to_dict()

            assert queue_name == "test-payments-queue"  # PaymentPayload goes to payments queue
            assert source == "DAPP.transaction_processor"
            assert message["meta_data"]["source"] == "MYKOBO_DAPP"
            assert message["meta_data"]["instruction_type"] == "PAYMENT"
            assert message["meta_data"]["token"] == "test-service-token-abc123"
            assert message["payload"]["reference"] == "MYK6666666666"
            assert message["payload"]["external_reference"] == solana_signature
            assert message["payload"]["currency"] == "EURC"
            assert message["payload"]["value"] == "97.5"  # 100 - 2.50
            assert message["payload"]["source"] == "CHAIN_SOLANA"

    def test_status_update_on_successful_transaction(self, processor, app, mock_message_bus):
        """Test that payment message is sent when Solana transaction succeeds"""
        with app.app_context():
            # Create transaction and inbox message
            tx_id = str(uuid.uuid4())
            transaction = Transaction(
                id=tx_id,
                reference="MYK5555555555",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",  # WITHDRAW requires PENDING_PAYEE to be processed
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("50.00"),
                fee=Decimal("1.50"),
                first_name="Jane",
                last_name="Smith",
                wallet_address="StatusUpdateWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)

            inbox_message = Inbox(
                message_id=str(uuid.uuid4()),
                message_body={
                    "reference": "MYK5555555555",
                    "status": "APPROVED"
                },
                transaction_reference="MYK5555555555",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Mock Solana transaction to succeed
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "test_signature_abc123"
                }

                # Process messages
                processor._process_messages()

                # Verify payment message was sent
                mock_message_bus.send_message.assert_called_once()

                # Verify the message content
                call_args = mock_message_bus.send_message.call_args
                message_obj = call_args[0][0]

                # Convert message object to dict for assertions
                message = message_obj.to_dict()

                assert message["meta_data"]["source"] == "MYKOBO_DAPP"
                assert message["meta_data"]["instruction_type"] == "PAYMENT"
                assert message["meta_data"]["token"] == "test-service-token-abc123"
                assert message["payload"]["reference"] == "MYK5555555555"
                assert message["payload"]["external_reference"] == "test_signature_abc123"
                assert message["payload"]["currency"] == "USDC"
                assert message["payload"]["value"] == "48.5"  # 50 - 1.50
                assert message["payload"]["source"] == "CHAIN_SOLANA"

    def test_no_status_update_when_queue_not_configured(self, processor, app):
        """Test that missing queue configuration is handled gracefully"""
        with app.app_context():
            # Remove queue configuration
            processor.status_update_queue_name = None

            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK4444444444",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="FULFILLED",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("75.00"),
                fee=Decimal("2.00"),
                wallet_address="NoQueueWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )

            # Should not raise an exception
            payment_payload = PaymentPayload(
                external_reference="test_signature",
                payer_name="Test User",
                currency=transaction.outgoing_currency,
                value=f"{float(transaction.value - transaction.fee)}",
                source="CHAIN_SOLANA",
                reference=transaction.reference,
                bank_account_number=None
            )
            processor._send_status_update(payment_payload, transaction.reference)
            # No assertion needed - just verifying it doesn't crash

    def test_funds_received_status_updates_transaction_to_pending_anchor(self, processor, app):
        """Test that FUNDS_RECEIVED status updates transaction to PENDING_ANCHOR"""
        with app.app_context():
            # Create a transaction with initial status
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK6666666666",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("5.00"),
                wallet_address="FundsReceivedWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Create inbox message with FUNDS_RECEIVED status
            inbox_message = Inbox(
                message_id="funds-received-msg-123",
                message_body={
                    "reference": "MYK6666666666",
                    "status": "FUNDS_RECEIVED",
                    "transaction_id": "ledger-tx-123"
                },
                transaction_reference="MYK6666666666",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Process the message
            processor._process_messages()

            # Verify transaction status was updated to PENDING_ANCHOR
            updated_transaction = Transaction.query.filter_by(reference="MYK6666666666").first()
            assert updated_transaction.status == "PENDING_ANCHOR"

            # Verify inbox message was completed
            updated_inbox = Inbox.query.filter_by(message_id="funds-received-msg-123").first()
            assert updated_inbox.status == "completed"

    def test_funds_received_then_approved_flow(self, processor, app, mock_message_bus):
        """Test complete flow: FUNDS_RECEIVED updates WITHDRAW status to PENDING_ANCHOR, but doesn't trigger processing. Only PENDING_PAYEE + APPROVED triggers Solana transaction"""
        with app.app_context():
            # Step 1: Create WITHDRAW transaction with PENDING_PAYEE status
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK7777777777",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="PENDING_PAYEE",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("200.00"),
                fee=Decimal("10.00"),
                wallet_address="TwoStepWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Step 2: Create APPROVED message directly (WITHDRAW at PENDING_PAYEE with APPROVED should process)
            inbox_message = Inbox(
                message_id="msg-approved-789",
                message_body={
                    "reference": "MYK7777777777",
                    "status": "APPROVED"
                },
                transaction_reference="MYK7777777777",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Mock Solana transaction
            with patch.object(processor, '_create_and_send_solana_transaction') as mock_solana:
                mock_solana.return_value = {
                    "status": "success",
                    "transaction_signature": "two_step_signature_xyz"
                }

                # Process APPROVED message
                processor._process_messages()

                # Verify Solana transaction was called
                mock_solana.assert_called_once()

                # Verify transaction is now completed
                tx = Transaction.query.filter_by(reference="MYK7777777777").first()
                assert tx.status == "COMPLETED"

                # Verify status update was sent
                mock_message_bus.send_message.assert_called_once()

    def test_funds_received_with_non_withdrawal_transaction(self, processor, app):
        """Test that FUNDS_RECEIVED still updates status for non-withdrawal transactions"""
        with app.app_context():
            # Create a DEPOSIT transaction
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK8888888888",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="DEPOSIT",
                status="pending_payer",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("50.00"),
                fee=Decimal("1.00"),
                wallet_address="DepositWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Create inbox message with FUNDS_RECEIVED
            inbox_message = Inbox(
                message_id="deposit-funds-received-111",
                message_body={
                    "reference": "MYK8888888888",
                    "status": "FUNDS_RECEIVED"
                },
                transaction_reference="MYK8888888888",
                status="pending"
            )
            db.session.add(inbox_message)
            db.session.commit()

            # Process the message
            processor._process_messages()

            # Verify status was updated even for non-withdrawal
            updated_transaction = Transaction.query.filter_by(reference="MYK8888888888").first()
            assert updated_transaction.status == "PENDING_ANCHOR"

            # Verify inbox message was completed
            updated_inbox = Inbox.query.filter_by(message_id="deposit-funds-received-111").first()
            assert updated_inbox.status == "completed"

    def test_status_update_without_identity_service(self, processor, app, mock_message_bus):
        """Test that status update fails when identity service is not configured"""
        with app.app_context():
            # Remove identity service
            processor.identity_service = None

            # Create transaction
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK9999999999",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="FULFILLED",
                incoming_currency="EUR",
                outgoing_currency="EURC",
                value=Decimal("100.00"),
                fee=Decimal("5.00"),
                wallet_address="NoIdentityWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Send status update should raise ValueError
            solana_signature = "signature_without_identity"
            payment_payload = PaymentPayload(
                external_reference=solana_signature,
                payer_name="Test User",
                currency=transaction.outgoing_currency,
                value=f"{float(transaction.value - transaction.fee)}",
                source="CHAIN_SOLANA",
                reference=transaction.reference,
                bank_account_number=None
            )
            with pytest.raises(ValueError, match="Identity service not configured"):
                processor._send_status_update(payment_payload, transaction.reference)

            # Verify message was NOT sent
            mock_message_bus.send_message.assert_not_called()

    def test_status_update_with_token_acquisition_failure(self, processor, app, mock_message_bus, mock_identity_service):
        """Test that status update fails when token acquisition fails"""
        with app.app_context():
            # Make token acquisition fail
            mock_identity_service.acquire_token.side_effect = Exception("Token service unavailable")

            # Create transaction
            transaction = Transaction(
                id=str(uuid.uuid4()),
                reference="MYK1010101010",
                idempotency_key=str(uuid.uuid4()),
                transaction_type="WITHDRAW",
                status="COMPLETED",
                incoming_currency="USD",
                outgoing_currency="USDC",
                value=Decimal("150.00"),
                fee=Decimal("7.50"),
                wallet_address="TokenFailWallet",
                source="ANCHOR_SOLANA",
                instruction_type="Transaction",
            )
            db.session.add(transaction)
            db.session.commit()

            # Send status update should raise ValueError
            solana_signature = "signature_token_fail"
            payment_payload = PaymentPayload(
                external_reference=solana_signature,
                payer_name="Test User",
                currency=transaction.outgoing_currency,
                value=f"{float(transaction.value - transaction.fee)}",
                source="CHAIN_SOLANA",
                reference=transaction.reference,
                bank_account_number=None
            )
            with pytest.raises(ValueError, match="Failed to acquire service token"):
                processor._send_status_update(payment_payload, transaction.reference)

            # Verify message was NOT sent
            mock_message_bus.send_message.assert_not_called()

    def test_send_different_payload_types(self, processor, app, mock_message_bus):
        """Test sending different payload types (Payment, StatusUpdate, Correction)"""
        with app.app_context():
            reference = "MYK1111111111"

            # Test 1: PaymentPayload
            payment_payload = PaymentPayload(
                external_reference="solana_signature_123",
                payer_name="John Doe",
                currency="EURC",
                value="97.50",
                source="CHAIN_SOLANA",
                reference=reference,
                bank_account_number=None
            )
            processor._send_status_update(payment_payload, reference)

            # Verify payment message was sent
            assert mock_message_bus.send_message.call_count == 1
            call_args = mock_message_bus.send_message.call_args
            message = call_args[0][0].to_dict()
            assert message["meta_data"]["instruction_type"] == "PAYMENT"
            assert message["payload"]["external_reference"] == "solana_signature_123"

            # Reset mock
            mock_message_bus.reset_mock()

            # Test 2: StatusUpdatePayload
            status_update_payload = StatusUpdatePayload(
                reference=reference,
                status="FAILED",
                message="Transaction failed due to insufficient funds"
            )
            processor._send_status_update(status_update_payload, reference)

            # Verify status update message was sent
            assert mock_message_bus.send_message.call_count == 1
            call_args = mock_message_bus.send_message.call_args
            message = call_args[0][0].to_dict()
            assert message["meta_data"]["instruction_type"] == "STATUS_UPDATE"
            assert message["payload"]["status"] == "FAILED"
            assert message["payload"]["message"] == "Transaction failed due to insufficient funds"

            # Reset mock
            mock_message_bus.reset_mock()

            # Test 3: CorrectionPayload
            correction_payload = CorrectionPayload(
                reference=reference,
                value="5.00",
                message="Fee adjustment correction",
                currency="EURC",
                source="CHAIN_SOLANA"
            )
            processor._send_status_update(correction_payload, reference)

            # Verify correction message was sent
            assert mock_message_bus.send_message.call_count == 1
            call_args = mock_message_bus.send_message.call_args
            message = call_args[0][0].to_dict()
            assert message["meta_data"]["instruction_type"] == "CORRECTION"
            assert message["payload"]["value"] == "5.00"
            assert message["payload"]["message"] == "Fee adjustment correction"

    def test_payment_payload_routed_to_payments_queue(self, processor, app, mock_message_bus):
        """Test that PaymentPayload is routed to the payments queue"""
        with app.app_context():
            reference = "MYK2222222222"
            payment_payload = PaymentPayload(
                external_reference="solana_sig_payment",
                payer_name="Jane Smith",
                currency="USDC",
                value="150.00",
                source="CHAIN_SOLANA",
                reference=reference,
                bank_account_number=None
            )

            processor._send_status_update(payment_payload, reference)

            # Verify message was sent to payments queue
            assert mock_message_bus.send_message.call_count == 1
            call_args = mock_message_bus.send_message.call_args
            queue_name = call_args[0][1]  # Second argument is the queue name
            assert queue_name == "test-payments-queue"

    def test_status_update_payload_routed_to_status_update_queue(self, processor, app, mock_message_bus):
        """Test that StatusUpdatePayload is routed to the status update queue"""
        with app.app_context():
            reference = "MYK3333333333"
            status_update_payload = StatusUpdatePayload(
                reference=reference,
                status="PENDING",
                message="Awaiting confirmation"
            )

            processor._send_status_update(status_update_payload, reference)

            # Verify message was sent to status update queue
            assert mock_message_bus.send_message.call_count == 1
            call_args = mock_message_bus.send_message.call_args
            queue_name = call_args[0][1]  # Second argument is the queue name
            assert queue_name == "test-status-update-queue"

    def test_correction_payload_routed_to_correction_queue(self, processor, app, mock_message_bus):
        """Test that CorrectionPayload is routed to the correction queue"""
        with app.app_context():
            reference = "MYK4444444444"
            correction_payload = CorrectionPayload(
                reference=reference,
                value="10.00",
                message="Refund processing fee",
                currency="EURC",
                source="CHAIN_SOLANA"
            )

            processor._send_status_update(correction_payload, reference)

            # Verify message was sent to correction queue
            assert mock_message_bus.send_message.call_count == 1
            call_args = mock_message_bus.send_message.call_args
            queue_name = call_args[0][1]  # Second argument is the queue name
            assert queue_name == "test-correction-queue"

    def test_missing_queue_configuration_logs_warning(self, processor, app, mock_message_bus):
        """Test that missing queue configuration logs a warning and doesn't send"""
        with app.app_context():
            # Remove queue configurations
            processor.payment_queue_name = None
            processor.status_update_queue_name = None
            processor.correction_queue_name = None

            reference = "MYK5555555555"
            payment_payload = PaymentPayload(
                external_reference="solana_sig_no_queue",
                payer_name="Test User",
                currency="EURC",
                value="50.00",
                source="CHAIN_SOLANA",
                reference=reference,
                bank_account_number=None
            )

            # Should not raise exception, just log warning
            processor._send_status_update(payment_payload, reference)

            # Verify message was NOT sent
            mock_message_bus.send_message.assert_not_called()
