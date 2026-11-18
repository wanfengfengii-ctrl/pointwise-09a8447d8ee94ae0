from collections.abc import Sequence
from sqlite3 import Connection

from .definition import LayoutRevision, Stage
from .repository import LayoutRepository
from .validation import validate_layout


class UnknownLayoutRevision(LookupError):
    """The requested published topology is absent."""


def save_layout(db: Connection, stages: Sequence[Stage]) -> int:
    validated = validate_layout(db, stages)
    return LayoutRepository(db).insert_revision(validated)


def load_layout_revision(db: Connection, revision_id: int) -> LayoutRevision:
    layout = LayoutRepository(db).find_revision(revision_id)
    if layout is None:
        raise UnknownLayoutRevision(f'unknown layout revision {revision_id!r}')
    return layout
