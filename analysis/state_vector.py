from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from topology.definition import LayoutRevision


class InvalidStateVector(ValueError):
    """The submitted actual states do not identify one complete assignment."""


StateInput = Mapping[str, bool] | Iterable[tuple[str, bool]]


@dataclass(frozen=True)
class StateVector:
    entries: tuple[tuple[str, bool], ...]

    def as_mapping(self) -> dict[str, bool]:
        return dict(self.entries)


def validate_state_vector(layout: LayoutRevision, component_states: StateInput) -> StateVector:
    member_order = layout.member_ids()
    members = set(member_order)
    raw_items = component_states.items() if isinstance(component_states, Mapping) else component_states
    try:
        items = iter(raw_items)
    except TypeError as exc:
        raise InvalidStateVector('component states must be a mapping or an iterable of pairs') from exc

    states = {}
    for item in items:
        try:
            asset_id, state = item
        except (ValueError, TypeError) as exc:
            raise InvalidStateVector('each state must be an asset and boolean pair') from exc
        if not isinstance(asset_id, str) or asset_id not in members:
            raise InvalidStateVector(f'asset {asset_id!r} is not a member of this topology')
        if asset_id in states:
            raise InvalidStateVector(f'duplicate state for asset {asset_id!r}')
        if type(state) is not bool:
            raise InvalidStateVector(f'state for {asset_id!r} must be a boolean')
        states[asset_id] = state
    missing = tuple(asset_id for asset_id in member_order if asset_id not in states)
    if missing:
        raise InvalidStateVector(f'missing states for {missing!r}')
    return StateVector(tuple((asset_id, states[asset_id]) for asset_id in member_order))
