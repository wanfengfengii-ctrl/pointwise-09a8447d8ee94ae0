from fractions import Fraction
from sqlite3 import Connection

from .repository import AssetRepository
from .validation import validate_asset_fields


def put_asset(db: Connection, asset_id: str, description: str, availability: Fraction) -> int:
    validate_asset_fields(asset_id, description, availability)
    return AssetRepository(db).append_revision(asset_id, description, availability)
