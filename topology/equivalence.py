from sqlite3 import Connection

from .definition import LayoutRevision, Stage
from .layout import load_layout_revision


def stage_terms(stage: Stage) -> frozenset[frozenset[str]]:
    """Return the canonical passage function of one stage.

    A stage passes when at least one route passes, and a route passes when all
    of its physical components are available.  Repeated occurrences of a
    component are the same boolean variable, so a route is a conjunction over
    the *set* of component IDs.  The minimal such sets (the antichain with
    supersets removed) determine the monotone function exactly, independent of
    stage names, route names, route order and asset revision numbers.
    """
    terms = {
        frozenset(reference.asset_id for reference in route.components)
        for route in stage.routes
    }
    return frozenset(
        term for term in terms if not any(other < term for other in terms)
    )


def equivalent_stages(left: Stage, right: Stage) -> bool:
    return stage_terms(left) == stage_terms(right)


def eligible_pairs_for_layouts(old_layout: LayoutRevision,
                               new_layout: LayoutRevision) -> tuple[tuple[str, str], ...]:
    """Return all semantic-equivalence pairs in old-major, new-minor order."""
    new_terms = tuple((stage.name, stage_terms(stage)) for stage in new_layout.stages)
    pairs = []
    for old_stage in old_layout.stages:
        old_terms = stage_terms(old_stage)
        for new_name, terms in new_terms:
            if terms == old_terms:
                pairs.append((old_stage.name, new_name))
    return tuple(pairs)


def eligible_stage_pairs(db: Connection, old_layout_id: int,
                         new_layout_id: int) -> tuple[tuple[str, str], ...]:
    """List every old/new stage pair with identical passage semantics."""
    old_layout = load_layout_revision(db, old_layout_id)
    new_layout = load_layout_revision(db, new_layout_id)
    return eligible_pairs_for_layouts(old_layout, new_layout)
