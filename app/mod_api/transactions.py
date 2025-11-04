"""
API endpoints for transaction data
"""
from flask import Blueprint, jsonify, request, current_app as app
from app.decorators import require_wallet_auth
from app.models import Transaction

bp = Blueprint("api", __name__)


@bp.route("/transactions", methods=["GET"])
@require_wallet_auth
def get_transactions():
    """
    Get list of transactions for authenticated wallet.

    Query parameters:
        limit (optional): Maximum number of transactions to return (default: 50, max: 100)
        offset (optional): Number of transactions to skip (default: 0)
        status (optional): Filter by transaction status
        transaction_type (optional): Filter by transaction type (DEPOSIT, WITHDRAW)

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
                    "tx_hash": "..."
                },
                ...
            ],
            "total": 123,
            "limit": 50,
            "offset": 0
        }
    """
    wallet_address = request.wallet_address

    # Get pagination parameters
    limit = min(int(request.args.get('limit', 50)), 100)  # Max 100
    offset = int(request.args.get('offset', 0))

    # Get optional filters
    status = request.args.get('status')
    transaction_type = request.args.get('transaction_type')

    try:
        # Build query
        query = Transaction.query.filter_by(wallet_address=wallet_address)

        # Apply optional filters
        if status:
            query = query.filter_by(status=status.upper())

        if transaction_type:
            query = query.filter_by(transaction_type=transaction_type.upper())

        # Get total count
        total = query.count()

        # Get paginated results ordered by most recent first
        transactions = query.order_by(Transaction.created_at.desc()).limit(limit).offset(offset).all()

        # Convert to list of dicts
        transactions_data = []
        for tx in transactions:
            transactions_data.append({
                "id": tx.id,
                "reference": tx.reference,
                "external_reference": tx.external_reference,
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

        app.logger.info(f"API: Retrieved {len(transactions_data)} transactions for wallet {wallet_address}")

        return jsonify({
            "wallet_address": wallet_address,
            "transactions": transactions_data,
            "total": total,
            "limit": limit,
            "offset": offset
        }), 200

    except Exception as e:
        app.logger.exception(f"API: Error fetching transactions for wallet {wallet_address}: {e}")
        return jsonify({
            "error": "Failed to fetch transactions",
            "message": str(e)
        }), 500


@bp.route("/transactions/<transaction_id>", methods=["GET"])
@require_wallet_auth
def get_transaction(transaction_id):
    """
    Get a single transaction by ID.

    Args:
        transaction_id: Transaction ID (UUID string)

    Returns:
        JSON response with transaction data:
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
            "tx_hash": "...",
            ...
        }
    """
    wallet_address = request.wallet_address

    try:
        # Find transaction by ID
        transaction = Transaction.query.get(transaction_id)

        if not transaction:
            return jsonify({
                "error": "Transaction not found",
                "id": transaction_id
            }), 404

        # Verify transaction belongs to this wallet
        if transaction.wallet_address != wallet_address:
            return jsonify({
                "error": "Unauthorized",
                "message": "This transaction does not belong to your wallet"
            }), 403

        # Return transaction data
        transaction_data = {
            "id": transaction.id,
            "reference": transaction.reference,
            "external_reference": transaction.external_reference,
            "idempotency_key": transaction.idempotency_key,
            "transaction_type": transaction.transaction_type,
            "status": transaction.status,
            "incoming_currency": transaction.incoming_currency,
            "outgoing_currency": transaction.outgoing_currency,
            "value": str(transaction.value),
            "fee": str(transaction.fee),
            "payer_id": transaction.payer_id,
            "payee_id": transaction.payee_id,
            "first_name": transaction.first_name,
            "last_name": transaction.last_name,
            "wallet_address": transaction.wallet_address,
            "source": transaction.source,
            "tx_hash": transaction.tx_hash,
            "created_at": transaction.created_at.isoformat() if transaction.created_at else None,
            "updated_at": transaction.updated_at.isoformat() if transaction.updated_at else None,
            "message_id": transaction.message_id,
            "queue_sent_at": transaction.queue_sent_at.isoformat() if transaction.queue_sent_at else None
        }

        app.logger.info(f"API: Retrieved transaction {transaction_id} for wallet {wallet_address}")

        return jsonify(transaction_data), 200

    except Exception as e:
        app.logger.exception(f"API: Error fetching transaction {transaction_id}: {e}")
        return jsonify({
            "error": "Failed to fetch transaction",
            "message": str(e)
        }), 500


@bp.route("/transactions/stats", methods=["GET"])
@require_wallet_auth
def get_transaction_stats():
    """
    Get transaction statistics for authenticated wallet.

    Returns:
        JSON response with statistics:
        {
            "wallet_address": "...",
            "total_transactions": 123,
            "total_deposits": 50,
            "total_withdrawals": 73,
            "pending_transactions": 5,
            "completed_transactions": 118,
            "total_volume": {
                "USDC": "10000.00",
                "EURC": "5000.00"
            }
        }
    """
    wallet_address = request.wallet_address

    try:
        from sqlalchemy import func

        # Get total transactions
        total_transactions = Transaction.query.filter_by(wallet_address=wallet_address).count()

        # Get deposits count
        total_deposits = Transaction.query.filter_by(
            wallet_address=wallet_address,
            transaction_type="DEPOSIT"
        ).count()

        # Get withdrawals count
        total_withdrawals = Transaction.query.filter_by(
            wallet_address=wallet_address,
            transaction_type="WITHDRAW"
        ).count()

        # Get pending transactions (not completed/failed)
        pending_transactions = Transaction.query.filter_by(
            wallet_address=wallet_address
        ).filter(
            Transaction.status.in_(['PENDING_PAYER', 'PENDING_PAYEE', 'PENDING_ANCHOR'])
        ).count()

        # Get completed transactions
        completed_transactions = Transaction.query.filter_by(
            wallet_address=wallet_address,
            status="COMPLETED"
        ).count()

        # Get volume by currency
        volume_query = Transaction.query.filter_by(
            wallet_address=wallet_address,
            status="COMPLETED"
        ).with_entities(
            Transaction.outgoing_currency,
            func.sum(Transaction.value).label('total')
        ).group_by(Transaction.outgoing_currency).all()

        total_volume = {currency: str(total) for currency, total in volume_query}

        stats = {
            "wallet_address": wallet_address,
            "total_transactions": total_transactions,
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "pending_transactions": pending_transactions,
            "completed_transactions": completed_transactions,
            "total_volume": total_volume
        }

        app.logger.info(f"API: Retrieved stats for wallet {wallet_address}")

        return jsonify(stats), 200

    except Exception as e:
        app.logger.exception(f"API: Error fetching stats for wallet {wallet_address}: {e}")
        return jsonify({
            "error": "Failed to fetch transaction statistics",
            "message": str(e)
        }), 500
