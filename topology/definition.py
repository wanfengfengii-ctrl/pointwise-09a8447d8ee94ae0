from dataclasses import dataclass


@dataclass(frozen=True)
class AssetReference:
    asset_id: str
    revision_id: int


@dataclass(frozen=True)
class Route:
    name: str
    components: tuple[AssetReference, ...]


@dataclass(frozen=True)
class Stage:
    name: str
    routes: tuple[Route, ...]


@dataclass(frozen=True)
class LayoutRevision:
    revision_id: int
    stages: tuple[Stage, ...]

    def member_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            reference.asset_id
            for stage in self.stages
            for route in stage.routes
            for reference in route.components
        ))
