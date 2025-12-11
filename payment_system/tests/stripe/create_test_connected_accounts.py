#!/usr/bin/env python3
"""
Stripe Connected Account Creation Script
========================================

This script creates multiple test Stripe connected accounts with different IBAN configurations
to simulate various payout scenarios for testing purposes.

Features:
- Creates custom connected accounts for Portugal (PT)
- Configures different test IBANs with expected behaviors
- Attaches external bank accounts for payout testing
- Comprehensive error handling and logging
- Account validation and status checks
- Detailed output for debugging

Usage:
    python create_test_connected_accounts.py

Requirements:
    - stripe library: pip install stripe
    - python-dotenv: pip install python-dotenv
    - STRIPE_SECRET_KEY in .env file

Security:
    - Uses test mode only (ensure test API key)
    - Creates sandbox accounts for testing
    - No real financial transactions
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

import stripe
from dotenv import load_dotenv


# Load environment variables
load_dotenv()

# Configuration
STRIPE_API_KEY = os.getenv("STRIPE_SECRET_KEY")
if not STRIPE_API_KEY:
    print(" ERROR: STRIPE_SECRET_KEY not found in environment variables")
    print("   Please add STRIPE_SECRET_KEY to your .env file")
    sys.exit(1)

# Verify it's a test key
if not STRIPE_API_KEY.startswith("sk_test_"):
    print(" ERROR: Not a test API key! This script only works with test keys.")
    print("   Found key starting with:", STRIPE_API_KEY[:10] + "...")
    sys.exit(1)

stripe.api_key = STRIPE_API_KEY

# Test bank accounts with expected payout behaviors
TEST_BANK_ACCOUNTS = {
    "PT50000201231234567890154": {
        "description": "Payout succeeds - Standard success case",
        "expected_behavior": "success",
        "currency": "eur",
    },
    "PT23000201231234567890155": {
        "description": "Payout fails with no_account",
        "expected_behavior": "failure_no_account",
        "currency": "eur",
    },
    "PT89370400440532013002": {
        "description": "Payout fails with account_closed",
        "expected_behavior": "failure_account_closed",
        "currency": "eur",
    },
    "w": {
        "description": "Payout fails with insufficient_funds",
        "expected_behavior": "failure_insufficient_funds",
        "currency": "eur",
    },
    "PT89370400440532013004": {
        "description": "Payout fails with debit_not_authorized",
        "expected_behavior": "failure_debit_not_authorized",
        "currency": "eur",
    },
    "PT89370400440532013005": {
        "description": "Payout fails with invalid_currency",
        "expected_behavior": "failure_invalid_currency",
        "currency": "eur",
    },
}

# Store created accounts for later reference
CREATED_ACCOUNTS: List[Dict] = []


def log_message(level: str, message: str) -> None:
    """Log messages with timestamp and level."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {level}: {message}")


def validate_stripe_connection() -> bool:
    """Validate Stripe API connection and account access."""
    try:
        log_message("INFO", "Validating Stripe API connection...")
        account = stripe.Account.retrieve()
        log_message("INFO", f"  Connected to Stripe account: {account.id}")
        log_message("INFO", f"   Country: {account.country}")
        log_message("INFO", f"   Email: {account.email or 'Not specified'}")
        return True
    except Exception as e:
        log_message("ERROR", f" Failed to connect to Stripe: {e}")
        return False


