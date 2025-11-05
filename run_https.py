#!/usr/bin/env python3
"""
Run Django development server with HTTPS support
Usage: python run_https.py
"""
import os
import sys
import logging
from pathlib import Path

# Add the project directory to Python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'designiaBackend.settings')

# Import Django management command
import django
from django.core.management import execute_from_command_line

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    # SSL certificate paths (relative to project root)
    cert_dir = BASE_DIR.parent / 'certs'
    cert_file = cert_dir / 'cert.pem'
    key_file = cert_dir / 'key.pem'

    # Check if certificates exist
    if not cert_file.exists() or not key_file.exists():
        logger.error("ERROR: SSL certificates not found!")
        logger.error(f"Expected cert: {cert_file}")
        logger.error(f"Expected key: {key_file}")
        logger.info("\nPlease generate certificates first:")
        logger.info("cd ../certs && openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes")
        sys.exit(1)

    # Run Django with HTTPS
    logger.info("Starting Django HTTPS server...")
    logger.info(f"Using cert: {cert_file}")
    logger.info(f"Using key: {key_file}")
    logger.info("Server will be available at: https://0.0.0.0:8001")
    logger.info("Access via: https://192.168.3.2:8001 or https://localhost:8001")
    logger.info("\nNote: You may see browser security warnings with self-signed certificates.")
    logger.info("This is normal for development. Click 'Advanced' and 'Proceed' to continue.\n")

    # Use Daphne ASGI server with HTTPS support
    try:
        import daphne
        import subprocess

        # Use --port and separate SSL arguments instead of endpoint string
        cmd = [
            'daphne',
            '--port', '8001',
            '--bind', '0.0.0.0',
            '--ssl-keyfile', str(key_file),
            '--ssl-certfile', str(cert_file),
            'designiaBackend.asgi:application'
        ]

        logger.info(f"Running: {' '.join(cmd)}\n")
        subprocess.run(cmd, check=True)

    except ImportError:
        logger.error("\nERROR: Daphne is not installed!")
        logger.info("Install it with: pip install daphne")
        logger.info("\nDaphne is required for ASGI + HTTPS support with Django Channels")
        sys.exit(1)
