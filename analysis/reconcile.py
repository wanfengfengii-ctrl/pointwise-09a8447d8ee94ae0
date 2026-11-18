from dataclasses import dataclass

from evidence.records import ObservationRevision
from topology.evaluate import LayoutPassage


@dataclass(frozen=True)
class ReadingDifference:
    stage_name: str
    observed: bool
    computed: bool


def find_reading_differences(observations: ObservationRevision,
                             passage: LayoutPassage) -> tuple[ReadingDifference, ...]:
    readings = dict(observations.readings)
    differences = []
    for stage in passage.stages:
        observed = readings.get(stage.stage_name)
        if observed is not None and observed != stage.passed:
            differences.append(ReadingDifference(stage.stage_name, observed, stage.passed))
    return tuple(differences)
