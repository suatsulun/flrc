"""Temporary public-demo administrators (ADR-051).

Active only when ``ENV=demo`` and ``DEMO_PUBLIC_LOGIN=true``. Any verified
Google account becomes an administrator of the shared fictional school for at
most 24 hours. Google's stable subject is never stored: a keyed hash links the
visitor row to the account so a repeat login reuses it while a session is
alive, and scrubbing removes even that link. Rows are physically deleted by
the demo reset; school mode never creates them.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import structlog
from redis.exceptions import RedisError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from flrc.config import settings
from flrc.core.redis import client
from flrc.db.models import DemoVisitor, User
from flrc.modules.auth import sessions
from flrc.modules.auth.policy import allowed_google_domain

log = structlog.get_logger()

VISITOR_LIFETIME = timedelta(hours=24)
# Unambiguous lowercase characters for the generated visitor tag.
_TAG_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_TAG_LENGTH = 5


class VisitorLimitReached(Exception):
    """Today's cap on new visitor accounts is exhausted."""


def enabled() -> bool:
    return settings.demo_visitors_enabled()


def subject_hash(subject: str) -> str:
    """Keyed, one-way pseudonym of Google's ``sub``; meaningless without the secret."""
    return hmac.new(
        settings.session_secret.encode(),
        f"demo-visitor:{subject}".encode(),
        hashlib.sha256,
    ).hexdigest()


def session_ttl(visitor: DemoVisitor) -> int:
    """Seconds left until the visitor's absolute expiry, at least one."""
    return max(1, int((visitor.expires_at - _now()).total_seconds()))


async def login_visitor(db: AsyncSession, subject: str) -> tuple[User, str]:
    """Reuse the live account for this Google identity or create a fresh one.

    Returns the user and a new session id. The advisory lock serializes
    simultaneous logins of one identity (two tabs at once) so they cannot both
    create an account, and the session is created before the commit so the
    second login already sees the first one as alive.
    """
    digest = subject_hash(subject)
    now = _now()
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _lock_key(digest)})
    result = await db.execute(
        select(User, DemoVisitor)
        .join(DemoVisitor, DemoVisitor.user_id == User.id)
        .where(DemoVisitor.subject_hash == digest)
    )
    pair = result.one_or_none()
    if pair is not None:
        user, visitor = pair
        alive = (
            user.is_active
            and visitor.expires_at > now
            and await sessions.live_session_count(user.id) > 0
        )
        if alive:
            sid = await sessions.create_session(user.id, ttl=session_ttl(visitor))
            await db.commit()
            return user, sid
        await sessions.revoke_user_sessions(user.id)
        _scrub(visitor, user)
        await db.flush()

    if await _new_visitors_today() > settings.demo_visitor_limit_per_day:
        await db.rollback()
        raise VisitorLimitReached

    tag = _tag()
    user = User(
        email=f"visitor-{tag}@{allowed_google_domain()}",
        full_name=f"Demo Admin {tag.upper()}",
        is_admin=True,
        is_coordinator=True,
        teaching_field="english",
        teaching_stage="middle",
    )
    db.add(user)
    await db.flush()
    visitor = DemoVisitor(user_id=user.id, subject_hash=digest, expires_at=now + VISITOR_LIFETIME)
    db.add(visitor)
    await db.flush()
    sid = await sessions.create_session(user.id, ttl=session_ttl(visitor))
    await db.commit()
    return user, sid


async def release_visitor(db: AsyncSession, user_id: int) -> None:
    """After a session ends: scrub the account once no live session remains."""
    result = await db.execute(
        select(User, DemoVisitor)
        .join(DemoVisitor, DemoVisitor.user_id == User.id)
        .where(DemoVisitor.user_id == user_id, DemoVisitor.scrubbed_at.is_(None))
    )
    pair = result.one_or_none()
    if pair is None or await sessions.live_session_count(user_id) > 0:
        return
    user, visitor = pair
    _scrub(visitor, user)
    await db.commit()


async def is_visitor(db: AsyncSession, user_id: int) -> bool:
    if not enabled():
        return False
    found = await db.scalar(select(DemoVisitor.user_id).where(DemoVisitor.user_id == user_id))
    return found is not None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _tag() -> str:
    return "".join(secrets.choice(_TAG_ALPHABET) for _ in range(_TAG_LENGTH))


def _lock_key(digest: str) -> int:
    # Fits PostgreSQL's signed 64-bit advisory-lock key.
    return int(digest[:15], 16)


def _scrub(visitor: DemoVisitor, user: User) -> None:
    """Drop the identity link and deactivate; the caller commits."""
    visitor.subject_hash = None
    visitor.scrubbed_at = _now()
    user.is_active = False
    user.email = f"deleted-visitor-{user.id}@{allowed_google_domain()}"
    user.full_name = "Deleted visitor"


async def _new_visitors_today() -> int:
    key = f"demo:visitors:{_now():%Y-%m-%d}"
    try:
        async with client().pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, 2 * 24 * 60 * 60)
            count, _ = await pipe.execute()
    except RedisError:
        log.warning("demo_visitor_counter_unavailable")
        return 0
    return int(count)
