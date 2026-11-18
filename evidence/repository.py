from sqlite3 import Connection

from catalog.repository import is_revision_number, write_transaction

from .records import FrozenIncident, ObservationRevision


class EvidenceRepository:
    def __init__(self, db: Connection):
        self.db = db

    def initialize(self) -> None:
        with write_transaction(self.db):
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS observation_revision (
                    revision_id INTEGER PRIMARY KEY,
                    incident_key TEXT NOT NULL,
                    layout_revision_id INTEGER NOT NULL REFERENCES layout_revision(revision_id),
                    UNIQUE (layout_revision_id, revision_id)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS observation_reading (
                    observation_revision_id INTEGER NOT NULL,
                    layout_revision_id INTEGER NOT NULL,
                    reading_position INTEGER NOT NULL,
                    stage_name TEXT NOT NULL,
                    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
                    PRIMARY KEY (observation_revision_id, reading_position),
                    UNIQUE (observation_revision_id, stage_name),
                    FOREIGN KEY (layout_revision_id, observation_revision_id)
                        REFERENCES observation_revision(layout_revision_id, revision_id),
                    FOREIGN KEY (layout_revision_id, stage_name)
                        REFERENCES layout_stage(layout_revision_id, stage_name)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS frozen_incident (
                    incident_id INTEGER PRIMARY KEY,
                    layout_revision_id INTEGER NOT NULL REFERENCES layout_revision(revision_id),
                    observation_revision_id INTEGER NOT NULL,
                    FOREIGN KEY (layout_revision_id, observation_revision_id)
                        REFERENCES observation_revision(layout_revision_id, revision_id)
                )
            ''')

    def append_observations(self, incident_key: str, layout_revision_id: int,
                            readings: tuple[tuple[str, bool], ...]) -> int:
        with write_transaction(self.db):
            cursor = self.db.execute('''
                INSERT INTO observation_revision (incident_key, layout_revision_id) VALUES (?, ?)
            ''', (incident_key, layout_revision_id))
            revision_id = cursor.lastrowid
            self.db.executemany('''
                INSERT INTO observation_reading
                    (observation_revision_id, layout_revision_id, reading_position, stage_name, passed)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                (revision_id, layout_revision_id, position, name, int(reading))
                for position, (name, reading) in enumerate(readings)
            ))
        return revision_id

    def find_observations(self, revision_id: int) -> ObservationRevision | None:
        if not is_revision_number(revision_id):
            return None
        row = self.db.execute('''
            SELECT incident_key, layout_revision_id FROM observation_revision WHERE revision_id = ?
        ''', (revision_id,)).fetchone()
        if row is None:
            return None
        incident_key, layout_revision_id = row
        readings = self.db.execute('''
            SELECT stage_name, passed FROM observation_reading WHERE observation_revision_id = ?
            ORDER BY reading_position
        ''', (revision_id,))
        return ObservationRevision(
            revision_id, incident_key, layout_revision_id,
            tuple((stage_name, bool(passed)) for stage_name, passed in readings),
        )

    def insert_incident(self, layout_revision_id: int, observation_revision_id: int) -> int:
        with write_transaction(self.db):
            cursor = self.db.execute('''
                INSERT INTO frozen_incident (layout_revision_id, observation_revision_id)
                VALUES (?, ?)
            ''', (layout_revision_id, observation_revision_id))
            incident_id = cursor.lastrowid
        return incident_id

    def find_incident(self, incident_id: int) -> FrozenIncident | None:
        if not is_revision_number(incident_id):
            return None
        row = self.db.execute('''
            SELECT incident_id, layout_revision_id, observation_revision_id
            FROM frozen_incident WHERE incident_id = ?
        ''', (incident_id,)).fetchone()
        return None if row is None else FrozenIncident(*row)
