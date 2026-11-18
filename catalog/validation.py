from fractions import Fraction


class InvalidAsset(ValueError):
    """An asset registration does not meet the catalog contract."""


def validate_asset_fields(asset_id: str, description: str, availability: Fraction) -> None:
    if not isinstance(asset_id, str) or not asset_id or asset_id.strip() != asset_id or '\x00' in asset_id:
        raise InvalidAsset('asset ID must be a nonempty, trimmed string without NUL')
    if not isinstance(description, str):
        raise InvalidAsset('description must be a string')
    if not isinstance(availability, Fraction) or not 0 <= availability <= 1:
        raise InvalidAsset('availability must be a Fraction in [0, 1]')
