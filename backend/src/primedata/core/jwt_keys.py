"""
JWT key management for PrimeData API.
"""

import base64
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from primedata.core.settings import get_settings


def get_keys_dir() -> Path:
    """Get the keys directory, creating it if it doesn't exist."""
    keys_dir = Path(__file__).parent.parent.parent.parent / "keys"
    keys_dir.mkdir(exist_ok=True)
    return keys_dir


def generate_keypair() -> tuple[str, str]:
    """Generate RSA keypair and return as PEM strings."""
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Get public key
    public_key = private_key.public_key()

    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")

    return private_pem, public_pem


def get_or_create_keypair() -> tuple[str, str]:
    """Get existing keypair or create new one."""
    keys_dir = get_keys_dir()
    private_key_path = keys_dir / "private_key.pem"
    public_key_path = keys_dir / "public_key.pem"

    if private_key_path.exists() and public_key_path.exists():
        # Load existing keys
        with open(private_key_path, "r") as f:
            private_pem = f.read()
        with open(public_key_path, "r") as f:
            public_pem = f.read()
        return private_pem, public_pem
    else:
        # Generate new keys
        private_pem, public_pem = generate_keypair()

        # Save keys
        with open(private_key_path, "w") as f:
            f.write(private_pem)
        with open(public_key_path, "w") as f:
            f.write(public_pem)

        return private_pem, public_pem


def sign_jwt(payload: Dict[str, Any], exp_s: int = 3600) -> str:
    """
    Sign JWT with RS256 algorithm.

    Args:
        payload: Data to encode in the token
        exp_s: Expiration time in seconds

    Returns:
        Encoded JWT token
    """
    settings = get_settings()
    private_pem, _ = get_or_create_keypair()
    private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)

    now = datetime.utcnow()
    to_encode = payload.copy()
    to_encode.update(
        {
            "exp": now + timedelta(seconds=exp_s),
            "iat": now,
            "nbf": now,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
    )

    encoded_jwt = jwt.encode(to_encode, private_key, algorithm="RS256", headers={"kid": "primedata-key-1"})
    return encoded_jwt


def get_jwks() -> Dict[str, Any]:
    """Get JWKS (JSON Web Key Set) for token verification."""
    try:
        _, public_pem = get_or_create_keypair()

        # Load public key
        public_key = serialization.load_pem_public_key(public_pem.encode("utf-8"))

        # Get key components
        public_numbers = public_key.public_numbers()

        # Convert to JWK format
        n = base64.urlsafe_b64encode(public_numbers.n.to_bytes(256, "big")).decode("utf-8").rstrip("=")

        e = base64.urlsafe_b64encode(public_numbers.e.to_bytes(3, "big")).decode("utf-8").rstrip("=")

        # Create JWK
        jwk = {"kty": "RSA", "use": "sig", "kid": "primedata-key-1", "n": n, "e": e, "alg": "RS256"}

        return {"keys": [jwk]}

    except Exception as e:
        # Return empty JWKS on error
        return {"keys": []}


def get_public_jwks() -> dict:
    """Get public JWKS for JWT key discovery."""
    return get_jwks()
