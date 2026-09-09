import secrets

from flrc.config import settings
from flrc.core.redis import client


def _key(sid: str) -> str:
    return f"session:{sid}"


def _user_key(user_id: int) -> str:
    return f"user_sessions:{user_id}"


async def create_session(user_id: int, ttl: int | None = None) -> str:
    """Create a session; `ttl` may only shorten the configured absolute lifetime."""
    sid = secrets.token_urlsafe(32)
    lifetime = settings.session_ttl_seconds
    if ttl is not None:
        lifetime = max(1, min(ttl, lifetime))
    async with client().pipeline(transaction=True) as pipe:
        pipe.set(_key(sid), str(user_id), ex=lifetime)
        pipe.sadd(_user_key(user_id), sid)
        # The index outlives the longest session this deployment can issue, so
        # a later, shorter session never shortens an earlier one's revocation.
        pipe.expire(_user_key(user_id), settings.session_ttl_seconds + 3600)
        await pipe.execute()
    return sid


async def get_user_id(sid: str) -> int | None:
    value = await client().get(_key(sid))
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        await client().delete(_key(sid))
        return None


async def destroy_session(sid: str) -> int | None:
    """Delete one session and return its owner if the session existed."""
    value = await client().get(_key(sid))
    await client().delete(_key(sid))
    if value is None:
        return None
    try:
        user_id = int(value)
    except ValueError:
        return None
    await client().srem(_user_key(user_id), sid)
    return user_id


async def live_session_count(user_id: int) -> int:
    """Count sessions that still exist, pruning expired ids from the index."""
    index = _user_key(user_id)
    members = sorted(await client().smembers(index))
    if not members:
        return 0
    async with client().pipeline(transaction=False) as pipe:
        for member in members:
            pipe.exists(_key(str(member)))
        flags = await pipe.execute()
    dead = [member for member, flag in zip(members, flags, strict=True) if not flag]
    if dead:
        await client().srem(index, *dead)
    return len(members) - len(dead)


async def revoke_user_sessions(user_id: int) -> int:
    index = _user_key(user_id)
    members = await client().smembers(index)
    if not members:
        await client().delete(index)
        return 0
    deleted = await client().delete(*[_key(str(member)) for member in members])
    await client().delete(index)
    return int(deleted)


async def destroy_all_for_user(user_id: int) -> None:
    await revoke_user_sessions(user_id)