def create_connected_account(iban: str, config: Dict) -> Optional[Dict]:
    """
    Create a test connected account with the given IBAN and configuration.

    Args:
        iban: The IBAN to use for the external bank account
        config: Configuration dictionary with description and expected behavior

    Returns:
        Dictionary with account details if successful, None if failed
    """
    account_suffix = iban[-4:]  # Last 4 digits for unique identification

    try:
        log_message("INFO", f"Creating connected account for IBAN {iban}")
        log_message("INFO", f"   Description: {config['description']}")
        log_message("INFO", f"   Expected behavior: {config['expected_behavior']}")

        # Create connected account
        account = stripe.Account.create(
            type="custom",
            country="PT",
            email=f"test-{account_suffix}@designia-testing.com",
            business_type="individual",
            capabilities={
                "transfers": {"requested": True},
                "card_payments": {"requested": True},
            },
            business_profile={
                "name": f"Designia Test Account {account_suffix}",
                "mcc": "5734",  # Computer software stores
                "url": "https://designia-testing.com",
                "support_email": f"support-{account_suffix}@designia-testing.com",
            },
            individual={
                "first_name": "Test",
                "last_name": f"User{account_suffix}",
                "dob": {"day": 1, "month": 1, "year": 1990},
                "address": {
                    "line1": f"Rua de Teste {account_suffix}",
                    "city": "Lisboa",
                    "postal_code": "1000-000",
                    "country": "PT",
                },
                "email": f"individual-{account_suffix}@designia-testing.com",
                "phone": "+351912345678",
                # 🔑 These fields help auto-verify the account in test mode
                "id_number": "000000000",  # Generic test ID number
                "verification": {
                    "document": {
                        "front": "file_identity_document_success",  # Use Stripe test file ID
                    }
                },
            },
            tos_acceptance={"date": int(time.time()), "ip": "127.0.0.1"},
        )

        log_message("INFO", f"     Created account: {account.id}")

        # Wait a moment for account to be fully created
        time.sleep(1)

        # Attach external bank account
        log_message("INFO", "   Attaching external bank account...")
        external_account = stripe.Account.create_external_account(
            account.id,
            external_account={
                "object": "bank_account",
                "country": "PT",
                "currency": config["currency"],
                "account_holder_name": f"Test Holder {account_suffix}",
                "account_number": iban,
            },
        )

        log_message("INFO", f"     Attached bank account: {external_account.id}")

        # Retrieve full account details for verification
        full_account = stripe.Account.retrieve(account.id)

        account_details = {
            "account_id": account.id,
            "iban": iban,
            "external_account_id": external_account.id,
            "description": config["description"],
            "expected_behavior": config["expected_behavior"],
            "currency": config["currency"],
            "email": account.email,
            "status": full_account.charges_enabled,
            "payouts_enabled": full_account.payouts_enabled,
            "details_submitted": full_account.details_submitted,
            "created_at": datetime.now().isoformat(),
        }

        log_message(
            "INFO",
            f"   Account status - Charges: {full_account.charges_enabled}, Payouts: {full_account.payouts_enabled}",
        )

        return account_details

    except stripe.error.StripeError as e:
        log_message("ERROR", f"    Stripe error for IBAN {iban}: {e}")
        log_message("ERROR", f"      Error type: {type(e).__name__}")
        if hasattr(e, "code"):
            log_message("ERROR", f"      Error code: {e.code}")
        return None

    except Exception as e:
        log_message("ERROR", f"    Unexpected error for IBAN {iban}: {e}")
        log_message("ERROR", f"      Error type: {type(e).__name__}")
        return None


def verify_account_setup(account_details: Dict) -> bool:
    """
    Verify that the account was set up correctly.

    Args:
        account_details: Dictionary with account information

    Returns:
        True if account is properly configured, False otherwise
    """
    try:
        account_id = account_details["account_id"]
        log_message("INFO", f"Verifying account setup for {account_id}")

        # Retrieve account
        _account = stripe.Account.retrieve(account_id)

        # Check external accounts
        external_accounts = stripe.Account.list_external_accounts(account_id, object="bank_account")

        if len(external_accounts.data) == 0:
            log_message("ERROR", "    No external accounts found")
            return False

        bank_account = external_accounts.data[0]
        log_message("INFO", f"     Bank account verified: {bank_account.last4}")
        log_message("INFO", f"   Currency: {bank_account.currency}")
        log_message("INFO", f"   Status: {bank_account.status}")

        return True

    except Exception as e:
        log_message("ERROR", f"    Account verification failed: {e}")
        return False


