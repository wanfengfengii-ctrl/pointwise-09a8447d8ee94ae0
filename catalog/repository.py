from collections.abc import Iterator
from contextlib import contextmanager
from fractions import Fraction
from sqlite3 import Connection

from .fractions import decode_availability, encode_availability


RevisionRow = tuple[int, str, str, Fraction]


@contextmanager
def write_transaction(db: Connection) -> Iterator[None]:
    """Own a write transaction and roll back a failed commit as well as a failed statement."""
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise


def is_revision_number(value: object) -> bool:
    return type(value) is int and 0 < value < (1 << 63)


class AssetRepository:
    def __init__(self, db: Connection):
        self.db = db

    def initialize(self) -> None:
        self.db.execute('PRAGMA foreign_keys = ON')
        with write_transaction(self.db):
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS asset_identity (
                    asset_id TEXT PRIMARY KEY NOT NULL
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS asset_revision (
                    revision_id INTEGER PRIMARY KEY,
                    asset_id TEXT NOT NULL REFERENCES asset_identity(asset_id),
                    description TEXT NOT NULL,
                    availability_numerator TEXT NOT NULL,
                    availability_denominator TEXT NOT NULL,
                    UNIQUE (asset_id, revision_id)
                )
            ''')

    def append_revision(self, asset_id: str, description: str, availability: Fraction) -> int:
        numerator, denominator = encode_availability(availability)
        with write_transaction(self.db):
            self.db.execute('''
                INSERT INTO asset_identity (asset_id) VALUES (?)
                ON CONFLICT (asset_id) DO NOTHING
            ''', (asset_id,))
            cursor = self.db.execute('''
                INSERT INTO asset_revision
                    (asset_id, description, availability_numerator, availability_denominator)
                VALUES (?, ?, ?, ?)
            ''', (asset_id, description, numerator, denominator))
            revision_id = cursor.lastrowid
        return revision_id

    def find_revision(self, revision_id: int) -> RevisionRow | None:
        if not is_revision_number(revision_id):
            return None
        row = self.db.execute('''
            SELECT revision_id, asset_id, description, availability_numerator, availability_denominator
            FROM asset_revision WHERE revision_id = ?
        ''', (revision_id,)).fetchone()
        return self._decode_row(row)

    def find_current_revision(self, asset_id: str) -> RevisionRow | None:
        if not isinstance(asset_id, str):
            return None
        row = self.db.execute('''
            SELECT revision_id, asset_id, description, availability_numerator, availability_denominator
            FROM asset_revision WHERE asset_id = ?
            ORDER BY revision_id DESC LIMIT 1
        ''', (asset_id,)).fetchone()
        return self._decode_row(row)

    @staticmethod
    def _decode_row(row) -> RevisionRow | None:
        if row is None:
            return None
        revision_id, asset_id, description, numerator, denominator = row
        return revision_id, asset_id, description, decode_availability(numerator, denominator)
