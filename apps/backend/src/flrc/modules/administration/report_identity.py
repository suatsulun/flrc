"""Validation and atomic audit for a teacher's printed identity."""

import hashlib
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.db.models import ReportIdentityAudit, User

MAX_SIGNATURE_BYTES = 1024 * 1024
MAX_SIGNATURE_DIMENSION = 4096
MAX_SIGNATURE_PIXELS = 4_000_000


def validate_signature(data: bytes) -> bytes:
    """Decode a bounded, single-frame PNG and re-encode without metadata.

    File names and browser MIME types cannot establish that a file is a PNG.
    Limit dimensions before decoding, verify checksums, and retain the exact
    pixel content (including transparency) without EXIF or appended payloads.
    """
    if not data or len(data) > MAX_SIGNATURE_BYTES:
        raise ValueError("signature_too_large")
    try:
        with Image.open(BytesIO(data), formats=["PNG"]) as source:
            width, height = source.size
            if (
                max(width, height) > MAX_SIGNATURE_DIMENSION
                or width * height > MAX_SIGNATURE_PIXELS
            ):
                raise ValueError("signature_dimensions")
            if getattr(source, "n_frames", 1) != 1:
                raise ValueError("signature_invalid_png")
            source.verify()
        with Image.open(BytesIO(data), formats=["PNG"]) as source:
            pixels = source.convert("RGBA")
            if pixels.getbbox() is None:
                raise ValueError("signature_empty")
            # A fresh image prevents source metadata being copied on save.
            clean = Image.frombytes("RGBA", pixels.size, pixels.tobytes())
            out = BytesIO()
            clean.save(out, format="PNG")
    except (OSError, UnidentifiedImageError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("signature_invalid_png") from exc
    result = out.getvalue()
    if len(result) > MAX_SIGNATURE_BYTES:
        raise ValueError("signature_too_large")
    return result


def identity_snapshot(user: User) -> dict[str, str | None]:
    return {"report_name": user.report_name, "signature_digest": user.signature_digest}


def audit_identity(
    db: AsyncSession, user: User, actor: User, before: dict[str, str | None]
) -> None:
    after = identity_snapshot(user)
    if before != after:
        db.add(ReportIdentityAudit(user_id=user.id, actor_id=actor.id, before=before, after=after))


async def set_signature(db: AsyncSession, user: User, actor: User, png: bytes | None) -> None:
    before = identity_snapshot(user)
    user.signature_png = png
    user.signature_digest = hashlib.sha256(png).hexdigest() if png else None
    audit_identity(db, user, actor, before)
    await db.commit()
