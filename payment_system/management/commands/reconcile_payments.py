import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from payment_system.domain.services.webhook_service import WebhookService  # For handling payment_intent.succeeded
from payment_system.infra.payment_provider.stripe_provider import StripePaymentProvider
from payment_system.models import PaymentTransaction
from utils.transaction_utils import atomic_with_isolation


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconciles pending payment transactions with Stripe."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Reconcile all transactions regardless of age (default: last 7 days)",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=7,
            help="Number of days back to check for transactions (default: 7)",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting payment reconciliation with Stripe..."))

        provider = StripePaymentProvider()

        # Determine the date range for transactions to reconcile
        since_date = None
        if not options["all"]:
            since_date = timezone.now() - timezone.timedelta(days=options["days"])
            self.stdout.write(f"Reconciling transactions from the last {options['days']} days.")
        else:
            self.stdout.write("Reconciling all outstanding transactions.")

        # Find transactions that might need reconciliation
        reconcile_statuses = ["pending", "held", "processing", "waiting_refund"]
        transactions_to_reconcile = PaymentTransaction.objects.filter(status__in=reconcile_statuses)
        if since_date:
            transactions_to_reconcile = transactions_to_reconcile.filter(created_at__gte=since_date)

        total_transactions = transactions_to_reconcile.count()
        self.stdout.write(f"Found {total_transactions} transactions to potentially reconcile.")

        reconciled_count = 0
        error_count = 0

        for transaction_obj in transactions_to_reconcile:
            try:
                self.stdout.write(
                    f"  Processing transaction {transaction_obj.id} (Status: {transaction_obj.status})..."
                )

                stripe_payment_intent_id = transaction_obj.stripe_payment_intent_id
                if not stripe_payment_intent_id:
                    self.stdout.write(
                        self.style.WARNING(
                            f"    Skipping transaction {transaction_obj.id}: No Stripe Payment Intent ID."
                        )
                    )
                    continue

                # Retrieve the latest status from Stripe
                with atomic_with_isolation("READ COMMITTED"):
                    try:
                        # Assuming provider has retrieve_payment_intent
                        payment_intent = provider.retrieve_payment_intent(stripe_payment_intent_id)

                        # Simulate Stripe webhook event for processing
                        # This reuses the existing webhook handling logic for consistency
                        fake_event = {
                            "id": f"evt_reconcile_{transaction_obj.id}",
                            "type": f"payment_intent.{payment_intent.status}",
                            "data": {"object": payment_intent},
                            "created": int(timezone.now().timestamp()),
                            "livemode": False,
                            "request": {"id": None, "idempotency_key": None},
                        }
                        # client_ip is not relevant for reconciliation command
                        handled = WebhookService.process_event(fake_event, "127.0.0.1")

                        if handled:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"    Successfully reconciled transaction {transaction_obj.id}. New status: {transaction_obj.status}"
                                )
                            )
                            reconciled_count += 1
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"    Reconciliation for {transaction_obj.id} resulted in no change or unhandled event."
                                )
                            )

                    except CommandError as e:
                        self.stdout.write(
                            self.style.ERROR(f"    Error during reconciliation of {transaction_obj.id}: {e}")
                        )
                        error_count += 1
                        logger.error(f"Reconciliation error for transaction {transaction_obj.id}: {e}")
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"    Unexpected error during reconciliation of {transaction_obj.id}: {e}"
                            )
                        )
                        error_count += 1
                        logger.error(f"Unexpected reconciliation error for transaction {transaction_obj.id}: {e}")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Failed to reconcile transaction {transaction_obj.id}: {e}"))
                error_count += 1
                logger.error(f"Failed to reconcile transaction {transaction_obj.id}: {e}")

        self.stdout.write(self.style.SUCCESS("--- Reconciliation Summary ---"))
        self.stdout.write(self.style.SUCCESS(f"Total transactions: {total_transactions}"))
        self.stdout.write(self.style.SUCCESS(f"Reconciled successfully: {reconciled_count}"))
        self.stdout.write(self.style.ERROR(f"Errors encountered: {error_count}"))

        if error_count > 0:
            raise CommandError("Reconciliation completed with errors.")
        self.stdout.write(self.style.SUCCESS("Payment reconciliation completed successfully."))
