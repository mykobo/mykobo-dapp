"""
Utility functions for retrying failed transaction queue sends.
"""
from datetime import datetime
from typing import List, Dict, Any

from flask import current_app as app
from mykobo_py.message_bus import MessageBusMessage, InstructionType, TransactionPayload
from sqlalchemy import and_

from app.database import db
from app.models import Transaction


def get_unsent_transactions(limit: int = 100) -> List[Transaction]:
    """
    Get transactions that have been saved to database but not sent to queue.

    Args:
        limit: Maximum number of transactions to retrieve

    Returns:
        List of Transaction objects where message_id is NULL
    """
    return Transaction.query.filter(
        Transaction.message_id.is_(None)
    ).order_by(
        Transaction.created_at.asc()
    ).limit(limit).all()


def get_failed_transactions_by_status(status: str, limit: int = 100) -> List[Transaction]:
    """
    Get transactions by status that haven't been sent to queue.

    Args:
        status: Transaction status to filter by
        limit: Maximum number of transactions to retrieve

    Returns:
        List of Transaction objects
    """
    return Transaction.query.filter(
        and_(
            Transaction.status == status,
            Transaction.message_id.is_(None)
        )
    ).order_by(
        Transaction.created_at.asc()
    ).limit(limit).all()


def retry_transaction(transaction: Transaction) -> Dict[str, Any]:
    """
    Retry sending a transaction to the queue.

    Args:
        transaction: Transaction object to retry

    Returns:
        Dict with status and details:
        {
            'success': bool,
            'message_id': str or None,
            'error': str or None
        }
    """
    try:
        # Acquire service token - REQUIRED for sending to queue
        identity_service = app.config.get("IDENTITY_SERVICE_CLIENT")
        if not identity_service:
            error_msg = f"Identity service not configured, cannot retry transaction [{transaction.reference}]"
            app.logger.error(error_msg)
            return {
                'success': False,
                'message_id': None,
                'error': error_msg
            }

        try:
            service_token = identity_service.acquire_token()
            app.logger.debug(f"Acquired service token for retry of transaction [{transaction.reference}]")
        except Exception as e:
            error_msg = f"Failed to acquire service token for [{transaction.reference}]: {e}"
            app.logger.error(error_msg)
            return {
                'success': False,
                'message_id': None,
                'error': error_msg
            }

        transaction_payload = TransactionPayload(
            external_reference=transaction.id,
            source=transaction.source,
            reference=transaction.reference,
            first_name=transaction.first_name,
            last_name=transaction.last_name,
            transaction_type=transaction.transaction_type,
            status=transaction.status,
            incoming_currency=transaction.incoming_currency,
            outgoing_currency=transaction.outgoing_currency,
            value=transaction.value,
            fee=transaction.fee,
            payer=transaction.payer_id,
            payee=transaction.payee_id,
        )

        ledger_payload = MessageBusMessage.create(
            source="DAPP",
            instruction_type=InstructionType.TRANSACTION,
            payload=transaction_payload,
            service_token=service_token.token,
            idempotency_key=None
        )
        # Reconstruct ledger payload from transaction record

        # Send to queue
        queue_response = app.config["MESSAGE_BUS"].send_message(
            ledger_payload,
            app.config["TRANSACTION_QUEUE_NAME"],
            "DAPP.transaction_retry",
        )

        # Update transaction with message ID
        transaction.message_id = queue_response['MessageId']
        transaction.queue_sent_at = datetime.now()
        db.session.commit()

        app.logger.info(
            f"Successfully retried transaction [{transaction.reference}] - Message ID: {queue_response['MessageId']}"
        )

        return {
            'success': True,
            'message_id': queue_response['MessageId'],
            'error': None
        }

    except Exception as e:
        app.logger.exception(
            f"Failed to retry transaction [{transaction.reference}]: {e}"
        )
        db.session.rollback()
        return {
            'success': False,
            'message_id': None,
            'error': str(e)
        }


def retry_unsent_transactions(limit: int = 100) -> Dict[str, Any]:
    """
    Retry all unsent transactions.

    Args:
        limit: Maximum number of transactions to retry

    Returns:
        Dict with summary:
        {
            'total': int,
            'succeeded': int,
            'failed': int,
            'results': List[Dict]
        }
    """
    unsent = get_unsent_transactions(limit)

    results = {
        'total': len(unsent),
        'succeeded': 0,
        'failed': 0,
        'results': []
    }

    for transaction in unsent:
        result = retry_transaction(transaction)

        if result['success']:
            results['succeeded'] += 1
        else:
            results['failed'] += 1

        results['results'].append({
            'reference': transaction.reference,
            'db_id': transaction.id,
            'success': result['success'],
            'message_id': result['message_id'],
            'error': result['error']
        })

    app.logger.info(
        f"Retry summary: {results['succeeded']} succeeded, {results['failed']} failed out of {results['total']}"
    )

    return results


def get_transaction_stats() -> Dict[str, int]:
    """
    Get statistics about transaction queue status.

    Returns:
        Dict with counts:
        {
            'total': int,
            'sent': int,
            'unsent': int,
            'by_status': Dict[str, int]
        }
    """
    total = Transaction.query.count()
    sent = Transaction.query.filter(Transaction.message_id.isnot(None)).count()
    unsent = Transaction.query.filter(Transaction.message_id.is_(None)).count()

    # Count by status
    from sqlalchemy import func
    status_counts = db.session.query(
        Transaction.status,
        func.count(Transaction.id)
    ).group_by(Transaction.status).all()

    by_status = {status: count for status, count in status_counts}

    return {
        'total': total,
        'sent': sent,
        'unsent': unsent,
        'by_status': by_status
    }
