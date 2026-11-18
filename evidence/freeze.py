from dataclasses import dataclass
from sqlite3 import Connection

from topology.definition import LayoutRevision
from topology.layout import UnknownLayoutRevision, load_layout_revision

from .records import FrozenIncident, ObservationRevision
from .repository import EvidenceRepository


class InvalidIncidentBinding(ValueError):
    """The selected parent revisions cannot identify one incident context."""


class UnknownIncident(LookupError):
    """No frozen incident has the requested number."""


@dataclass(frozen=True)
class IncidentContext:
    incident: FrozenIncident
    layout: LayoutRevision
    observations: ObservationRevision


def _resolve_parents(db: Connection, repository: EvidenceRepository, layout_revision_id: int,
                     observation_revision_id: int) -> tuple[LayoutRevision, ObservationRevision]:
    try:
        layout = load_layout_revision(db, layout_revision_id)
    except UnknownLayoutRevision as exc:
        raise InvalidIncidentBinding(f'unknown layout revision {layout_revision_id!r}') from exc
    observations = repository.find_observations(observation_revision_id)
    if observations is None:
        raise InvalidIncidentBinding(f'unknown observation revision {observation_revision_id!r}')
    if observations.layout_revision_id != layout.revision_id:
        raise InvalidIncidentBinding('observation and incident layout revisions differ')
    return layout, observations


def freeze_incident(db: Connection, layout_revision_id: int, observation_revision_id: int) -> int:
    repository = EvidenceRepository(db)
    layout, observations = _resolve_parents(db, repository, layout_revision_id, observation_revision_id)
    return repository.insert_incident(layout.revision_id, observations.revision_id)


def load_incident(db: Connection, incident_id: int) -> IncidentContext:
    repository = EvidenceRepository(db)
    incident = repository.find_incident(incident_id)
    if incident is None:
        raise UnknownIncident(f'unknown incident {incident_id!r}')
    layout, observations = _resolve_parents(
        db, repository, incident.layout_revision_id, incident.observation_revision_id,
    )
    return IncidentContext(incident, layout, observations)
