from analysis import InvalidStateVector, replay_incident
from analysis.reconcile import ReadingDifference
from topology import save_layout
from topology.evaluate import StagePassage

from tests.fixtures import (DatabaseCase, SHARED_STATES, ordered_stages, record_incident,
                            register_components, shared_stages)


class ReplayTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.refs = register_components(self.db)
        self.layout_id = save_layout(self.db, shared_stages(self.refs))
        _, self.incident_id = record_incident(self.db, self.layout_id, [('polish', True)])

    def test_replay_conflict(self):
        replay = replay_incident(self.db, self.incident_id, SHARED_STATES)
        self.assertEqual(replay.passage.stages, (StagePassage('intake', ('backup',)), StagePassage('polish', ())))
        self.assertIs(replay.passage.line_passes, False)
        self.assertEqual(replay.blocked_stages, ('polish',))
        self.assertEqual(replay.differences, (ReadingDifference('polish', True, False),))
        self.assertEqual(replay.state_vector.entries, (('X', False), ('A', True), ('B', True)))
        self.assertEqual(replay, replay_incident(self.db, self.incident_id, reversed(SHARED_STATES)))

    def test_route_requires_all(self):
        for x_state, b_state, passes in ((True, False, False), (False, True, False), (True, True, True)):
            with self.subTest(x=x_state, b=b_state):
                replay = replay_incident(self.db, self.incident_id, {'X': x_state, 'A': True, 'B': b_state})
                self.assertEqual(replay.passage.stages[1].available_routes, ('supply',) if passes else ())
                self.assertIs(replay.passage.line_passes, passes)
        self.assertEqual(replay.passage.stages[0].available_routes, ('main', 'backup'))
        self.assertEqual(replay.blocked_stages, ())
        self.assertEqual(replay.differences, ())

    def test_continues_after_block(self):
        layout_id = save_layout(self.db, ordered_stages(self.refs))
        _, incident_id = record_incident(self.db, layout_id, [('M', False), ('Z', True)])
        replay = replay_incident(self.db, incident_id, SHARED_STATES)
        self.assertEqual(replay.passage.stages, (
            StagePassage('Z', ()), StagePassage('A', ()), StagePassage('M', ('z-backup', 'a-main')),
        ))
        self.assertIs(replay.passage.line_passes, False)
        self.assertEqual(replay.blocked_stages, ('Z', 'A'))
        self.assertIsNone(replay.context.observations.reading_for('A'))
        self.assertEqual(replay.differences, (
            ReadingDifference('Z', True, False), ReadingDifference('M', False, True),
        ))

    def test_false_reading_conflict(self):
        _, incident_id = record_incident(self.db, self.layout_id, [('polish', False)])
        replay = replay_incident(self.db, incident_id, {'X': True, 'A': False, 'B': True})
        self.assertIs(replay.passage.line_passes, True)
        self.assertIs(replay.context.observations.reading_for('polish'), False)
        self.assertEqual(replay.differences, (ReadingDifference('polish', False, True),))

    def test_unobserved_stage(self):
        _, incident_id = record_incident(self.db, self.layout_id, ())
        replay = replay_incident(self.db, incident_id, SHARED_STATES)
        self.assertEqual(replay.blocked_stages, ('polish',))
        self.assertEqual(tuple(stage.stage_name for stage in replay.passage.stages), ('intake', 'polish'))
        self.assertEqual(replay.differences, ())

    def test_missing_component(self):
        with self.assertRaisesRegex(InvalidStateVector, 'missing states.*X'):
            replay_incident(self.db, self.incident_id, {'A': True, 'B': True})
        replay = replay_incident(self.db, self.incident_id, {'X': False, 'A': True, 'B': True})
        self.assertEqual(replay.blocked_stages, ('polish',))

    def test_extra_member(self):
        with self.assertRaisesRegex(InvalidStateVector, 'not a member'):
            replay_incident(self.db, self.incident_id, (*SHARED_STATES, ('outside', True)))

    def test_non_boolean(self):
        for value in (0, 1):
            with self.subTest(value=value):
                with self.assertRaisesRegex(InvalidStateVector, 'boolean'):
                    replay_incident(self.db, self.incident_id, {'X': value, 'A': True, 'B': True})

    def test_duplicate_member(self):
        with self.assertRaisesRegex(InvalidStateVector, 'duplicate state.*X'):
            replay_incident(self.db, self.incident_id, (*SHARED_STATES, ('X', True)))
