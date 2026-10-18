"""Concrete, bounded MIME attachment input for draft tools."""

from pydantic import BaseModel, ConfigDict, Field


class DraftAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    filename: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    content_type: str = "application/octet-stream"
