"""
Generate secure secrets for production deployment.

This script generates:
- SETTINGS_ADMIN_TOKEN: A secure random token for settings page protection
- SETTINGS_ENCRYPTION_KEY: A Fernet encryption key for encrypting secret settings

Usage:
    python generate_secrets.py
"""

import secrets
try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: cryptography package not installed.")
    print("Install it with: pip install cryptography")
    exit(1)


def generate_secrets():
    """Generate secure tokens and encryption keys"""

    print("=" * 60)
    print("SECURE SECRETS GENERATOR")
    print("=" * 60)
    print()

    # Generate admin token
    admin_token = secrets.token_urlsafe(32)
    print("SETTINGS_ADMIN_TOKEN:")
    print(admin_token)
    print()

    # Generate encryption key
    encryption_key = Fernet.generate_key().decode()
    print("SETTINGS_ENCRYPTION_KEY:")
    print(encryption_key)
    print()

    print("=" * 60)
    print("IMPORTANT SECURITY NOTES:")
    print("=" * 60)
    print()
    print("1. Add these values to your environment variables:")
    print("   - In .env file for local development")
    print("   - In Render dashboard for production deployment")
    print()
    print("2. Never commit these values to Git")
    print("3. Keep them secure and do not share them")
    print("4. Generate new values if these are ever compromised")
    print()
    print("5. For Render deployment:")
    print("   - Go to your service settings")
    print("   - Add these as Environment Variables")
    print("   - SETTINGS_ADMIN_TOKEN: " + admin_token)
    print("   - SETTINGS_ENCRYPTION_KEY: " + encryption_key)
    print()


if __name__ == "__main__":
    generate_secrets()
