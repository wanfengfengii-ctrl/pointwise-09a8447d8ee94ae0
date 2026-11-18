from dataclasses import dataclass


@dataclass(frozen=True)
class ObservationRevision:
    revision_id: int
    incident_key: str
    layout_revision_id: int
    readings: tuple[tuple[str, bool], ...]

    def reading_for(self, stage_name: str) -> bool | None:
        for name, reading in self.readings:
            if name == stage_name:
                return reading
        return None


@dataclass(frozen=True)
class FrozenIncident:
    incident_id: int
    layout_revision_id: int
    observation_revision_id: int


@dataclass(frozen=True)
class CarryRecord:
    derived_observation_id: int
    source_observation_id: int
    old_layout_id: int
    new_layout_id: int
    matches: tuple[tuple[str, str, bool], ...]
