from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import AlertRecord
from app.schemas import AlertIn, AlertOut
from app.services import database_unavailable, process_alert, to_response


def create_app(session_factory=None, processing_delay_seconds=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = None
        if session_factory is None:
            settings = get_settings()
            engine = create_async_engine(settings.database_url, pool_pre_ping=True)
            application.state.sessions = async_sessionmaker(
                engine, expire_on_commit=False
            )
            application.state.delay = (
                settings.processing_delay_seconds
                if processing_delay_seconds is None
                else processing_delay_seconds
            )
        else:
            application.state.sessions = session_factory
            application.state.delay = (
                3.0 if processing_delay_seconds is None else processing_delay_seconds
            )
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    application = FastAPI(title="Webhook Processor", version="1.0.0", lifespan=lifespan)

    @application.post(
        "/webhook", response_model=AlertOut, status_code=status.HTTP_201_CREATED
    )
    async def webhook(incoming: AlertIn, response: Response):
        result, created = await process_alert(
            application.state.sessions,
            incoming,
            application.state.delay,
        )
        if not created:
            response.status_code = status.HTTP_200_OK
        return result

    @application.get("/alerts", response_model=list[AlertOut])
    async def get_alerts():
        try:
            async with application.state.sessions() as session:
                query = select(AlertRecord).order_by(
                    AlertRecord.processed_at.desc(), AlertRecord.event_id.desc()
                )
                result = await session.execute(query)
                records = result.scalars().all()
                return [to_response(record) for record in records]
        except SQLAlchemyError as exc:
            raise database_unavailable() from exc

    @application.get("/health")
    async def health():
        try:
            async with application.state.sessions() as session:
                await session.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise database_unavailable() from exc
        return {"status": "ok"}

    return application


app = create_app()
