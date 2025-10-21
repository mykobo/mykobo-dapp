"""
Solana transaction utilities for USDC transfers
"""
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import botocore
from solana.rpc.api import Client
from solders.transaction import Transaction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from spl.token.instructions import (
    get_associated_token_address,
    create_associated_token_account,
    transfer_checked,
    TransferCheckedParams,
)
from spl.token.constants import TOKEN_PROGRAM_ID, ASSOCIATED_TOKEN_PROGRAM_ID
from flask import current_app as app, Blueprint, Response, make_response, render_template, request, redirect, url_for
from app.forms import Transaction as TransactionForm
from app.decorators import require_wallet_auth
from app.util import generate_reference, retrieve_ip_address, get_fee, get_minimum_transaction_value, \
    get_maximum_transaction_value

bp = Blueprint("transaction", __name__)
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
            return 'EUR', 'EURC'
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
                    "external_reference": str(uuid.uuid4()),
                    "source": "ANCHOR_SOLANA",
                    "reference": tx_reference,
                    "first_name": user_data["first_name"],
                    "last_name": user_data["last_name"],
                    "transaction_type": kind,
                    "status": (
                        "pending_payee"
                        if kind == "withdrawal"
                        else "pending_payer"
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
            try:
                app.logger.info(
                    f"Sending message to ledger for transaction [{tx_reference}]..."
                )
                print(ledger_payload)
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
                return make_response(render_template(
                    "transactions/info.html",
                    transaction_data=ledger_payload["payload"],
                    user_data=user_data,
                    wallet_address=wallet_address,
                    wallet_balances={
                        "solana_balance": 2000,
                        "usdc_balance": 2000,
                        "eurc_balance": 2000,
                    }
                ), 201)
            except botocore.exceptions.EndpointConnectionError as e:
                app.logger.exception(
                    f"We could not submit this transaction to our ledger: {e}"
                )
                return make_response(
                    render_template(
                        "error/500.html",
                        reason="Could not submit transaction to ledger, if this persists please contact support",
                    ),
                    500,
                )

        else:
            return make_response(redirect(url_for("transaction.new", type=kind)))
    else:
        return make_response(
            render_template(
                f"transactions/{kind}.html",
                form=form,
                user_data=user_data,
                wallet_address=wallet_address,
                kind=kind,
                asset=asset,
                min_amount=get_minimum_transaction_value(),
                max_amount=get_maximum_transaction_value(),
                fee_endpoint="/fees",
                wallet_balances={
                    "solana_balance": 2000,
                    "usdc_balance": 2000,
                    "eurc_balance": 2000,
                }
            )
            , 200)


@require_wallet_auth
def create_transaction(
        recipient_address: str,
        amount: float,
) -> Dict[str, Any]:
    """
    Create a Solana transaction to transfer TOKEN from the distribution address to a user-provided address.

    Args:
        recipient_address: The recipient's Solana wallet address (base58 string)
        amount: The amount of TOKEN to transfer (in TOKEN units, will be converted to lamports)

    Returns:
        Dict containing:
            - transaction: Serialized transaction (base64 string)
            - transaction_hash: Transaction signature/hash
            - status: "success" or "error"
            - message: Status message
            - details: Additional transaction details

    Raises:
        ValueError: If configuration is missing or invalid
        Exception: If transaction creation fails
    """
    try:
        # Get configuration from Flask app
        rpc_url = app.config.get("SOLANA_RPC_URL")
        distribution_private_key = app.config.get("SOLANA_DISTRIBUTION_PRIVATE_KEY")
        eurc_mint_address = app.config.get("EURC_TOKEN_MINT")

        # Validate configuration
        if not rpc_url:
            raise ValueError("SOLANA_RPC_URL not configured")
        if not distribution_private_key:
            raise ValueError("SOLANA_DISTRIBUTION_PRIVATE_KEY not configured")
        if not eurc_mint_address:
            raise ValueError("USDC_TOKEN_MINT not configured")

        # Validate inputs
        if not recipient_address:
            raise ValueError("Recipient address is required")
        if amount <= 0:
            raise ValueError("Amount must be greater than 0")

        # Initialize Solana client
        client = Client(rpc_url)

        # Parse keypairs and addresses
        distribution_keypair = Keypair.from_base58_string(distribution_private_key)
        distribution_pubkey = distribution_keypair.pubkey()
        recipient_pubkey = Pubkey.from_string(recipient_address)
        eurc_mint = Pubkey.from_string(eurc_mint_address)

        # EURC has 6 decimals
        eurc_decimals = 6
        amount_in_smallest_unit = int(amount * (10 ** eurc_decimals))

        # Get associated token accounts
        distribution_token_account = get_associated_token_address(
            distribution_pubkey,
            eurc_mint
        )
        recipient_token_account = get_associated_token_address(
            recipient_pubkey,
            eurc_mint
        )

        # Create transaction
        transaction = Transaction()

        # Check if recipient token account exists
        recipient_account_info = client.get_account_info(recipient_token_account)

        # If recipient doesn't have a token account, create it
        if not recipient_account_info.value:
            app.logger.info(
                f"Recipient token account doesn't exist, creating it: {recipient_token_account}"
            )
            create_account_ix = create_associated_token_account(
                payer=distribution_pubkey,
                owner=recipient_pubkey,
                mint=eurc_mint,
            )
            transaction.add(create_account_ix)

        # Add transfer instruction
        transfer_ix = transfer_checked(
            TransferCheckedParams(
                program_id=TOKEN_PROGRAM_ID,
                source=distribution_token_account,
                mint=eurc_mint,
                dest=recipient_token_account,
                owner=distribution_pubkey,
                amount=amount_in_smallest_unit,
                decimals=eurc_decimals,
            )
        )
        transaction.add(transfer_ix)

        # Get recent blockhash
        recent_blockhash = client.get_latest_blockhash().value.blockhash
        transaction.recent_blockhash = recent_blockhash
        transaction.fee_payer = distribution_pubkey

        # Sign transaction
        transaction.sign(distribution_keypair)

        # Serialize transaction
        serialized_transaction = transaction.serialize()

        app.logger.info(
            f"Created EURC transfer transaction: {amount} EURC to {recipient_address}"
        )

        return {
            "status": "success",
            "message": "Transaction created successfully",
            "transaction": serialized_transaction.hex(),
            "details": {
                "from_address": str(distribution_pubkey),
                "to_address": recipient_address,
                "amount_eurc": amount,
                "amount_lamports": amount_in_smallest_unit,
                "token_mint": eurc_mint_address,
                "distribution_token_account": str(distribution_token_account),
                "recipient_token_account": str(recipient_token_account),
            }
        }

    except ValueError as e:
        app.logger.error(f"Validation error creating EURC transfer: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "transaction": None,
            "details": None
        }
    except Exception as e:
        app.logger.error(f"Error creating EURC transfer transaction: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to create transaction: {str(e)}",
            "transaction": None,
            "details": None
        }


def send_transaction(serialized_transaction: str) -> Dict[str, Any]:
    """
    Send a serialized Solana transaction to the network.

    Args:
        serialized_transaction: Hex-encoded serialized transaction

    Returns:
        Dict containing:
            - status: "success" or "error"
            - transaction_signature: Transaction signature if successful
            - message: Status message
    """
    try:
        rpc_url = app.config.get("SOLANA_RPC_URL")
        if not rpc_url:
            raise ValueError("SOLANA_RPC_URL not configured")

        client = Client(rpc_url)

        # Deserialize and send transaction
        transaction_bytes = bytes.fromhex(serialized_transaction)
        result = client.send_raw_transaction(transaction_bytes)

        app.logger.info(f"Transaction sent: {result.value}")

        return {
            "status": "success",
            "transaction_signature": str(result.value),
            "message": "Transaction sent successfully"
        }

    except Exception as e:
        app.logger.error(f"Error sending transaction: {str(e)}")
        return {
            "status": "error",
            "transaction_signature": None,
            "message": f"Failed to send transaction: {str(e)}"
        }
