#!/bin/bash

# Stripe CLI Setup Script for Payment System Testing
# This script installs Stripe CLI and sets up webhook forwarding for testing

echo "🔧 Setting up Stripe CLI for payment system testing..."

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install Stripe CLI
install_stripe_cli() {
    echo "📥 Installing Stripe CLI..."
    
    # For Linux (Ubuntu/Debian)
    if command_exists apt-get; then
        echo "Installing on Ubuntu/Debian..."
        curl -s https://packages.stripe.dev/api/security/keypair/stripe-cli-gpg/public | gpg --dearmor | sudo tee /usr/share/keyrings/stripe.gpg >/dev/null
        echo "deb [signed-by=/usr/share/keyrings/stripe.gpg] https://packages.stripe.dev/stripe-cli-debian-local stable main" | sudo tee -a /etc/apt/sources.list.d/stripe.list
        sudo apt update
        sudo apt install stripe
    
    # For macOS with Homebrew
    elif command_exists brew; then
        echo "Installing on macOS with Homebrew..."
        brew install stripe/stripe-cli/stripe
    
    # For other Linux distributions - direct download
    else
        echo "Installing via direct download..."
        STRIPE_VERSION=$(curl -s https://api.github.com/repos/stripe/stripe-cli/releases/latest | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
        curl -L "https://github.com/stripe/stripe-cli/releases/download/${STRIPE_VERSION}/stripe_linux_x86_64.tar.gz" -o /tmp/stripe_cli.tar.gz
        tar -xzf /tmp/stripe_cli.tar.gz -C /tmp
        sudo mv /tmp/stripe /usr/local/bin/
        rm /tmp/stripe_cli.tar.gz
    fi
    
    echo "✅ Stripe CLI installed successfully!"
}

# Check if Stripe CLI is already installed
if command_exists stripe; then
    echo "✅ Stripe CLI is already installed"
    stripe --version
else
    install_stripe_cli
fi

echo ""
echo "🔐 Next steps for setup:"
echo "1. Login to Stripe CLI:"
echo "   stripe login"
echo ""
echo "2. Forward webhooks to your local server:"
echo "   stripe listen --forward-to localhost:8001/api/payments/stripe_webhook/"
echo ""
echo "3. Copy the webhook signing secret and add it to your .env file:"
echo "   STRIPE_WEBHOOK_SECRET=whsec_..."
echo ""
echo "4. Test webhook forwarding:"
echo "   stripe trigger payment_intent.succeeded"
echo ""
echo "📋 Available test commands:"
echo "   • Test successful payment: stripe trigger payment_intent.succeeded"
echo "   • Test failed payment: stripe trigger payment_intent.payment_failed"
echo "   • Test account updated: stripe trigger account.updated"
echo "   • Test transfer created: stripe trigger transfer.created"
echo ""
echo "🧪 Run the webhook tests:"
echo "   python manage.py test payment_system.testing.test_webhooks"