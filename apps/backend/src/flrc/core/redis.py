import asyncio
from weakref import WeakKeyDictionary

from redis.asyncio import Redis

from flrc.config import settings

# redis-py binds a connection pool to the event loop that first used it, so a
# single module-level client raises "Event loop is closed" the moment a second
# loop touches it. One client per running loop keeps the common single-loop
# server path unchanged while staying correct under pytest, the Celery worker,
# and anything else that runs more than one loop in a process.
_clients: WeakKeyDictionary[asyncio.AbstractEventLoop, Redis] = WeakKeyDictionary()


def client() -> Redis:
    loop = asyncio.get_running_loop()
    existing = _clients.get(loop)
    if existing is None:
        existing = Redis.from_url(settings.redis_url, decode_responses=True)
        _clients[loop] = existing
    return existing
