from dataclasses import dataclass
from fractions import Fraction
from sqlite3 import Connection

from .repository import AssetRepository


@dataclass(frozen=True)
class AssetRevision:
    revision_id: int
    asset_id: str
    description: str
    availability: Fraction


class UnknownAssetRevision(LookupError):
    """The requested catalog revision is absent."""


def get_asset_revision(db: Connection, revision_id: int) -> AssetRevision:
    row = AssetRepository(db).find_revision(revision_id)
    if row is None:
        raise UnknownAssetRevision(f'unknown asset revision {revision_id!r}')
    return AssetRevision(*row)


def get_current_asset_revision(db: Connection, asset_id: str) -> AssetRevision:
    row = AssetRepository(db).find_current_revision(asset_id)
    if row is None:
        raise UnknownAssetRevision(f'no asset revisions for {asset_id!r}')
    return AssetRevision(*row)
