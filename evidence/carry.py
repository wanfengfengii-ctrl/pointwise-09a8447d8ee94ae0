from sqlite3 import Connection

from catalog.repository import is_revision_number
from topology.equivalence import eligible_pairs_for_layouts
from topology.layout import load_layout_revision

from .alignment import unambiguous_pairs
from .records import CarryRecord, ObservationRevision
from .repository import EvidenceRepository


class UnknownObservation(LookupError):
    """The requested observation batch is absent or not a revision number."""


class UnknownCarry(LookupError):
    """The requested batch is not a published carry derivation."""


def _require_observations(repository: EvidenceRepository, revision_id: int) -> ObservationRevision:
    observations = repository.find_observations(revision_id) if is_revision_number(revision_id) else None
    if observations is None:
        raise UnknownObservation(f'unknown observation revision {revision_id!r}')
    return observations


def carried_matches(source: ObservationRevision, old_layout, new_layout) -> tuple[tuple[str, str, bool], ...]:
    """Carry explicit source readings across the unambiguous stage pairs.

    ``False`` is an explicit reading and is carried like ``True``.  A pair whose
    old stage has no explicit reading carries nothing and stays unobserved.  The
    result is ordered by the new layout's stage order.
    """
    eligible = eligible_pairs_for_layouts(old_layout, new_layout)
    pinned = unambiguous_pairs(
        tuple(stage.name for stage in old_layout.stages),
        tuple(stage.name for stage in new_layout.stages),
        eligible,
    )
    readings = dict(source.readings)
    new_order = {stage.name: index for index, stage in enumerate(new_layout.stages)}
    carried = [
        (old_name, new_name, readings[old_name])
        for old_name, new_name in pinned
        if readings.get(old_name) is not None
    ]
    carried.sort(key=lambda item: new_order[item[1]])
    return tuple(carried)


def carry_observations(db: Connection, source_observation_id: int, new_layout_id: int) -> int:
    """Register a derived batch in the target layout and return its number.

    The source batch is left untouched.  The derived batch keeps the source
    incident key and can be frozen with ``freeze_incident`` directly.
    """
    repository = EvidenceRepository(db)
    source = _require_observations(repository, source_observation_id)
    new_layout = load_layout_revision(db, new_layout_id)
    old_layout = load_layout_revision(db, source.layout_revision_id)
    return repository.append_carry(
        source,
        old_layout.revision_id,
        new_layout.revision_id,
        carried_matches(source, old_layout, new_layout),
    )


def read_carry(db: Connection, derived_observation_id: int) -> dict:
    """Read the fixed source numbers and matches of a published carry batch.

    The numbers and matches are read back as stored; the topology is not
    re-compared and the alignment is not recomputed.
    """
    record = _find_carry(db, derived_observation_id)
    return {
        'source_observation_id': record.source_observation_id,
        'old_layout_id': record.old_layout_id,
        'new_layout_id': record.new_layout_id,
        'matches': record.matches,
    }


def _find_carry(db: Connection, derived_observation_id: int) -> CarryRecord:
    record = EvidenceRepository(db).find_carry(derived_observation_id)
    if record is None:
        raise UnknownCarry(f'unknown carry batch {derived_observation_id!r}')
    return record
