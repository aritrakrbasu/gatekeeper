import os
import base64
from cryptography.fernet import Fernet

# Retrieve secret master key from environment, or use a stable fallback for development.
# Fernet key must be a 32 URL-safe base64-encoded bytes key.
raw_key = os.getenv("GATEKEEPER_ENCRYPTION_KEY", "gatekeeper-dev-secret-key-32-len")

try:
    # Try parsing the raw_key directly as url-safe base64 of 32 bytes
    decoded = base64.urlsafe_b64decode(raw_key)
    if len(decoded) == 32:
        fernet_key = raw_key.encode()
    else:
        # Generate a stable key by padding/truncating to 32 bytes and base64-encoding
        derived = raw_key.encode().ljust(32, b'\0')[:32]
        fernet_key = base64.urlsafe_b64encode(derived)
except Exception:
    derived = raw_key.encode().ljust(32, b'\0')[:32]
    fernet_key = base64.urlsafe_b64encode(derived)

fernet = Fernet(fernet_key)

def encrypt_value(value: str) -> str:
    """Encrypt a string value using Fernet symmetric encryption."""
    if not value:
        return ""
    try:
        return fernet.encrypt(value.encode()).decode()
    except Exception as e:
        print(f"[ERROR] Encryption failed: {e}")
        return value

def decrypt_value(value: str) -> str:
    """Decrypt a string value using Fernet symmetric encryption."""
    if not value:
        return ""
    try:
        return fernet.decrypt(value.encode()).decode()
    except Exception as e:
        # If decryption fails (e.g. invalid key or already plain text), return the original value
        print(f"[ERROR] Decryption failed: {e}")
        return value
