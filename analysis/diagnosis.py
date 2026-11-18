from dataclasses import dataclass

from evidence.freeze import IncidentContext
from topology.evaluate import LayoutPassage

from .reconcile import ReadingDifference
from .state_vector import StateVector


@dataclass(frozen=True)
class ReplayResult:
    context: IncidentContext
    state_vector: StateVector
    passage: LayoutPassage
    blocked_stages: tuple[str, ...]
    differences: tuple[ReadingDifference, ...]


def build_diagnosis(context: IncidentContext, state_vector: StateVector, passage: LayoutPassage,
                    differences: tuple[ReadingDifference, ...]) -> ReplayResult:
    blocked_stages = tuple(stage.stage_name for stage in passage.stages if not stage.passed)
    return ReplayResult(context, state_vector, passage, blocked_stages, differences)
