from collections.abc import Sequence
from sqlite3 import Connection

from catalog.revisions import UnknownAssetRevision, get_asset_revision

from .definition import AssetReference, Route, Stage


class InvalidLayout(ValueError):
    """A topology cannot be published from the supplied definition."""


def _valid_name(name: object) -> bool:
    return isinstance(name, str) and bool(name) and name.strip() == name and '\x00' not in name


def _require_sequence(value, label: str) -> tuple:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise InvalidLayout(f'{label} must be a nonempty ordered sequence')
    return tuple(value)


def _validate_route(db: Connection, route: Route, revisions: dict[str, int]) -> Route:
    components = _require_sequence(route.components, f'components for route {route.name!r}')
    for reference in components:
        if not isinstance(reference, AssetReference) or not _valid_name(reference.asset_id):
            raise InvalidLayout(f'invalid asset reference in route {route.name!r}')
        asset_id = reference.asset_id
        revision_id = reference.revision_id
        if type(revision_id) is not int:
            raise InvalidLayout(f'invalid revision for asset {asset_id!r}')
        if asset_id in revisions:
            if revision_id != revisions[asset_id]:
                raise InvalidLayout(f'layout uses different revisions of {asset_id!r}')
            continue
        try:
            revision = get_asset_revision(db, revision_id)
        except UnknownAssetRevision as exc:
            raise InvalidLayout(f'unknown asset revision {revision_id!r}') from exc
        if revision.asset_id != asset_id:
            raise InvalidLayout(f'asset revision {revision_id} does not belong to {asset_id!r}')
        revisions[asset_id] = revision_id
    return Route(route.name, components)


def validate_layout(db: Connection, stages: Sequence[Stage]) -> tuple[Stage, ...]:
    stage_names = set()
    revisions: dict[str, int] = {}
    validated = []
    for stage in _require_sequence(stages, 'stages'):
        if not isinstance(stage, Stage) or not _valid_name(stage.name):
            raise InvalidLayout('invalid stage name or definition')
        if stage.name in stage_names:
            raise InvalidLayout(f'duplicate stage {stage.name!r}')
        stage_names.add(stage.name)
        route_names = set()
        routes = []
        for route in _require_sequence(stage.routes, f'routes for stage {stage.name!r}'):
            if not isinstance(route, Route) or not _valid_name(route.name):
                raise InvalidLayout(f'invalid route in stage {stage.name!r}')
            if route.name in route_names:
                raise InvalidLayout(f'duplicate route {route.name!r} in stage {stage.name!r}')
            route_names.add(route.name)
            routes.append(_validate_route(db, route, revisions))
        validated.append(Stage(stage.name, tuple(routes)))
    return tuple(validated)
