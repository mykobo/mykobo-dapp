"""
Solana transaction utilities for USDC transfers
"""
from typing import Dict, Any
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
from flask import current_app

from app.decorators import require_wallet_auth


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
        rpc_url = current_app.config.get("SOLANA_RPC_URL")
        distribution_private_key = current_app.config.get("SOLANA_DISTRIBUTION_PRIVATE_KEY")
        eurc_mint_address = current_app.config.get("EURC_TOKEN_MINT")

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
            current_app.logger.info(
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

        current_app.logger.info(
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
        current_app.logger.error(f"Validation error creating EURC transfer: {str(e)}")
        return {
            "status": "error",
            "message": str(e),
            "transaction": None,
            "details": None
        }
    except Exception as e:
        current_app.logger.error(f"Error creating EURC transfer transaction: {str(e)}")
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
        rpc_url = current_app.config.get("SOLANA_RPC_URL")
        if not rpc_url:
            raise ValueError("SOLANA_RPC_URL not configured")

        client = Client(rpc_url)

        # Deserialize and send transaction
        transaction_bytes = bytes.fromhex(serialized_transaction)
        result = client.send_raw_transaction(transaction_bytes)

        current_app.logger.info(f"Transaction sent: {result.value}")

        return {
            "status": "success",
            "transaction_signature": str(result.value),
            "message": "Transaction sent successfully"
        }

    except Exception as e:
        current_app.logger.error(f"Error sending transaction: {str(e)}")
        return {
            "status": "error",
            "transaction_signature": None,
            "message": f"Failed to send transaction: {str(e)}"
        }
