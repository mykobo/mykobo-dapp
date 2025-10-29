"""
Solana transaction utilities for USDC transfers
"""
import uuid
from datetime import datetime
from typing import Optional

import botocore
from flask import current_app as app, Blueprint, Response, make_response, render_template, request, redirect, url_for, \
    flash
from app.forms import Transaction as TransactionForm
from app.decorators import require_wallet_auth
from app.util import generate_reference, retrieve_ip_address, get_fee, get_minimum_transaction_value, \
    get_maximum_transaction_value
from app.database import db
from app.models import Transaction as TransactionModel, Transaction

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

    wallet_data = {}
    try:
        wallet_data = get_wallet_balance(wallet_address).json
    except Exception as wallet_error:
        app.logger.exception(f"Could not fetch wallet balance: {wallet_error}")

    if asset and wallet_data and kind == 'withdraw':
        minimum_transaction_value = get_minimum_transaction_value()
        asset_balance = wallet_data["balances"].get(asset, {})
        if "amount" in asset_balance and asset_balance["amount"] < minimum_transaction_value:
            app.logger.warning(
                "Asset balance is less than minimum transaction value ({})".format(minimum_transaction_value))
            flash(f"You do not have enough {asset} minimum value is {minimum_transaction_value}", "danger")
            return make_response(redirect(url_for("transaction.new", type=kind)), 302)

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

            # Now try to send to queue
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
                return make_response(redirect(url_for("transaction.info", reference=tx_reference)))
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
            return make_response(redirect(url_for("transaction.new", type=kind)))
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

    return make_response(render_template(
        "transactions/info.html",
        transaction_data=transaction,
        user_data=user_data,
        wallet_data=wallet_data
    ), 201)


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
        solana_rpc_url = app.config.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
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
