"""One exact, inclusive scope shared by import, search, brief, and agent tools."""

from dataclasses import dataclass
from datetime import date

from .domain import Record


@dataclass(frozen=True)
class Scope:
    asset_id: str | None = None
    start: date | None = None
    end: date | None = None

    def select(self, records: list[Record]) -> list[Record]:
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be on or before end")
        return [
            record
            for record in records
            if (self.asset_id is None or record.asset_id == self.asset_id)
            and (self.start is None or record.event_date >= self.start)
            and (self.end is None or record.event_date <= self.end)
        ]
