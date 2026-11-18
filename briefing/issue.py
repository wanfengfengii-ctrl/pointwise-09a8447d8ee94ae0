from sqlite3 import Connection

from analysis.replay import replay_incident
from analysis.state_vector import StateInput

from .payload import encode_brief_payload
from .repository import BriefRepository
from .snapshot import capture_snapshot


def issue_brief(db: Connection, incident_id: int, component_states: StateInput) -> int:
    replay = replay_incident(db, incident_id, component_states)
    snapshot = capture_snapshot(replay)
    payload = encode_brief_payload(snapshot)
    return BriefRepository(db).store(snapshot.incident_id, payload)
