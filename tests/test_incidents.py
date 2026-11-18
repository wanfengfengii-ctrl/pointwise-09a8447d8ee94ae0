from evidence import (EvidenceRepository, InvalidIncidentBinding, InvalidObservations, UnknownIncident,
                      freeze_incident, load_incident, put_observations)
from topology import Stage, UnknownLayoutRevision, save_layout

from tests.fixtures import DatabaseCase, INCIDENT_KEY, record_incident, register_components, shared_stages


class IncidentTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.stages = shared_stages(register_components(self.db))
        self.layout_id = save_layout(self.db, self.stages)
        self.observation_id, self.incident_id = record_incident(self.db, self.layout_id, [('intake', True)])

    def test_partial_evidence(self):
        supplement = put_observations(self.db, INCIDENT_KEY, self.layout_id,
                                      [('polish', False), ('intake', True)])
        old = load_incident(self.db, self.incident_id)
        self.assertEqual(old.incident.observation_revision_id, self.observation_id)
        self.assertIs(old.observations.reading_for('intake'), True)
        self.assertIsNone(old.observations.reading_for('polish'))
        revised = EvidenceRepository(self.db).find_observations(supplement)
        self.assertEqual(revised.readings, (('intake', True), ('polish', False)))
        self.assertIs(revised.reading_for('polish'), False)

    def test_empty_evidence(self):
        observation_id, incident_id = record_incident(self.db, self.layout_id, ())
        unknown = load_incident(self.db, incident_id)
        self.assertEqual(unknown.incident.observation_revision_id, observation_id)
        self.assertEqual(unknown.observations.readings, ())
        self.assertEqual([unknown.observations.reading_for(stage.name) for stage in unknown.layout.stages],
                         [None, None])

    def test_freeze_historical(self):
        supplement = put_observations(self.db, INCIDENT_KEY, self.layout_id, {'polish': False})
        historical_id = freeze_incident(self.db, self.layout_id, self.observation_id)
        corrected_id = freeze_incident(self.db, self.layout_id, supplement)
        old = load_incident(self.db, historical_id)
        corrected = load_incident(self.db, corrected_id)
        self.assertNotEqual(historical_id, corrected_id)
        self.assertEqual(old.observations.readings, (('intake', True),))
        self.assertIsNone(old.observations.reading_for('polish'))
        self.assertIsNone(corrected.observations.reading_for('intake'))
        self.assertIs(corrected.observations.reading_for('polish'), False)
        self.assertEqual((old.incident.observation_revision_id, corrected.incident.observation_revision_id),
                         (self.observation_id, supplement))
        self.assertEqual(old.observations, load_incident(self.db, self.incident_id).observations)

    def test_mismatched_parents(self):
        changed = (Stage('intake', (self.stages[0].routes[1],)), self.stages[1])
        other_layout = save_layout(self.db, changed)
        with self.assertRaisesRegex(InvalidIncidentBinding, 'layout revisions differ'):
            freeze_incident(self.db, other_layout, self.observation_id)
        self._assert_no_new_incident()
        other_incident = freeze_incident(self.db, self.layout_id, self.observation_id)
        self.assertEqual(load_incident(self.db, other_incident).layout.stages, self.stages)

    def test_missing_parents(self):
        for layout_id, reading_id in ((9000, self.observation_id), (self.layout_id, 9000)):
            with self.subTest(layout_id=layout_id, reading_id=reading_id):
                with self.assertRaises(InvalidIncidentBinding):
                    freeze_incident(self.db, layout_id, reading_id)
                self._assert_no_new_incident()
        with self.assertRaises(UnknownIncident):
            load_incident(self.db, 9000)

    def test_unknown_stage(self):
        self._assert_batch_rejected([('intake', False), ('unknown', True)], 'unknown stage')
        with self.assertRaises(UnknownLayoutRevision):
            put_observations(self.db, INCIDENT_KEY, 9000, ())
        self._assert_no_new_observations()

    def test_duplicate_stage(self):
        self._assert_batch_rejected([('polish', False), ('intake', True), ('intake', False)], 'duplicate')

    def test_non_boolean(self):
        for value in (0, 1, None):
            with self.subTest(value=value):
                self._assert_batch_rejected([('intake', False), ('polish', value)], 'boolean')

    def _assert_batch_rejected(self, items, message):
        with self.assertRaisesRegex(InvalidObservations, message):
            put_observations(self.db, INCIDENT_KEY, self.layout_id, items)
        self._assert_no_new_observations()

    def _assert_no_new_observations(self):
        self.assertEqual(self.db.execute('SELECT revision_id FROM observation_revision').fetchall(),
                         [(self.observation_id,)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM observation_reading').fetchone(), (1,))
        observation = EvidenceRepository(self.db).find_observations(self.observation_id)
        self.assertEqual(observation.readings, (('intake', True),))

    def _assert_no_new_incident(self):
        self.assertEqual(self.db.execute('SELECT incident_id FROM frozen_incident').fetchall(), [(self.incident_id,)])
