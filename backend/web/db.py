import os
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor, Json

DSN = os.getenv('KNOWLEDGE_DATABASE_URL', 'dbname=knowledge_agent host=/tmp')

@contextmanager
def transaction():
    connection = psycopg2.connect(DSN)
    try:
        with connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cur:
                yield cur
    finally:
        connection.close()

def rows(sql, args=()):
    with transaction() as cur:
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

def one(sql, args=()):
    result = rows(sql, args)
    return result[0] if result else None
