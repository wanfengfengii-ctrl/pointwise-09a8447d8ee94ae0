from sqlite3 import Connection

from topology.layout import load_layout_revision

from .repository import EvidenceRepository
from .validation import InvalidObservations, ReadingInput, validate_readings


def put_observations(db: Connection, incident_key: str, layout_revision_id: int,
                     readings: ReadingInput) -> int:
    if not isinstance(incident_key, str) or not incident_key.strip() or '\x00' in incident_key:
        raise InvalidObservations('incident key must be a nonempty string without NUL')
    layout = load_layout_revision(db, layout_revision_id)
    validated = validate_readings(layout, readings)
    return EvidenceRepository(db).append_observations(incident_key, layout.revision_id, validated)
