from sqlite3 import Connection

from .payload import decode_brief_payload
from .repository import BriefRepository
from .snapshot import BriefSnapshot


class UnknownBrief(LookupError):
    """No committed brief has the requested number."""


def read_brief(db: Connection, brief_id: int) -> BriefSnapshot:
    payload = BriefRepository(db).find_payload(brief_id)
    if payload is None:
        raise UnknownBrief(f'unknown brief {brief_id!r}')
    return decode_brief_payload(payload)