def save_accounts_summary(accounts: List[Dict]) -> None:
    """Save created accounts summary to a JSON file."""
    try:
        summary_file = "/mnt/f/Nigger/Projects/Programmes/WebApps/Desginia/Designia-backend/payment_system/tests/stripe/created_accounts.json"

        summary = {
            "created_at": datetime.now().isoformat(),
            "total_accounts": len(accounts),
            "successful_accounts": len([a for a in accounts if a is not None]),
            "accounts": accounts,
        }

        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        log_message("INFO", f"  Account summary saved to: {summary_file}")

    except Exception as e:
        log_message("ERROR", f" Failed to save summary: {e}")


def print_usage_instructions(accounts: List[Dict]) -> None:
    """Print instructions on how to use the created accounts."""
    successful_accounts = [a for a in accounts if a is not None]

    print("\n" + "=" * 80)
    print("🎯 USAGE INSTRUCTIONS")
    print("=" * 80)
    print(f"Created {len(successful_accounts)} test connected accounts.")
    print("\nTo use these accounts in your tests:")
    print("1. Copy the account IDs below")
    print("2. Use them in your Django views/tests for Stripe transfers")
    print("3. Test different payout scenarios based on expected behaviors")

    print("\n📋 ACCOUNT SUMMARY:")
    print("-" * 80)

    for account in successful_accounts:
        print(f"Account ID: {account['account_id']}")
        print(f"IBAN: {account['iban']}")
        print(f"Expected Behavior: {account['expected_behavior']}")
        print(f"Description: {account['description']}")
        print(f"Email: {account['email']}")
        print("-" * 40)

    print("\n🔧 INTEGRATION EXAMPLE:")
    print("In your Django tests, use these account IDs:")
    print("```python")
    for account in successful_accounts[:2]:  # Show first 2 as examples
        print(f"# {account['description']}")
        print(f"test_account_id = '{account['account_id']}'")
        print()
    print("```")

    print("\n📁 FILES CREATED:")
    print("- created_accounts.json - Full account details")
    print("- This script can be run again to create fresh accounts")


def main():
    """Main execution function."""
    print("🚀 Stripe Connected Account Creation Script")
    print("=" * 60)
    print(f"Creating {len(TEST_BANK_ACCOUNTS)} test connected accounts...")
    print()

    # Validate Stripe connection
    if not validate_stripe_connection():
        sys.exit(1)

    print()
    log_message("INFO", "Starting account creation process...")

    # Create accounts
    for iban, config in TEST_BANK_ACCOUNTS.items():
        print("-" * 60)
        account_details = create_connected_account(iban, config)

        if account_details:
            # Verify the account setup
            if verify_account_setup(account_details):
                CREATED_ACCOUNTS.append(account_details)
                log_message("INFO", f"  Account {account_details['account_id']} ready for testing")
            else:
                log_message("ERROR", f" Account verification failed for {account_details['account_id']}")
                CREATED_ACCOUNTS.append(account_details)  # Still add it, but mark as potentially problematic
        else:
            log_message("ERROR", f" Failed to create account for IBAN {iban}")
            CREATED_ACCOUNTS.append(None)

        # Small delay between creations
        time.sleep(0.5)

    print("\n" + "=" * 60)
    log_message("INFO", "Account creation process completed")

    # Save summary
    save_accounts_summary(CREATED_ACCOUNTS)

    # Print usage instructions
    print_usage_instructions(CREATED_ACCOUNTS)

    # Final summary
    successful = len([a for a in CREATED_ACCOUNTS if a is not None])
    failed = len(CREATED_ACCOUNTS) - successful

    print("\n🎉 FINAL SUMMARY:")
    print(f"     Successfully created: {successful} accounts")
    print(f"    Failed: {failed} accounts")

    if failed > 0:
        print("\n⚠️  Some accounts failed to create. Check the logs above for details.")
        print("   You can re-run this script to try again.")

    print("\n🔐 SECURITY REMINDER:")
    print("   - These are TEST accounts only")
    print("   - Use only with test API keys")
    print("   - No real money will be transferred")
    print("   - Clean up accounts when testing is complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n Script interrupted by user")
        sys.exit(1)
    except Exception as e:
        log_message("ERROR", f" Unexpected error: {e}")
        sys.exit(1)
