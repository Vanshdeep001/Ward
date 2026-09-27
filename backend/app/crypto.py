"""Encryption for the one secret Ward stores: the ExternalId a customer's trust policy requires.

The shape is what matters — ciphertext in the database, key outside it — so a dump of the `accounts`
table is useless on its own. Production should hold the key in KMS or put the value in Secrets
Manager and keep only its ARN in the row; this keeps the same property with a local key file so a
fresh install works with no setup.
"""
import logging
from base64 import urlsafe_b64encode
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

log = logging.getLogger('ward')


class SecretError(RuntimeError):
    """The stored ciphertext cannot be read with the key this process has."""


def _key() -> bytes:
    if settings.secret_key:
        key = settings.secret_key.encode()
        # Accept either a Fernet key or any 32-byte passphrase, so operators can set something typed.
        return key if len(key) == 44 else urlsafe_b64encode(key.ljust(32, b'0')[:32])

    path = Path(settings.secret_key_file)
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
        path.chmod(0o600)
        log.warning('Generated a local encryption key at %s. Set WARD_SECRET_KEY in production.', path)
    return path.read_bytes().strip()


def encrypt(plaintext: str) -> str:
    return Fernet(_key()).encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return Fernet(_key()).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretError(
            'Stored secret could not be decrypted — WARD_SECRET_KEY does not match the one that wrote it.'
        ) from exc
