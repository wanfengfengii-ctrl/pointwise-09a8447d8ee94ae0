from sqlite3 import Connection

from evidence.freeze import load_incident
from topology.evaluate import evaluate_layout

from .diagnosis import ReplayResult, build_diagnosis
from .reconcile import find_reading_differences
from .state_vector import StateInput, validate_state_vector


def replay_incident(db: Connection, incident_id: int, component_states: StateInput) -> ReplayResult:
    context = load_incident(db, incident_id)
    state_vector = validate_state_vector(context.layout, component_states)
    passage = evaluate_layout(context.layout, state_vector.as_mapping())
    differences = find_reading_differences(context.observations, passage)
    return build_diagnosis(context, state_vector, passage, differences)
