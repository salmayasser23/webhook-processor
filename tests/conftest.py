import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_app
from app.models import Base


class AsyncSessionAdapter:
    def __init__(self, factory):
        self._session = factory()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self._session.close()

    async def get(self, *args, **kwargs):
        return self._session.get(*args, **kwargs)

    async def execute(self, *args, **kwargs):
        return self._session.execute(*args, **kwargs)

    def add(self, record):
        self._session.add(record)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sync_factory = sessionmaker(engine, class_=Session, expire_on_commit=False)

    def make_session():
        return AsyncSessionAdapter(sync_factory)

    test_app = create_app(session_factory=make_session, processing_delay_seconds=0)
    with TestClient(test_app) as test_client:
        yield test_client
    engine.dispose()
