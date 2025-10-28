#!/usr/bin/env python
"""
CLI tool for retrying failed transaction queue sends.

Usage:
    python retry_transactions.py list          # List unsent transactions
    python retry_transactions.py stats         # Show transaction statistics
    python retry_transactions.py retry [id]    # Retry specific transaction by ID
    python retry_transactions.py retry-all     # Retry all unsent transactions
"""
import sys
import os
from app import create_app
from app.database import db
from app.models import Transaction
from app.transaction_retry import (
    get_unsent_transactions,
    retry_transaction,
    retry_unsent_transactions,
    get_transaction_stats
)


def list_unsent():
    """List all unsent transactions."""
    transactions = get_unsent_transactions(limit=1000)

    if not transactions:
        print("✓ No unsent transactions found")
        return

    print(f"\n{'ID':<8} {'Reference':<20} {'Type':<12} {'Status':<20} {'Amount':<12} {'Created':<20}")
    print("=" * 100)

    for tx in transactions:
        print(
            f"{tx.id:<8} {tx.reference:<20} {tx.transaction_type:<12} "
            f"{tx.status:<20} {tx.value:<12} {tx.created_at.strftime('%Y-%m-%d %H:%M:%S'):<20}"
        )

    print(f"\nTotal unsent: {len(transactions)}")


def show_stats():
    """Show transaction statistics."""
    stats = get_transaction_stats()

    print("\n=== Transaction Statistics ===")
    print(f"Total transactions:  {stats['total']}")
    print(f"Sent to queue:       {stats['sent']}")
    print(f"Unsent (pending):    {stats['unsent']}")

    print("\n=== By Status ===")
    for status, count in stats['by_status'].items():
        print(f"  {status:<25} {count}")


def retry_by_id(transaction_id: int):
    """Retry a specific transaction by ID."""
    transaction = db.session.get(Transaction, transaction_id)

    if not transaction:
        print(f"✗ Transaction with ID {transaction_id} not found")
        return

    if transaction.message_id:
        print(f"✓ Transaction [{transaction.reference}] already sent (Message ID: {transaction.message_id})")
        return

    print(f"Retrying transaction [{transaction.reference}] (ID: {transaction_id})...")

    result = retry_transaction(transaction)

    if result['success']:
        print(f"✓ Successfully sent to queue - Message ID: {result['message_id']}")
    else:
        print(f"✗ Failed to send: {result['error']}")


def retry_all():
    """Retry all unsent transactions."""
    print("Retrying all unsent transactions...")

    results = retry_unsent_transactions(limit=1000)

    print(f"\n=== Retry Summary ===")
    print(f"Total processed: {results['total']}")
    print(f"Succeeded:       {results['succeeded']}")
    print(f"Failed:          {results['failed']}")

    if results['failed'] > 0:
        print("\n=== Failed Transactions ===")
        for result in results['results']:
            if not result['success']:
                print(f"  ID {result['db_id']} ({result['reference']}): {result['error']}")


def main():
    """Main entry point."""
    env = os.getenv('ENV', 'development')
    app = create_app(env)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    with app.app_context():
        if command == 'list':
            list_unsent()
        elif command == 'stats':
            show_stats()
        elif command == 'retry':
            if len(sys.argv) < 3:
                print("Error: Please provide transaction ID")
                print("Usage: python retry_transactions.py retry <id>")
                sys.exit(1)
            try:
                tx_id = int(sys.argv[2])
                retry_by_id(tx_id)
            except ValueError:
                print("Error: Transaction ID must be a number")
                sys.exit(1)
        elif command == 'retry-all':
            retry_all()
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)


if __name__ == '__main__':
    main()
