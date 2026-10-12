"""Bounded, structured input for creating vCard 3.0 contacts."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(max_length=16384)]
Label = Annotated[str, StringConstraints(max_length=80)]


class ContactFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def safe_text(cls, value):
        if isinstance(value, str) and any(ord(char) < 32 and char not in "\n\t" for char in value):
            raise ValueError("Contact text contains unsupported control characters")
        return value


class ContactValue(ContactFields):
    value: Annotated[str, StringConstraints(min_length=1, max_length=1024)]
    label: Label = ""

    @field_validator("value")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Contact value must not be blank")
        return value


class PostalAddress(ContactFields):
    label: Label = ""
    po_box: Text = ""
    extended: Text = ""
    street: Text = ""
    city: Text = ""
    region: Text = ""
    postal_code: Text = ""
    country: Text = ""

    @model_validator(mode="after")
    def meaningful(self):
        if not any(getattr(self, key).strip() for key in type(self).model_fields if key != "label"):
            raise ValueError("Postal address must contain an address field")
        return self


class ContactInput(ContactFields):
    display_name: Text = ""
    given_name: Text = ""
    family_name: Text = ""
    additional_name: Text = ""
    name_prefix: Text = ""
    name_suffix: Text = ""
    organization: Text = ""
    emails: list[ContactValue] = Field(default_factory=list, max_length=50)
    phones: list[ContactValue] = Field(default_factory=list, max_length=50)
    addresses: list[PostalAddress] = Field(default_factory=list, max_length=20)
    birthday: Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")] | None = None
    notes: Text = ""

    @field_validator("birthday")
    @classmethod
    def real_date(cls, value: str | None) -> str | None:
        if value is not None:
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def meaningful(self):
        if not any(value.strip() for value in (
            self.display_name, self.given_name, self.family_name, self.additional_name, self.organization,
        )):
            raise ValueError("A contact needs a name or organization")
        return self
