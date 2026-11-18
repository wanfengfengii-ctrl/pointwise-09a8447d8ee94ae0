import json
from dataclasses import asdict

from analysis.reconcile import ReadingDifference
from topology.definition import AssetReference, Route

from .snapshot import BriefSnapshot, BriefStage


def encode_brief_payload(snapshot: BriefSnapshot) -> str:
    return json.dumps({'version': 1, 'snapshot': asdict(snapshot)}, ensure_ascii=False, separators=(',', ':'))


def _decode_stage(data: dict) -> BriefStage:
    routes = tuple(
        Route(route['name'], tuple(AssetReference(**reference) for reference in route['components']))
        for route in data['routes']
    )
    return BriefStage(
        name=data['name'],
        routes=routes,
        reading=data['reading'],
        available_routes=tuple(data['available_routes']),
        passed=data['passed'],
    )


def decode_brief_payload(payload: str) -> BriefSnapshot:
    envelope = json.loads(payload)
    if envelope['version'] != 1:
        raise ValueError(f'unsupported brief payload version {envelope["version"]!r}')
    snapshot = envelope['snapshot']
    return BriefSnapshot(
        incident_id=snapshot['incident_id'],
        incident_key=snapshot['incident_key'],
        layout_revision_id=snapshot['layout_revision_id'],
        observation_revision_id=snapshot['observation_revision_id'],
        stages=tuple(_decode_stage(stage) for stage in snapshot['stages']),
        component_states=tuple((asset_id, state) for asset_id, state in snapshot['component_states']),
        line_passes=snapshot['line_passes'],
        blocked_stages=tuple(snapshot['blocked_stages']),
        differences=tuple(ReadingDifference(**difference) for difference in snapshot['differences']),
    )
