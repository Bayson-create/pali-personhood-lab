from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Record:
    """One directly locatable search unit.

    The locator fields are intentionally explicit.  A result must be able to
    navigate back to immutable source data without storing a mutable copy in
    SQLite.
    """

    locator: str
    corpus: str
    resource_type: str = "corpus"
    work_id: str | None = None
    row_id: int | None = None
    uid: str | None = None
    segment_id: str | None = None
    author_uid: str | None = None
    translator: str | None = None
    paranum: str | None = None
    anchor: str | None = None
    path: list[str] = field(default_factory=list)
    title: str = ""
    text_zh: str = ""
    text_en: str = ""
    text_pali: str = ""
    source: str = ""
    version: str = ""
    source_ref: str | None = None
    source_url: str | None = None
    dictionary_table: str | None = None
    resource_locator: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Record":
        data = dict(value)
        data["path"] = list(data.get("path") or [])
        if data.get("row_id") is not None:
            data["row_id"] = int(data["row_id"])
        # Keep dataclass defaults for older shards that omit optional fields.
        fields = cls.__dataclass_fields__
        required = {"locator", "corpus"}
        kwargs = {name: data[name] for name in fields if name in data}
        missing = required - kwargs.keys()
        if missing:
            raise ValueError(f"record missing required fields: {sorted(missing)}")
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in self.__dataclass_fields__}

    @property
    def text_by_language(self) -> dict[str, str]:
        return {"zh": self.text_zh, "en": self.text_en, "pali": self.text_pali}

    @property
    def stable_key(self) -> str:
        # The persisted locator is already versioned and collision-free.  In
        # particular, Early-Buddhist Chinese rows include author_uid because
        # different legacy translations reuse uid+i.
        return self.locator
