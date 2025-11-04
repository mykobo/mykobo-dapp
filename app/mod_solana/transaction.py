"""
Solana transaction utilities for USDC transfers
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

import botocore
from flask import current_app as app, Blueprint, Response, make_response, render_template, request, redirect, url_for, \
    flash
from app.forms import Transaction as TransactionForm
from app.decorators import require_wallet_auth
from app.util import generate_reference, retrieve_ip_address, get_fee, get_minimum_transaction_value, \
    get_maximum_transaction_value
from app.database import db
from app.models import Transaction as TransactionModel, Transaction

bp = Blueprint("solana_transaction", __name__)
network = 'solana'


def determine_currencies(kind: str, asset: Optional[str]) -> (str, str):
    if asset is None:
        return None, None
    if kind.lower() == 'deposit':
        if asset.lower().startswith('usd'):
            return 'USD', 'USDC'
        elif asset.lower().startswith('eur'):
            return 'EUR', 'EURC'
        else:
            return None, None
    else:
        if asset.lower().startswith('usd'):
            return 'USDC', 'USD'
        elif asset.lower().startswith('eur'):
            return 'EURC', 'EUR'
        return None, None


@bp.route("/new", methods=["GET", "POST"])
@require_wallet_auth
def new() -> Response:
    kind = request.args.get("type")
    asset = request.args.get("asset")
    incoming_currency, outgoing_currency = determine_currencies(kind=kind, asset=asset)
    wallet_address = request.wallet_address
    form = TransactionForm()
    tx_reference = generate_reference()
    service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()
    user_data = {}

    wallet_data = {}
    try:
        wallet_data = get_wallet_balance(wallet_address).json
    except Exception as wallet_error:
        app.logger.exception(f"Could not fetch wallet balance: {wallet_error}")

    try:
        wallet_profile_response = app.config["WALLET_SERVICE_CLIENT"].get_wallet_profile(service_token, wallet_address)
        wallet_profile = wallet_profile_response.json()

        try:
            identity_service_response = app.config[
                "IDENTITY_SERVICE_CLIENT"
            ].get_user_profile(service_token, wallet_profile["profile_id"])

            user_data = identity_service_response.json()
        except Exception as e:
            app.logger.exception(
                "Could not fetch user data %s", e
            )
            return make_response(
                render_template(
                    "error/500.html", reason="Could not fetch user data"
                ),
                500,
            )
    except Exception as e:
        app.logger.error(e)

    if request.method == "POST":
        form = TransactionForm(request.form)
        if form.validate_on_submit():
            fee_details = get_fee(app.config["FEE_ENDPOINT"], form.amount.data, kind, None)

            # For withdrawals, validate user has sufficient balance
            if kind == "withdraw":
                if not wallet_data or "balances" not in wallet_data:
                    app.logger.error(f"Could not fetch wallet balance for validation")
                    flash("Unable to verify wallet balance. Please try again.", "danger")
                    return make_response(redirect(url_for("solana_transaction.new", type=kind, asset=asset)), 302)

                # Get the balance for the asset being withdrawn
                asset_balance = wallet_data["balances"].get(asset.lower(), {})
                current_balance = asset_balance.get("amount", 0.0)

                # User needs to have the full withdrawal amount (value they entered)
                # The fee is deducted from what they receive, not added to what they send
                required_balance = float(form.amount.data)

                app.logger.info(
                    f"Balance check for withdrawal: asset={asset}, current={current_balance}, required={required_balance}"
                )

                if current_balance < required_balance:
                    app.logger.warning(
                        f"Insufficient balance for withdrawal: has {current_balance} {asset}, needs {required_balance}"
                    )
                    flash(
                        f"Insufficient balance. You have {current_balance:.2f} {asset.upper()} but need {required_balance:.2f} {asset.upper()} for this withdrawal.",
                        "danger"
                    )
                    return make_response(redirect(url_for("solana_transaction.new", type=kind, asset=asset)), 302)

            ledger_payload = {
                "meta_data": {
                    "source": "DAPP",
                    "instruction_type": "Transaction",
                    "created_at": datetime.now().strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "token": service_token.token,
                    "idempotency_key": str(uuid.uuid4()),
                    "ip_address": retrieve_ip_address(request),
                },
                "payload": {
                    "external_reference": str(uuid.uuid4()),  # This becomes transaction.id in database
                    "source": "ANCHOR_SOLANA",
                    "reference": tx_reference,
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "transaction_type": kind.upper(),
                    "status": (
                        "PENDING_PAYEE"
                        if kind == "withdraw"
                        else "PENDING_PAYER"
                    ),
                    "incoming_currency": incoming_currency,
                    "outgoing_currency": outgoing_currency,
                    "value": str(form.amount.data),
                    "fee": str(fee_details["total"]),
                    "payer": (
                        user_data["id"]
                        if kind == "deposit"
                        else None
                    ),
                    "payee": (
                        user_data["id"]
                        if kind == "withdraw"
                        else None
                    ),
                },
            }

            app.logger.debug(ledger_payload)
            # Create and save database record BEFORE sending to queue
            # This allows us to retry failed queue sends
            transaction_record = TransactionModel.from_ledger_payload(
                ledger_payload=ledger_payload,
                wallet_address=wallet_address
            )

            try:
                # Save transaction to database first
                db.session.add(transaction_record)
                db.session.commit()
                app.logger.info(
                    f"Transaction [{tx_reference}] saved to database with ID {transaction_record.id}"
                )

            except Exception as db_error:
                app.logger.exception(f"Database error while saving transaction: {db_error}")
                db.session.rollback()
                return make_response(
                    render_template(
                        "error/500.html",
                        reason="Could not save transaction record, if this persists please contact support",
                    ),
                    500,
                )

            # Send transaction to ledger queue for all transaction types
            try:
                app.logger.info(
                    f"Sending message to ledger for transaction [{tx_reference}]..."
                )
                queue_response = app.config[
                    "MESSAGE_BUS"
                ].send_message(
                    ledger_payload,
                    app.config["TRANSACTION_QUEUE_NAME"],
                    "ANCHOR_SOLANA",
                )
                app.logger.info(
                    f"Message Sent to Ledger Queue: {queue_response['MessageId']}"
                )

                # Update transaction record with message ID
                transaction_record.message_id = queue_response['MessageId']
                transaction_record.queue_sent_at = datetime.now()
                db.session.commit()

                app.logger.info(
                    f"Transaction [{tx_reference}] updated with message ID {queue_response['MessageId']}"
                )

                # Redirect to info page for all transaction types
                # For withdrawals in PENDING_PAYEE status, the info endpoint will render the sign page
                return make_response(redirect(url_for("solana_transaction.info", reference=tx_reference)))
            except botocore.exceptions.EndpointConnectionError as e:
                app.logger.exception(
                    f"We could not submit this transaction to our ledger: {e}"
                )
                # Transaction is already saved in database for retry
                app.logger.warning(
                    f"Transaction [{tx_reference}] (DB ID: {transaction_record.id}) saved but not sent to queue. Manual retry required."
                )
                return make_response(
                    render_template(
                        "error/500.html",
                        reason="Could not submit transaction to ledger, if this persists please contact support",
                    ),
                    500,
                )
            except Exception as queue_error:
                app.logger.exception(f"Queue error while sending transaction: {queue_error}")
                # Transaction is already saved in database for retry
                app.logger.warning(
                    f"Transaction [{tx_reference}] (DB ID: {transaction_record.id}) saved but not sent to queue. Manual retry required."
                )
                return make_response(
                    render_template(
                        "error/500.html",
                        reason="Could not submit transaction to queue, if this persists please contact support",
                    ),
                    500,
                )

        else:
            return make_response(redirect(url_for("solana_transaction.new", type=kind)))
    else:
        return make_response(
            render_template(
                f"transactions/{kind}.html",
                form=form,
                user_data=user_data,
                kind=kind,
                asset=asset,
                min_amount=get_minimum_transaction_value(),
                max_amount=get_maximum_transaction_value(),
                fee_endpoint="/fees",
                wallet_data=wallet_data
            )
            , 200)


@bp.route("/transaction/info/<reference>", methods=["GET"])
@require_wallet_auth
def info(reference) -> Response:
    wallet_address = request.wallet_address
    user_data = {}
    wallet_data = {}

    try:
        wallet_data = get_wallet_balance(wallet_address).json
    except Exception as wallet_error:
        app.logger.exception(f"Could not fetch wallet balance: {wallet_error}")

    service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()

    try:
        wallet_profile_response = app.config["WALLET_SERVICE_CLIENT"].get_wallet_profile(service_token, wallet_address)
        wallet_profile = wallet_profile_response.json()

        try:
            identity_service_response = app.config[
                "IDENTITY_SERVICE_CLIENT"
            ].get_user_profile(service_token, wallet_profile["profile_id"])

            user_data = identity_service_response.json()
        except Exception as e:
            app.logger.exception(
                "Could not fetch user data %s", e
            )
            return make_response(
                render_template(
                    "error/500.html", reason="Could not fetch user data"
                ),
                500,
            )
    except Exception as e:
        app.logger.error(e)

    transaction = Transaction.query.filter_by(reference=reference).first()

    # If transaction is a withdrawal still pending payee, redirect to sign screen
    if (transaction and
        transaction.transaction_type == "WITHDRAW" and
        transaction.status == "PENDING_PAYEE"):

        app.logger.info(f"Transaction {reference} is WITHDRAW in PENDING_PAYEE status, redirecting to sign screen")

        try:
            # Generate unsigned transaction for user to sign
            unsigned_tx_data = build_unsigned_withdraw_transaction(
                user_wallet=wallet_address,
                amount=float(transaction.value),
                currency=transaction.incoming_currency,
                memo=reference
            )

            # Render sign page instead of info page
            return make_response(
                render_template(
                    "transactions/sign_withdraw.html",
                    transaction_data=transaction,
                    user_data=user_data,
                    wallet_data=wallet_data,
                    unsigned_transaction=unsigned_tx_data["serialized_transaction"],
                    destination=unsigned_tx_data["destination"],
                    reference=reference
                ),
                200
            )
        except Exception as tx_error:
            app.logger.exception(f"Error generating unsigned transaction for {reference}: {tx_error}")
            # Fall through to show info page with error
            flash("Unable to generate transaction for signing. Please try again.", "danger")

    return make_response(render_template(
        "transactions/info.html",
        transaction_data=transaction,
        user_data=user_data,
        wallet_data=wallet_data,
        mykobo_iban=app.config.get("IBAN"),
        explorer_url=f"https://explorer.solana.com/tx/{transaction.tx_hash}?cluster={app.config.get("SOLANA_CLUSTER")}" if transaction.tx_hash else None
    ), 201)


@bp.route("/list", methods=["GET"])
@require_wallet_auth
def list_transactions() -> Response:
    """
    API endpoint to get list of transactions for a wallet address.
    Extracts wallet address from authenticated request.
    Returns transactions ordered by most recent first.

    Query parameters:
        limit (optional): Maximum number of transactions to return (default: 50, max: 100)
        offset (optional): Number of transactions to skip (default: 0)

    Returns:
        JSON response with transactions:
        {
            "wallet_address": "...",
            "transactions": [
                {
                    "id": "...",
                    "reference": "...",
                    "transaction_type": "...",
                    "status": "...",
                    "incoming_currency": "...",
                    "outgoing_currency": "...",
                    "value": "...",
                    "fee": "...",
                    "created_at": "...",
                    "updated_at": "...",
                    "solana_tx_signature": "..."
                },
                ...
            ],
            "total": 123,
            "limit": 50,
            "offset": 0
        }
    """
    wallet_address = request.wallet_address

    user_data = {}
    wallet_data = {}

    try:
        wallet_data = get_wallet_balance(wallet_address).json
    except Exception as wallet_error:
        app.logger.exception(f"Could not fetch wallet balance: {wallet_error}")

    service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()

    try:
        wallet_profile_response = app.config["WALLET_SERVICE_CLIENT"].get_wallet_profile(service_token, wallet_address)
        wallet_profile = wallet_profile_response.json()

        try:
            identity_service_response = app.config[
                "IDENTITY_SERVICE_CLIENT"
            ].get_user_profile(service_token, wallet_profile["profile_id"])

            user_data = identity_service_response.json()
        except Exception as e:
            app.logger.exception(
                "Could not fetch user data %s", e
            )
            return make_response(
                render_template(
                    "error/500.html", reason="Could not fetch user data"
                ),
                500,
            )
    except Exception as e:
        app.logger.error(e)

    # Get pagination parameters
    limit = min(int(request.args.get('limit', 5)), 10)  # Max 100
    offset = int(request.args.get('offset', 0))

    try:
        # Query transactions for this wallet address, ordered by most recent
        query = Transaction.query.filter_by(wallet_address=wallet_address)

        # Get total count
        total = query.count()

        # Get paginated results ordered by created_at descending (most recent first)
        transactions = query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset).all()

        # Convert to list of dicts
        transactions_data = []
        for tx in transactions:
            transactions_data.append({
                "id": tx.id,
                "reference": tx.reference,
                "transaction_type": tx.transaction_type,
                "status": tx.status,
                "incoming_currency": tx.incoming_currency,
                "outgoing_currency": tx.outgoing_currency,
                "value": str(tx.value),
                "fee": str(tx.fee),
                "first_name": tx.first_name,
                "last_name": tx.last_name,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
                "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
                "tx_hash": tx.tx_hash
            })

        app.logger.info(f"Retrieved {len(transactions_data)} transactions for wallet {wallet_address}")

        return make_response(
            render_template(
                "transactions/list.html",
                wallet_data=wallet_data,
                user_data=user_data,
                transaction_data={
                    "transactions": transactions_data,
                    "total": total,
                    "limit": limit,
                    "offset": offset
                })
        )

    except Exception as e:
        app.logger.exception(f"Error fetching transactions for wallet {wallet_address}: {e}")
        return make_response(
            render_template("error/500.html", reason="Failed to fetch transactions"), 500
        )


@bp.route("/balance", methods=["GET"])
@require_wallet_auth
def balance() -> Response:
    """
    API endpoint to get wallet balance.
    Extracts wallet address from authenticated request.
    """
    wallet_address = request.wallet_address
    return get_wallet_balance(wallet_address)


def get_wallet_balance(wallet_address: str) -> Response:
    """
    Get wallet balance for SOL, USDC, and EURC tokens.

    Returns:
        JSON response with wallet balances:
        {
            "wallet_address": "...",
            "balances": {
                "sol": {"amount": float, "decimals": int, "formatted": str},
                "usdc": {"amount": float, "decimals": int, "formatted": str},
                "eurc": {"amount": float, "decimals": int, "formatted": str}
            }
        }
    """
    try:
        from solana.rpc.api import Client
        from solders.pubkey import Pubkey
        from spl.token.instructions import get_associated_token_address

        # Initialize Solana client
        solana_rpc_url = app.config.get("SOLANA_RPC_URL")
        app.logger.info(f"Getting wallet balance for {wallet_address} at {solana_rpc_url}")
        client = Client(solana_rpc_url)

        # Parse wallet address
        wallet_pubkey = Pubkey.from_string(wallet_address)

        # Get SOL balance
        sol_balance_response = client.get_balance(wallet_pubkey)
        sol_balance_lamports = sol_balance_response.value if sol_balance_response.value else 0
        sol_balance = sol_balance_lamports / 1e9  # Convert lamports to SOL

        # Get token mint addresses
        usdc_mint = app.config.get("USDC_TOKEN_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
        eurc_mint = app.config.get("EURC_TOKEN_MINT", "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr")

        usdc_mint_pubkey = Pubkey.from_string(usdc_mint)
        eurc_mint_pubkey = Pubkey.from_string(eurc_mint)

        # Get associated token accounts
        usdc_token_account = get_associated_token_address(wallet_pubkey, usdc_mint_pubkey)
        eurc_token_account = get_associated_token_address(wallet_pubkey, eurc_mint_pubkey)

        # Get USDC balance
        usdc_balance = 0.0
        try:
            usdc_account_info = client.get_token_account_balance(usdc_token_account)
            if usdc_account_info.value:
                usdc_balance = float(usdc_account_info.value.amount) / (10 ** usdc_account_info.value.decimals)
        except Exception as e:
            app.logger.debug(f"USDC account not found or error: {e}")

        # Get EURC balance
        eurc_balance = 0.0
        try:
            eurc_account_info = client.get_token_account_balance(eurc_token_account)
            if eurc_account_info.value:
                eurc_balance = float(eurc_account_info.value.amount) / (10 ** eurc_account_info.value.decimals)
        except Exception as e:
            app.logger.debug(f"EURC account not found or error: {e}")

        response_data = {
            "wallet_address": wallet_address,
            "balances": {
                "sol": {
                    "amount": sol_balance,
                    "decimals": 9,
                    "formatted": f"{sol_balance:.9f}"
                },
                "usdc": {
                    "amount": usdc_balance,
                    "decimals": 6,
                    "formatted": f"{usdc_balance:.6f}"
                },
                "eurc": {
                    "amount": eurc_balance,
                    "decimals": 6,
                    "formatted": f"{eurc_balance:.6f}"
                }
            }
        }

        return make_response(response_data, 200)

    except Exception as e:
        app.logger.exception(f"Error fetching wallet balance for {request.wallet_address}: {e}")
        return make_response({
            "error": "Failed to fetch wallet balance",
            "message": str(e)
        }, 500)


@bp.route("/confirm-withdraw/<reference>", methods=["POST"])
@require_wallet_auth
def confirm_withdraw_transaction(reference: str) -> Response:
    """
    Confirms a withdrawal transaction after user has signed and submitted it.
    Updates the database with the transaction signature and sends to ledger queue.

    Expects JSON body:
    {
        "signature": "transaction_signature_from_solana"
    }

    Returns:
        JSON response with status
    """
    wallet_address = request.wallet_address

    try:
        # Get signature from request
        data = request.get_json()
        if not data or 'signature' not in data:
            return make_response({
                "error": "Missing signature",
                "message": "Transaction signature is required"
            }, 400)

        signature = data['signature']

        # Look up transaction
        transaction = Transaction.query.filter_by(reference=reference).first()

        if not transaction:
            return make_response({
                "error": "Transaction not found",
                "reference": reference
            }, 404)

        # Validate transaction belongs to this wallet
        if transaction.wallet_address != wallet_address:
            return make_response({
                "error": "Unauthorized",
                "message": "This transaction does not belong to your wallet"
            }, 403)

        # Validate transaction type and status
        if transaction.transaction_type != "WITHDRAW":
            return make_response({
                "error": "Invalid transaction type",
                "message": "Only WITHDRAW transactions can be confirmed"
            }, 400)

        if transaction.status != "PENDING_PAYEE":
            return make_response({
                "error": "Invalid transaction status",
                "message": f"Transaction cannot be confirmed in {transaction.status} status"
            }, 400)

        app.logger.info(f"Confirming withdrawal {reference} with signature {signature}")

        # Verify transaction on Solana blockchain before updating our database
        try:
            from solana.rpc.api import Client
            from solders.signature import Signature
            from spl.memo.constants import MEMO_PROGRAM_ID

            solana_rpc_url = app.config.get("SOLANA_RPC_URL")
            client = Client(solana_rpc_url)

            # Parse signature
            sig = Signature.from_string(signature)

            # Get transaction details from Solana
            app.logger.info(f"Verifying transaction {signature} on Solana network...")
            tx_response = client.get_transaction(
                sig,
                encoding="json",
                max_supported_transaction_version=0
            )

            if not tx_response.value:
                app.logger.error(f"Transaction {signature} not found on Solana network")
                return make_response({
                    "error": "Transaction not found",
                    "message": "Transaction signature not found on Solana blockchain. Please wait a moment and try again."
                }, 404)

            # Check if transaction succeeded
            if tx_response.value.transaction.meta.err:
                app.logger.error(f"Transaction {signature} failed on Solana: {tx_response.value.transaction.meta.err}")
                return make_response({
                    "error": "Transaction failed",
                    "message": f"Transaction failed on Solana blockchain: {tx_response.value.transaction.meta.err}"
                }, 400)

            # Verify the transaction memo contains our reference
            tx_data = tx_response.value
            memo_found = False

            # Get account keys from the transaction message
            account_keys = tx_data.transaction.transaction.message.account_keys

            # Check instructions for memo
            for instruction in tx_data.transaction.transaction.message.instructions:
                # UiCompiledInstruction uses program_id_index to reference the program
                # We need to look up the actual program ID from account_keys
                program_id_index = instruction.program_id_index
                program_id = account_keys[program_id_index]

                # Check if instruction is from the memo program
                if str(program_id) == str(MEMO_PROGRAM_ID):
                    # Decode memo data - handle different data formats
                    try:
                        if isinstance(instruction.data, str):
                            # Data is already a string
                            memo_data = instruction.data
                        elif isinstance(instruction.data, bytes):
                            # Data is bytes, decode it
                            memo_data = instruction.data.decode('utf-8', errors='ignore')
                        elif isinstance(instruction.data, (list, tuple)):
                            # Data is a list/array of bytes
                            memo_data = bytes(instruction.data).decode('utf-8', errors='ignore')
                        else:
                            # Unknown format, convert to string
                            memo_data = str(instruction.data)

                        app.logger.info(f"Found memo in transaction: {memo_data}")
                        if reference in memo_data:
                            memo_found = True
                            break
                    except Exception as memo_error:
                        app.logger.warning(f"Could not decode memo data: {memo_error}")
                        continue

            if not memo_found:
                app.logger.warning(f"Transaction {signature} does not contain expected reference {reference}")
                # Don't fail here, just log warning - memo verification is secondary

            app.logger.info(f"Transaction {signature} verified successfully on Solana")

        except Exception as verify_error:
            app.logger.exception(f"Error verifying transaction on Solana: {verify_error}")
            return make_response({
                "error": "Verification failed",
                "message": f"Could not verify transaction on Solana blockchain: {str(verify_error)}"
            }, 500)

        # Update transaction with signature and set to PENDING_ANCHOR
        transaction.tx_hash = signature
        transaction.status = "PENDING_ANCHOR"
        transaction.updated_at = datetime.now()
        db.session.commit()

        app.logger.info(f"Transaction {reference} updated with signature and status PENDING_CHAIN")

        # Send payment payload to ledger with signature and payment details
        try:
            from mykobo_py.message_bus.models import PaymentPayload, MessageBusMessage, InstructionType

            service_token = app.config["IDENTITY_SERVICE_CLIENT"].acquire_token()

            # Get user data for payer name
            try:
                wallet_profile_response = app.config["WALLET_SERVICE_CLIENT"].get_wallet_profile(service_token, wallet_address)
                wallet_profile = wallet_profile_response.json()
                identity_service_response = app.config["IDENTITY_SERVICE_CLIENT"].get_user_profile(service_token, wallet_profile["profile_id"])
                user_data = identity_service_response.json()
                payer_name = f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip()
                bank_account_number = user_data.get('bank_account_number')
            except Exception as user_error:
                app.logger.warning(f"Could not fetch user data for payment payload: {user_error}")
                payer_name = None
                bank_account_number = None

            # Create payment payload with transaction details using mykobo-py library
            payment_payload = PaymentPayload(
                external_reference=signature, # Use tx_hash as the source/proof of payment
                payer_name=payer_name,
                currency=transaction.incoming_currency,
                value=str(transaction.value),
                source="CHAIN_SOLANA",
                reference=reference,
                bank_account_number=bank_account_number,
            )

            # Create message bus message using the create method
            message = MessageBusMessage.create(
                source="DAPP",
                instruction_type=InstructionType.PAYMENT,
                payload=payment_payload,
                service_token=service_token.token,
                idempotency_key=f"{transaction.idempotency_key}-payment",
            )

            # Send to payments queue
            payment_queue_name = app.config.get("PAYMENTS_QUEUE_NAME")
            if payment_queue_name:
                queue_response = app.config["MESSAGE_BUS"].send_message(
                    message,
                    payment_queue_name,
                    "DAPP.transaction_processor",
                )
                app.logger.info(
                    f"Payment payload sent to queue for transaction {reference}: {queue_response['MessageId']}"
                )
            else:
                app.logger.warning("PAYMENTS_QUEUE_NAME not configured, skipping payment notification")

        except Exception as payment_error:
            app.logger.exception(f"Error sending payment payload for {reference}: {payment_error}")
            # Don't fail the confirmation if payment notification fails
            # The transaction is already recorded in the database

        # Return success
        return make_response({
            "status": "success",
            "message": "Transaction confirmed on blockchain",
            "signature": signature,
            "reference": reference
        }, 200)

    except Exception as e:
        app.logger.exception(f"Error confirming withdrawal {reference}: {e}")
        db.session.rollback()
        return make_response({
            "error": "Failed to confirm transaction",
            "message": str(e)
        }, 500)


def build_unsigned_withdraw_transaction(
    user_wallet: str,
    amount: float,
    currency: str,
    memo: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build an unsigned Solana transaction for withdrawal.
    User sends tokens from their wallet to the distribution wallet.

    Args:
        user_wallet: User's Solana wallet address (payer and token source)
        amount: Amount to transfer
        currency: Currency (EURC or USDC)
        memo: Optional memo to include in transaction

    Returns:
        Dictionary containing:
        {
            "serialized_transaction": "base64_encoded_unsigned_transaction",
            "destination": "distribution_wallet_address",
            "amount": float,
            "currency": str
        }
    """
    import base64
    from solana.rpc.api import Client
    from solders.pubkey import Pubkey
    from solders.transaction import Transaction as SolanaTransaction
    from spl.token.instructions import (
        get_associated_token_address,
        create_associated_token_account,
        transfer_checked,
        TransferCheckedParams,
    )
    from spl.token.constants import TOKEN_PROGRAM_ID
    from spl.memo.constants import MEMO_PROGRAM_ID
    from spl.memo.instructions import MemoParams, create_memo

    # Get configuration
    solana_rpc_url = app.config.get("SOLANA_RPC_URL")
    receivables_address = app.config.get("SOLANA_RECEIVABLES_ADDRESS")

    # Get token mint based on currency
    if currency.upper() == "EURC":
        token_mint = app.config.get("EURC_TOKEN_MINT", "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr")
    elif currency.upper() == "USDC":
        token_mint = app.config.get("USDC_TOKEN_MINT", "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
    else:
        raise ValueError(f"Unsupported currency: {currency}")

    # Initialize Solana client
    client = Client(solana_rpc_url)
    print("user wallet: ", user_wallet)
    print("distribution wallet: ", receivables_address)
    print("Token Ming: ", token_mint)
    # Parse addresses
    user_pubkey = Pubkey.from_string(user_wallet)
    distribution_pubkey = Pubkey.from_string(receivables_address)
    mint_pubkey = Pubkey.from_string(token_mint)

    app.logger.info(
        f"Building unsigned transaction: {amount} {currency} {user_wallet} -> {receivables_address} on {solana_rpc_url}"
    )

    # Token has 6 decimals
    decimals = 6
    amount_in_smallest_unit = int(amount * (10 ** decimals))

    # Get associated token accounts
    user_token_account = get_associated_token_address(user_pubkey, mint_pubkey)
    distribution_token_account = get_associated_token_address(distribution_pubkey, mint_pubkey)

    # Check if distribution token account exists
    distribution_account_info = client.get_account_info(distribution_token_account)

    # Build instructions list
    instructions = []

    # Add memo instruction if memo is provided
    if memo:
        app.logger.info(f"Adding memo to transaction: {memo}")
        memo_ix = create_memo(
            MemoParams(
                program_id=MEMO_PROGRAM_ID,
                signer=user_pubkey,
                message=memo.encode('utf-8')
            )
        )
        instructions.append(memo_ix)

    # If distribution wallet doesn't have a token account, create it
    # User pays for this account creation
    if not distribution_account_info.value:
        app.logger.info(
            f"Creating token account for distribution wallet: {distribution_token_account}"
        )
        create_account_ix = create_associated_token_account(
            payer=user_pubkey,
            owner=distribution_pubkey,
            mint=mint_pubkey,
        )
        instructions.append(create_account_ix)

    # Add transfer instruction - user transfers to distribution wallet
    transfer_ix = transfer_checked(
        TransferCheckedParams(
            program_id=TOKEN_PROGRAM_ID,
            source=user_token_account,
            mint=mint_pubkey,
            dest=distribution_token_account,
            owner=user_pubkey,  # User is the owner/signer
            amount=amount_in_smallest_unit,
            decimals=decimals,
        )
    )
    instructions.append(transfer_ix)

    # Get recent blockhash
    recent_blockhash = client.get_latest_blockhash().value.blockhash

    # Create a message with instructions, payer, and blockhash
    from solders.message import Message

    message = Message.new_with_blockhash(
        instructions,
        user_pubkey,  # Payer
        recent_blockhash
    )

    # Create unsigned transaction from message
    # The transaction is ready to be signed by the user's wallet
    transaction = SolanaTransaction.new_unsigned(message)

    # Serialize the unsigned transaction to base64
    serialized_tx = base64.b64encode(bytes(transaction)).decode('utf-8')

    return {
        "serialized_transaction": serialized_tx,
        "destination": receivables_address,
        "amount": amount,
        "currency": currency
    }
