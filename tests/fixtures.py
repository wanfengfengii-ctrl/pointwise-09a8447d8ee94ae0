import json
import sqlite3
import unittest
from contextlib import closing
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis import replay_incident
from briefing import BriefRepository, issue_brief, read_brief
from catalog import AssetRepository, get_asset_revision, put_asset
from evidence import EvidenceRepository, freeze_incident, put_observations
from topology import AssetReference, LayoutRepository, Route, Stage, save_layout


INCIDENT_KEY = '冷却巡检-01'
SHARED_STATES = (('B', True), ('X', False), ('A', True))


def initialize_database(db):
    for repository in (AssetRepository, LayoutRepository, EvidenceRepository, BriefRepository):
        repository(db).initialize()


def register_components(db, shared_rate=Fraction(1, 3)):
    rates = {'X': shared_rate, 'A': Fraction(1, 2), 'B': Fraction(1, 2)}
    return {
        name: AssetReference(name, put_asset(db, name, f'冷却部件 {name}', rate))
        for name, rate in rates.items()
    }


def shared_stages(refs):
    return (
        Stage('intake', (Route('main', (refs['X'],)), Route('backup', (refs['A'],)))),
        Stage('polish', (Route('supply', (refs['X'], refs['B'])),)),
    )


def ordered_stages(refs):
    return (
        Stage('Z', (Route('primary', (refs['X'],)),)),
        Stage('A', (Route('feed', (refs['X'], refs['B'])),)),
        Stage('M', (Route('z-backup', (refs['A'],)), Route('a-main', (refs['B'],)))),
    )


def record_incident(db, layout_id, readings):
    observation_id = put_observations(db, INCIDENT_KEY, layout_id, readings)
    return observation_id, freeze_incident(db, layout_id, observation_id)


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'cooling.sqlite3'
        self.db = self.open_database()
        initialize_database(self.db)

    def open_database(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        return db


def _diagnosis(line_passes, blocked_stages, differences, stage_rows):
    return {
        'line_passes': line_passes,
        'blocked_stages': list(blocked_stages),
        'differences': [[item.stage_name, item.observed, item.computed] for item in differences],
        'stages': [[name, reading, list(routes)] for name, reading, routes in stage_rows],
    }


def main():
    expected = {
        'line_passes': False,
        'blocked_stages': ['polish'],
        'differences': [['polish', True, False]],
        'stages': [['intake', None, ['backup']], ['polish', True, []]],
    }
    with TemporaryDirectory() as directory:
        path = Path(directory) / 'cooling.sqlite3'
        with closing(sqlite3.connect(path)) as db:
            initialize_database(db)
            refs = register_components(db)
            layout_id = save_layout(db, shared_stages(refs))
            observation_id, incident_id = record_incident(db, layout_id, [('polish', True)])
            replay = replay_incident(db, incident_id, SHARED_STATES)
            actual = _diagnosis(
                replay.passage.line_passes, replay.blocked_stages, replay.differences,
                ((stage.stage_name, replay.context.observations.reading_for(stage.stage_name),
                  stage.available_routes) for stage in replay.passage.stages),
            )
            if actual != expected:
                raise AssertionError(f'unexpected replay {actual!r}')
            brief_id = issue_brief(db, incident_id, SHARED_STATES)
            corrected_revision = put_asset(db, 'X', '检修后更正', Fraction(2, 3))
            revised_refs = {**refs, 'X': AssetReference('X', corrected_revision)}
            revised_layout = save_layout(db, shared_stages(revised_refs))
            record_incident(db, revised_layout, [('intake', True), ('polish', False)])
        with closing(sqlite3.connect(path)) as db:
            saved = read_brief(db, brief_id)
            fixed_ids = [reference.revision_id for stage in saved.stages for route in stage.routes
                         for reference in route.components if reference.asset_id == 'X']
            downstream_actual = {
                'parents': [saved.incident_id, saved.layout_revision_id, saved.observation_revision_id],
                'shared_revision_ids': fixed_ids,
                'shared_rates': [str(get_asset_revision(db, revision_id).availability)
                                 for revision_id in fixed_ids],
                'component_states': dict(saved.component_states),
                'diagnosis': _diagnosis(
                    saved.line_passes, saved.blocked_stages, saved.differences,
                    ((stage.name, stage.reading, stage.available_routes) for stage in saved.stages),
                ),
            }
    downstream_expected = {
        'parents': [incident_id, layout_id, observation_id],
        'shared_revision_ids': [refs['X'].revision_id, refs['X'].revision_id],
        'shared_rates': ['1/3', '1/3'],
        'component_states': {'X': False, 'A': True, 'B': True},
        'diagnosis': expected,
    }
    if downstream_actual != downstream_expected:
        raise AssertionError(f'unexpected brief {downstream_actual!r}')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'n7',
        'input': {
            'layout': {'intake': [['X'], ['A']], 'polish': [['X', 'B']]},
            'readings': {'polish': True},
            'states': dict(SHARED_STATES),
        },
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': ['topology/evaluate.py', 'analysis/replay.py', 'briefing/issue.py',
                       'briefing/readback.py', 'catalog/revisions.py'],
        'oracle': 'X is down, so only the intake backup passes. Polish needs X and B. '
                  'The signed brief retains the original parents and both references to X at 1/3.',
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
