"""age encryption for backup files (ADR-056).

The server holds the school's age identity so the monthly restore test can
prove the remote copy is readable; the recipient (public key) is all the
nightly dump needs. Both are X25519 age keys, interchangeable with age-keygen.
"""

from pathlib import Path

import pyrage

SECRET_PREFIX = "AGE-SECRET-KEY-"


def generate_identity() -> tuple[str, str]:
    """Return ``(identity, recipient)`` as age strings."""
    identity = pyrage.x25519.Identity.generate()
    return str(identity), str(identity.to_public())


def parse_identity(text: str) -> str:
    """Accept a bare key or an age-keygen file with comment lines."""
    for line in text.splitlines():
        candidate = line.strip()
        if candidate.startswith(SECRET_PREFIX):
            return candidate
    raise ValueError("age_identity_missing")


def encrypt_file(source: Path, target: Path, recipient: str) -> None:
    key = pyrage.x25519.Recipient.from_str(recipient.strip())
    target.write_bytes(pyrage.encrypt(source.read_bytes(), [key]))


def decrypt_file(source: Path, target: Path, identity: str) -> None:
    key = pyrage.x25519.Identity.from_str(parse_identity(identity))
    target.write_bytes(pyrage.decrypt(source.read_bytes(), [key]))
