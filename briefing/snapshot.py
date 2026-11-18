from dataclasses import dataclass

from analysis.diagnosis import ReplayResult
from analysis.reconcile import ReadingDifference
from topology.definition import Route


@dataclass(frozen=True)
class BriefStage:
    name: str
    routes: tuple[Route, ...]
    reading: bool | None
    available_routes: tuple[str, ...]
    passed: bool


@dataclass(frozen=True)
class BriefSnapshot:
    incident_id: int
    incident_key: str
    layout_revision_id: int
    observation_revision_id: int
    stages: tuple[BriefStage, ...]
    component_states: tuple[tuple[str, bool], ...]
    line_passes: bool
    blocked_stages: tuple[str, ...]
    differences: tuple[ReadingDifference, ...]


def capture_snapshot(replay: ReplayResult) -> BriefSnapshot:
    context = replay.context
    readings = dict(context.observations.readings)
    passage_by_stage = {stage.stage_name: stage for stage in replay.passage.stages}
    stages = []
    for stage in context.layout.stages:
        passage = passage_by_stage[stage.name]
        stages.append(BriefStage(
            name=stage.name,
            routes=stage.routes,
            reading=readings.get(stage.name),
            available_routes=passage.available_routes,
            passed=passage.passed,
        ))
    return BriefSnapshot(
        incident_id=context.incident.incident_id,
        incident_key=context.observations.incident_key,
        layout_revision_id=context.incident.layout_revision_id,
        observation_revision_id=context.incident.observation_revision_id,
        stages=tuple(stages),
        component_states=replay.state_vector.entries,
        line_passes=replay.passage.line_passes,
        blocked_stages=replay.blocked_stages,
        differences=replay.differences,
    )
