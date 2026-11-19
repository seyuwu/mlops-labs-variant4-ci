import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./platform.db')
options = {}
if DATABASE_URL.startswith('sqlite'):
    options['connect_args'] = {'check_same_thread': False}
    if ':memory:' in DATABASE_URL:
        options['poolclass'] = StaticPool
engine = create_engine(DATABASE_URL, pool_pre_ping=True, **options)
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session
