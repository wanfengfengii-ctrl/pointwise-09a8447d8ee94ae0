from sqlite3 import Connection

from catalog.repository import is_revision_number, write_transaction


class BriefRepository:
    def __init__(self, db: Connection):
        self.db = db

    def initialize(self) -> None:
        with write_transaction(self.db):
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS brief (
                    brief_id INTEGER PRIMARY KEY,
                    incident_id INTEGER NOT NULL REFERENCES frozen_incident(incident_id),
                    payload TEXT NOT NULL
                )
            ''')

    def store(self, incident_id: int, payload: str) -> int:
        with write_transaction(self.db):
            cursor = self.db.execute('''
                INSERT INTO brief (incident_id, payload) VALUES (?, ?)
            ''', (incident_id, payload))
            brief_id = cursor.lastrowid
        return brief_id

    def find_payload(self, brief_id: int) -> str | None:
        if not is_revision_number(brief_id):
            return None
        row = self.db.execute('SELECT payload FROM brief WHERE brief_id = ?', (brief_id,)).fetchone()
        return None if row is None else row[0]
