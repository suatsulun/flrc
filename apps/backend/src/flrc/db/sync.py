from sqlalchemy import Engine, create_engine

from flrc.config import settings


def sync_engine() -> Engine:
    url = settings.database_url_direct.replace("+asyncpg", "+psycopg").replace(
        "ssl=require", "sslmode=require"
    )
    return create_engine(
        url,
        pool_pre_ping=True,
    )
