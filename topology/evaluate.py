from collections.abc import Mapping
from dataclasses import dataclass

from .definition import LayoutRevision


@dataclass(frozen=True)
class StagePassage:
    stage_name: str
    available_routes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return bool(self.available_routes)


@dataclass(frozen=True)
class LayoutPassage:
    stages: tuple[StagePassage, ...]
    line_passes: bool


def evaluate_layout(layout: LayoutRevision, states: Mapping[str, bool]) -> LayoutPassage:
    """Evaluate a published topology against one validated, complete assignment."""
    stages = []
    for stage in layout.stages:
        available_routes = tuple(
            route.name
            for route in stage.routes
            if all(states[reference.asset_id] for reference in route.components)
        )
        stages.append(StagePassage(stage.name, available_routes))
    return LayoutPassage(tuple(stages), all(stage.passed for stage in stages))
