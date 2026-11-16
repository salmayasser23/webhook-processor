import asyncio
import logging
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models import AlertRecord
from app.schemas import AlertIn, AlertOut

logger = logging.getLogger("uvicorn.error")


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_response(record: AlertRecord) -> AlertOut:
    return AlertOut(
        event_id=record.event_id,
        source=record.source,
        message=record.message,
        timestamp=as_utc(record.timestamp),
        processed_at=as_utc(record.processed_at),
    )


def payload_matches(record: AlertRecord, incoming: AlertIn) -> bool:
    return (
        record.source == incoming.source
        and record.message == incoming.message
        and as_utc(record.timestamp) == incoming.timestamp
    )


def resolved_duplicate(record: AlertRecord, incoming: AlertIn) -> tuple[AlertOut, bool]:
    if not payload_matches(record, incoming):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="event_id already exists with a different payload",
        )
    logger.info("Duplicate alert recognized event_id=%s", incoming.event_id)
    return to_response(record), False


def database_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Database temporarily unavailable",
    )


async def process_alert(
    session_factory, incoming: AlertIn, delay_seconds: float
) -> tuple[AlertOut, bool]:
    try:
        async with session_factory() as session:
            current = await session.get(AlertRecord, incoming.event_id)
            if current is not None:
                return resolved_duplicate(current, incoming)
    except SQLAlchemyError as exc:
        logger.exception("Failed to check event_id=%s", incoming.event_id)
        raise database_unavailable() from exc

    await asyncio.sleep(delay_seconds)

    record = AlertRecord(
        event_id=incoming.event_id,
        source=incoming.source,
        message=incoming.message,
        timestamp=incoming.timestamp,
        processed_at=datetime.now(UTC),
    )

    try:
        async with session_factory() as session:
            session.add(record)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                current = await session.get(AlertRecord, incoming.event_id)
                if current is None:
                    logger.error(
                        "Integrity error without event row event_id=%s",
                        incoming.event_id,
                    )
                    raise database_unavailable()
                return resolved_duplicate(current, incoming)
        logger.info("Processed and saved event_id=%s", incoming.event_id)
        return to_response(record), True
    except SQLAlchemyError as exc:
        logger.exception("Failed to save event_id=%s", incoming.event_id)
        raise database_unavailable() from exc
