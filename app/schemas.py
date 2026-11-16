from datetime import UTC, datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

ShortText = Annotated[str, Field(min_length=1, max_length=128)]


class AlertIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_id: ShortText
    source: ShortText
    message: Annotated[str, Field(min_length=1, max_length=5000)]
    timestamp: AwareDatetime

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class AlertOut(BaseModel):
    event_id: str
    source: str
    message: str
    timestamp: datetime
    processed_at: datetime
