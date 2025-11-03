#!/usr/bin/env python
"""
Background worker for automatically retrying failed transaction queue sends.

This service runs continuously and:
1. Checks for unsent transactions every N seconds
2. Retries sending them to the queue
3. Logs results
4. Provides health metrics

Usage:
    python retry_worker.py [--interval SECONDS]
"""
import os
import sys
import time
import signal
import argparse
from datetime import datetime

from app import create_app
from app.transaction_retry import retry_unsent_transactions, get_transaction_stats


class RetryWorker:
    """Background worker for retrying failed transactions."""

    def __init__(self, interval: int = 300, max_retries_per_run: int = 100):
        """
        Initialize the retry worker.

        Args:
            interval: Seconds between retry attempts (default: 300 = 5 minutes)
            max_retries_per_run: Maximum transactions to retry per run (default: 100)
        """
        self.interval = interval
        self.max_retries_per_run = max_retries_per_run
        self.running = True
        self.total_retries = 0
        self.total_successes = 0
        self.total_failures = 0
        self.start_time = datetime.now()

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Create Flask app
        env = os.getenv('ENV', 'production')
        self.app = create_app(env)

        print(f"[{self._timestamp()}] Retry Worker initialized")
        print(f"[{self._timestamp()}] Environment: {env}")
        print(f"[{self._timestamp()}] Retry interval: {interval} seconds")
        print(f"[{self._timestamp()}] Max retries per run: {max_retries_per_run}")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        print(f"\n[{self._timestamp()}] Received signal {signum}, shutting down...")
        self.running = False

    def _timestamp(self) -> str:
        """Get formatted timestamp for logging."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _log_stats(self):
        """Log current statistics."""
        uptime = datetime.now() - self.start_time
        print(f"\n[{self._timestamp()}] === Worker Statistics ===")
        print(f"[{self._timestamp()}] Uptime: {uptime}")
        print(f"[{self._timestamp()}] Total retry attempts: {self.total_retries}")
        print(f"[{self._timestamp()}] Total successes: {self.total_successes}")
        print(f"[{self._timestamp()}] Total failures: {self.total_failures}")

    def run_retry_cycle(self):
        """Run a single retry cycle."""
        with self.app.app_context():
            try:
                # Get statistics before retry
                stats_before = get_transaction_stats()
                unsent_count = stats_before['unsent']

                if unsent_count == 0:
                    print(f"[{self._timestamp()}] No unsent transactions, skipping cycle")
                    return

                print(f"\n[{self._timestamp()}] Starting retry cycle...")
                print(f"[{self._timestamp()}] Found {unsent_count} unsent transactions")

                # Retry transactions
                results = retry_unsent_transactions(limit=self.max_retries_per_run)

                # Update statistics
                self.total_retries += results['total']
                self.total_successes += results['succeeded']
                self.total_failures += results['failed']

                # Log results
                print(f"[{self._timestamp()}] Retry cycle completed")
                print(f"[{self._timestamp()}] Processed: {results['total']}")
                print(f"[{self._timestamp()}] Succeeded: {results['succeeded']}")
                print(f"[{self._timestamp()}] Failed: {results['failed']}")

                # Log any failures
                if results['failed'] > 0:
                    print(f"[{self._timestamp()}] Failed transactions:")
                    for result in results['results']:
                        if not result['success']:
                            print(
                                f"[{self._timestamp()}]   - ID {result['db_id']} "
                                f"({result['reference']}): {result['error']}"
                            )

            except Exception as e:
                print(f"[{self._timestamp()}] ERROR in retry cycle: {e}")
                import traceback
                traceback.print_exc()

    def run(self):
        """Main worker loop."""
        print(f"[{self._timestamp()}] Worker started, waiting for first cycle...")
        print(f"[{self._timestamp()}] Press Ctrl+C to stop\n")

        cycle_count = 0

        while self.running:
            try:
                # Run retry cycle
                self.run_retry_cycle()
                cycle_count += 1

                # Log stats every 10 cycles or on first cycle
                if cycle_count == 1 or cycle_count % 10 == 0:
                    self._log_stats()

                # Wait for next cycle (interruptible sleep)
                if self.running:
                    print(f"[{self._timestamp()}] Next cycle in {self.interval} seconds...")
                    for _ in range(self.interval):
                        if not self.running:
                            break
                        time.sleep(1)

            except KeyboardInterrupt:
                print(f"\n[{self._timestamp()}] Keyboard interrupt received")
                break
            except Exception as e:
                print(f"[{self._timestamp()}] ERROR in main loop: {e}")
                import traceback
                traceback.print_exc()
                # Wait a bit before retrying to avoid rapid error loops
                time.sleep(10)

        # Final statistics
        print(f"\n[{self._timestamp()}] Worker shutting down...")
        self._log_stats()
        print(f"[{self._timestamp()}] Goodbye!")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Background worker for retrying failed transaction queue sends'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=300,
        help='Seconds between retry attempts (default: 300)'
    )
    parser.add_argument(
        '--max-retries',
        type=int,
        default=100,
        help='Maximum transactions to retry per run (default: 100)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.interval < 10:
        print("ERROR: Interval must be at least 10 seconds")
        sys.exit(1)

    if args.max_retries < 1:
        print("ERROR: Max retries must be at least 1")
        sys.exit(1)

    # Create and run worker
    worker = RetryWorker(interval=args.interval, max_retries_per_run=args.max_retries)
    worker.run()


if __name__ == '__main__':
    main()
