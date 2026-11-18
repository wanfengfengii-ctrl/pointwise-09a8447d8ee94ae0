from collections.abc import Iterable, Mapping

from topology.definition import LayoutRevision


class InvalidObservations(ValueError):
    """The batch does not describe valid readings for the selected topology."""


ReadingInput = Mapping[str, bool] | Iterable[tuple[str, bool]]


def validate_readings(layout: LayoutRevision, readings: ReadingInput) -> tuple[tuple[str, bool], ...]:
    stage_names = tuple(stage.name for stage in layout.stages)
    known_stages = set(stage_names)
    raw_items = readings.items() if isinstance(readings, Mapping) else readings
    try:
        items = iter(raw_items)
    except TypeError as exc:
        raise InvalidObservations('readings must be a mapping or an iterable of pairs') from exc

    accepted = {}
    for item in items:
        try:
            stage_name, reading = item
        except (TypeError, ValueError) as exc:
            raise InvalidObservations('each reading must be a stage and boolean pair') from exc
        if not isinstance(stage_name, str) or stage_name not in known_stages:
            raise InvalidObservations(f'unknown stage {stage_name!r}')
        if stage_name in accepted:
            raise InvalidObservations(f'duplicate reading for stage {stage_name!r}')
        if type(reading) is not bool:
            raise InvalidObservations(f'reading for {stage_name!r} must be a boolean')
        accepted[stage_name] = reading
    return tuple((name, accepted[name]) for name in stage_names if name in accepted)
