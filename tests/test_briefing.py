import sqlite3
from fractions import Fraction

from analysis import InvalidStateVector, replay_incident
from analysis.reconcile import ReadingDifference
from briefing import UnknownBrief, issue_brief, read_brief
from catalog import get_asset_revision, get_current_asset_revision, put_asset
from evidence import UnknownIncident, load_incident
from topology import AssetReference, save_layout

from tests.fixtures import (DatabaseCase, INCIDENT_KEY, SHARED_STATES, initialize_database, ordered_stages,
                            record_incident, register_components, shared_stages)


class BriefingTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.refs = register_components(self.db)
        self.stages = shared_stages(self.refs)
        self.layout_id = save_layout(self.db, self.stages)
        self.observation_id, self.incident_id = record_incident(self.db, self.layout_id, {'polish': True})

    def test_read_after_correction(self):
        brief_id = issue_brief(self.db, self.incident_id, SHARED_STATES)
        corrected, new_layout, new_observation, new_incident = self._correct_shared_line()
        self.db.close()
        reopened = self.open_database()
        brief = read_brief(reopened, brief_id)
        self.assertEqual((brief.incident_id, brief.layout_revision_id, brief.observation_revision_id),
                         (self.incident_id, self.layout_id, self.observation_id))
        self.assertEqual(brief.incident_key, INCIDENT_KEY)
        self.assertEqual(brief.component_states, (('X', False), ('A', True), ('B', True)))
        self.assertEqual(tuple((stage.name, stage.routes) for stage in brief.stages),
                         tuple((stage.name, stage.routes) for stage in self.stages))
        self.assertEqual(tuple((stage.name, stage.reading, stage.available_routes, stage.passed)
                               for stage in brief.stages),
                         (('intake', None, ('backup',), True), ('polish', True, (), False)))
        self.assertIs(brief.line_passes, False)
        self.assertEqual(brief.blocked_stages, ('polish',))
        self.assertEqual(brief.differences, (ReadingDifference('polish', True, False),))
        shared = brief.stages[1].routes[0].components[0]
        self.assertEqual(shared, self.refs['X'])
        self.assertEqual(get_asset_revision(reopened, shared.revision_id).availability, Fraction(1, 3))
        self.assertEqual(get_current_asset_revision(reopened, 'X').revision_id, corrected.revision_id)
        revised = load_incident(reopened, new_incident)
        self.assertEqual((revised.layout.revision_id, revised.observations.revision_id), (new_layout, new_observation))
        self.assertEqual(revised.layout.stages[1].routes[0].components[0], corrected)
        self.assertIs(revised.observations.reading_for('polish'), False)

    def test_ordered_snapshot(self):
        stages, layout_id, observation_id, incident_id = self._record_ordered_line()
        brief_id = issue_brief(self.db, incident_id, SHARED_STATES)
        self._correct_shared_line()
        record_incident(self.db, layout_id, [('Z', False), ('A', False), ('M', True)])
        self.db.close()
        brief = read_brief(self.open_database(), brief_id)
        self._assert_ordered_snapshot(brief, stages, layout_id, observation_id, incident_id)

    def test_unknown_brief(self):
        for brief_id in (1, -1, True, '1', 1 << 70):
            with self.subTest(brief_id=brief_id):
                with self.assertRaises(UnknownBrief):
                    read_brief(self.db, brief_id)

    def test_reinitialize(self):
        brief_id = issue_brief(self.db, self.incident_id, SHARED_STATES)
        issued = read_brief(self.db, brief_id)
        corrected, new_layout, new_observation, new_incident = self._correct_shared_line()
        self.db.close()
        reopened = self.open_database()
        initialize_database(reopened)
        initialize_database(reopened)
        self.assertEqual(read_brief(reopened, brief_id), issued)
        self.assertEqual(get_current_asset_revision(reopened, 'X').availability, Fraction(2, 3))
        self.assertEqual(load_incident(reopened, new_incident).observations.readings,
                         (('intake', True), ('polish', False)))
        self.assertEqual(load_incident(reopened, self.incident_id).observations.readings, (('polish', True),))
        revised_id = issue_brief(reopened, new_incident, SHARED_STATES)
        self.assertNotEqual(revised_id, brief_id)
        revised = read_brief(reopened, revised_id)
        self.assertEqual((revised.layout_revision_id, revised.observation_revision_id), (new_layout, new_observation))
        self.assertEqual(revised.stages[0].routes[0].components, (corrected,))
        self.assertEqual(revised.differences, ())
        self.assertEqual(revised.blocked_stages, ('polish',))
        self.assertEqual(revised.blocked_stages, replay_incident(reopened, new_incident, SHARED_STATES).blocked_stages)

    def test_issue_rollback(self):
        prior_id = issue_brief(self.db, self.incident_id, SHARED_STATES)
        prior = read_brief(self.db, prior_id)
        stages, layout_id, observation_id, incident_id = self._record_ordered_line()
        self.db.executescript('''
            CREATE TABLE commit_guard_parent (id INTEGER PRIMARY KEY);
            CREATE TABLE commit_guard_child (
                id INTEGER REFERENCES commit_guard_parent(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER stop_brief_commit AFTER INSERT ON brief
            BEGIN
                INSERT INTO commit_guard_child (id) VALUES (NEW.brief_id);
            END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            issue_brief(self.db, incident_id, SHARED_STATES)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute('SELECT count(*) FROM commit_guard_child').fetchone(), (0,))
        reader = self.open_database()
        self.assertEqual(reader.execute('SELECT brief_id FROM brief ORDER BY brief_id').fetchall(), [(prior_id,)])
        self.assertEqual(read_brief(reader, prior_id), prior)
        with self.assertRaises(UnknownBrief):
            read_brief(reader, prior_id + 1)
        self.db.execute('DROP TRIGGER stop_brief_commit')
        retried_id = issue_brief(self.db, incident_id, SHARED_STATES)
        self.db.close()
        self.assertEqual(reader.execute('SELECT brief_id FROM brief ORDER BY brief_id').fetchall(),
                         [(prior_id,), (retried_id,)])
        retried = read_brief(self.open_database(), retried_id)
        self._assert_ordered_snapshot(retried, stages, layout_id, observation_id, incident_id)

    def test_invalid_input(self):
        with self.assertRaises(UnknownIncident):
            issue_brief(self.db, 9000, SHARED_STATES)
        with self.assertRaises(InvalidStateVector):
            issue_brief(self.db, self.incident_id, {'X': True, 'B': False})
        self.assertEqual(self.db.execute('SELECT count(*) FROM brief').fetchone(), (0,))
        with self.assertRaises(UnknownBrief):
            read_brief(self.db, 1)

    def _correct_shared_line(self):
        corrected = AssetReference('X', put_asset(self.db, 'X', '更正后可用率', Fraction(2, 3)))
        layout_id = save_layout(self.db, shared_stages({**self.refs, 'X': corrected}))
        observation_id, incident_id = record_incident(self.db, layout_id, {'intake': True, 'polish': False})
        return corrected, layout_id, observation_id, incident_id

    def _record_ordered_line(self):
        stages = ordered_stages(self.refs)
        layout_id = save_layout(self.db, stages)
        observation_id, incident_id = record_incident(self.db, layout_id, [('M', False), ('Z', True)])
        return stages, layout_id, observation_id, incident_id

    def _assert_ordered_snapshot(self, brief, stages, layout_id, observation_id, incident_id):
        self.assertEqual((brief.incident_id, brief.layout_revision_id, brief.observation_revision_id),
                         (incident_id, layout_id, observation_id))
        self.assertEqual(tuple((stage.name, stage.routes) for stage in brief.stages),
                         tuple((stage.name, stage.routes) for stage in stages))
        self.assertEqual(tuple((stage.name, stage.reading, stage.available_routes, stage.passed)
                               for stage in brief.stages), (
            ('Z', True, (), False), ('A', None, (), False), ('M', False, ('z-backup', 'a-main'), True),
        ))
        self.assertEqual(brief.component_states, (('X', False), ('B', True), ('A', True)))
        self.assertEqual(brief.differences, (
            ReadingDifference('Z', True, False), ReadingDifference('M', False, True),
        ))
        self.assertEqual(brief.blocked_stages, ('Z', 'A'))
        self.assertIs(brief.line_passes, False)
