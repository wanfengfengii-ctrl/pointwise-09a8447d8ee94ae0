import sqlite3
from fractions import Fraction

from carry_examples import (FULL_READINGS, INCIDENT_KEY, PARTIAL_READINGS, check_carry_example,
                            check_carry_fault, check_fault_fixture, check_reopened_carry, check_seed,
                            fail_observation_commit, seed_cases)
from catalog import put_asset
from evidence import (EvidenceRepository, UnknownCarry, UnknownObservation, carry_observations,
                      freeze_incident, load_incident, put_observations, read_carry)
from topology import (AssetReference, Route, Stage, UnknownLayoutRevision, eligible_stage_pairs,
                      load_layout_revision, save_layout)

from tests.fixtures import DatabaseCase


class CarryCase(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.cases = seed_cases(self.db)


class MigrationTests(DatabaseCase):
    def test_old_database_keeps_working(self):
        from catalog import AssetRepository
        from topology import LayoutRepository
        from evidence import EvidenceRepository
        from briefing import BriefRepository

        # A database initialized before the carry tables existed.
        for repository in (AssetRepository, LayoutRepository, EvidenceRepository):
            repository(self.db).initialize()
        reference = AssetReference('X', put_asset(self.db, 'X', '旧参数', Fraction(1, 2)))
        old_layout = save_layout(self.db, (Stage('feed', (Route('main', (reference,)),)),))
        source = put_observations(self.db, INCIDENT_KEY, old_layout, (('feed', True),))
        incident = freeze_incident(self.db, old_layout, source)
        BriefRepository(self.db).initialize()
        self.db.execute('DROP TABLE carry_match')
        self.db.execute('DROP TABLE carry_batch')
        self.db.commit()

        # Re-running the documented initialization adds only the missing tables.
        for repository in (AssetRepository, LayoutRepository, EvidenceRepository, BriefRepository):
            repository(self.db).initialize()
        self.assertEqual(load_incident(self.db, incident).observations.readings, (('feed', True),))
        self.assertEqual(load_layout_revision(self.db, old_layout).stages[0].name, 'feed')
        new_layout = save_layout(self.db, (Stage('feed-v2', (Route('only', (reference, reference)),)),))
        batch_id = carry_observations(self.db, source, new_layout)
        self.assertEqual(read_carry(self.db, batch_id)['matches'], (('feed', 'feed-v2', True),))
        new_incident = freeze_incident(self.db, new_layout, batch_id)
        self.assertEqual(load_incident(self.db, new_incident).observations.readings, (('feed-v2', True),))
        self.assertEqual(load_incident(self.db, incident).observations.readings, (('feed', True),))


class EligiblePairTests(CarryCase):
    def test_documented_candidates(self):
        self.assertEqual(
            eligible_stage_pairs(self.db, self.cases.old_layout_id, self.cases.new_layout_id),
            (('Z', 'R'), ('A', 'R'), ('M', 'S')),
        )

    def test_no_equivalent_stage(self):
        self.assertEqual(
            eligible_stage_pairs(self.db, self.cases.old_layout_id, self.cases.no_match_layout_id), (),
        )

    def test_crossed_names_are_semantic(self):
        self.assertEqual(
            eligible_stage_pairs(self.db, self.cases.crossed_old_layout_id, self.cases.crossed_new_layout_id),
            (('U', 'U'), ('V', 'V')),
        )

    def test_ordering_is_old_major_new_minor(self):
        p = AssetReference('P', put_asset(self.db, 'P', '参数', Fraction(1, 2)))
        q = AssetReference('Q', put_asset(self.db, 'Q', '参数', Fraction(1, 2)))
        old = save_layout(self.db, (
            Stage('old-2', (Route('x', (q,)),)),
            Stage('old-1', (Route('y', (p,)),)),
        ))
        new = save_layout(self.db, (
            Stage('new-b', (Route('r', (q,)),)),
            Stage('new-a', (Route('s', (p,)), Route('t', (p, p)))),
        ))
        self.assertEqual(
            eligible_stage_pairs(self.db, old, new),
            (('old-2', 'new-b'), ('old-1', 'new-a')),
        )

    def test_route_structure_does_not_matter(self):
        p = AssetReference('P', put_asset(self.db, 'P', '参数', Fraction(1, 2)))
        q = AssetReference('Q', put_asset(self.db, 'Q', '参数', Fraction(1, 2)))
        old = save_layout(self.db, (
            Stage('one', (Route('a', (p, q)), Route('b', (q, p, q)))),
        ))
        new = save_layout(self.db, (
            Stage('other', (Route('z', (q, p)),)),
        ))
        self.assertEqual(eligible_stage_pairs(self.db, old, new), (('one', 'other'),))

    def test_absorption_is_equivalence(self):
        p = AssetReference('P', put_asset(self.db, 'P', '参数', Fraction(1, 2)))
        q = AssetReference('Q', put_asset(self.db, 'Q', '参数', Fraction(1, 2)))
        old = save_layout(self.db, (Stage('wide', (Route('a', (p, q)), Route('b', (p,)))),))
        new = save_layout(self.db, (Stage('narrow', (Route('c', (p,)),)),))
        self.assertEqual(eligible_stage_pairs(self.db, old, new), (('wide', 'narrow'),))

    def test_revision_number_does_not_matter(self):
        p1 = AssetReference('P', put_asset(self.db, 'P', '旧参数', Fraction(1, 2)))
        p2 = AssetReference('P', put_asset(self.db, 'P', '新参数', Fraction(2, 3)))
        old = save_layout(self.db, (Stage('old', (Route('a', (p1,)),)),))
        new = save_layout(self.db, (Stage('new', (Route('b', (p2,)),)),))
        self.assertEqual(eligible_stage_pairs(self.db, old, new), (('old', 'new'),))

    def test_different_component_is_not_equivalent(self):
        p = AssetReference('P', put_asset(self.db, 'P', '参数', Fraction(1, 2)))
        q = AssetReference('Q', put_asset(self.db, 'Q', '参数', Fraction(1, 2)))
        old = save_layout(self.db, (Stage('old', (Route('a', (p,)),)),))
        new = save_layout(self.db, (Stage('new', (Route('b', (q,)),)),))
        self.assertEqual(eligible_stage_pairs(self.db, old, new), ())

    def test_unknown_layouts(self):
        for old_id, new_id in ((9000, self.cases.new_layout_id),
                               (self.cases.old_layout_id, 9000)):
            with self.subTest(old_id=old_id, new_id=new_id):
                with self.assertRaises(UnknownLayoutRevision):
                    eligible_stage_pairs(self.db, old_id, new_id)

    def test_read_only(self):
        before = self.db.total_changes
        eligible_stage_pairs(self.db, self.cases.old_layout_id, self.cases.new_layout_id)
        self.assertEqual(self.db.total_changes, before)


class CarryTests(CarryCase):
    def test_documented_alignment(self):
        batch_id = carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
        incident_id = freeze_incident(self.db, self.cases.new_layout_id, batch_id)
        readings = load_incident(self.db, incident_id).observations
        self.assertIsNone(readings.reading_for('R'))
        self.assertIs(readings.reading_for('S'), False)
        self.assertEqual(read_carry(self.db, batch_id), {
            'source_observation_id': self.cases.full_source_id,
            'old_layout_id': self.cases.old_layout_id,
            'new_layout_id': self.cases.new_layout_id,
            'matches': (('M', 'S', False),),
        })

    def test_source_batch_untouched(self):
        source_before = EvidenceRepository(self.db).find_observations(self.cases.full_source_id)
        carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
        self.assertEqual(EvidenceRepository(self.db).find_observations(self.cases.full_source_id), source_before)

    def test_partial_readings_still_align(self):
        batch_id = carry_observations(self.db, self.cases.partial_source_id, self.cases.new_layout_id)
        self.assertEqual(read_carry(self.db, batch_id)['matches'], ())
        incident_id = freeze_incident(self.db, self.cases.new_layout_id, batch_id)
        readings = load_incident(self.db, incident_id).observations
        self.assertEqual(readings.readings, ())
        self.assertIsNone(readings.reading_for('R'))
        self.assertIsNone(readings.reading_for('S'))

    def test_no_candidate_still_registers_empty_batch(self):
        batch_id = carry_observations(self.db, self.cases.full_source_id, self.cases.no_match_layout_id)
        self.assertEqual(read_carry(self.db, batch_id)['matches'], ())
        incident_id = freeze_incident(self.db, self.cases.no_match_layout_id, batch_id)
        self.assertEqual(load_incident(self.db, incident_id).observations.readings, ())
        self.assertEqual(self.db.execute('SELECT count(*) FROM carry_batch').fetchone(), (1,))

    def test_ambiguous_crossed_alignment_carries_nothing(self):
        batch_id = carry_observations(self.db, self.cases.crossed_source_id, self.cases.crossed_new_layout_id)
        self.assertEqual(read_carry(self.db, batch_id)['matches'], ())
        incident_id = freeze_incident(self.db, self.cases.crossed_new_layout_id, batch_id)
        readings = load_incident(self.db, incident_id).observations
        self.assertIsNone(readings.reading_for('U'))
        self.assertIsNone(readings.reading_for('V'))

    def test_derived_batch_keeps_incident_key_and_order(self):
        batch_id = carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
        derived = EvidenceRepository(self.db).find_observations(batch_id)
        self.assertEqual(derived.incident_key, INCIDENT_KEY)
        self.assertEqual(derived.layout_revision_id, self.cases.new_layout_id)
        self.assertEqual(derived.readings, (('S', False),))

    def test_same_layout_source_and_target(self):
        batch_id = carry_observations(self.db, self.cases.full_source_id, self.cases.old_layout_id)
        self.assertEqual(read_carry(self.db, batch_id)['matches'], (
            ('Z', 'Z', True), ('A', 'A', False), ('M', 'M', False),
        ))
        incident_id = freeze_incident(self.db, self.cases.old_layout_id, batch_id)
        readings = load_incident(self.db, incident_id).observations
        self.assertEqual(readings.readings, FULL_READINGS)

    def test_derived_batch_can_be_a_source(self):
        first_id = carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
        second_id = carry_observations(self.db, first_id, self.cases.old_layout_id)
        record = read_carry(self.db, second_id)
        self.assertEqual(record['source_observation_id'], first_id)
        self.assertEqual(record['old_layout_id'], self.cases.new_layout_id)
        self.assertEqual(record['new_layout_id'], self.cases.old_layout_id)
        self.assertEqual(record['matches'], (('S', 'M', False),))

    def test_read_after_reopen_and_later_changes(self):
        batch_id = carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
        published = read_carry(self.db, batch_id)
        put_asset(self.db, 'P', '后续更正', Fraction(3, 4))
        save_layout(self.db, (Stage('R', (Route('r', (AssetReference('P', put_asset(
            self.db, 'P', '再更正', Fraction(4, 5))),)),)),))
        put_observations(self.db, INCIDENT_KEY, self.cases.new_layout_id, {'S': True})
        self.db.close()
        reopened = self.open_database()
        self.assertEqual(read_carry(reopened, batch_id), published)
        self.assertEqual(load_layout_revision(reopened, self.cases.old_layout_id)
                         .stages[0].routes[0].components[0].asset_id, 'P')

    def test_unknown_source(self):
        for source_id in (9000, 0, -1, True, '1'):
            with self.subTest(source_id=source_id):
                with self.assertRaises(UnknownObservation):
                    carry_observations(self.db, source_id, self.cases.new_layout_id)
        self.assertEqual(self.db.execute('SELECT count(*) FROM carry_batch').fetchone(), (0,))

    def test_unknown_target(self):
        with self.assertRaises(UnknownLayoutRevision):
            carry_observations(self.db, self.cases.full_source_id, 9000)
        self.assertEqual(self.db.execute('SELECT count(*) FROM carry_batch').fetchone(), (0,))

    def test_read_carry_lookup_errors(self):
        for derived_id in (9000, 0, -1, True, '1', self.cases.full_source_id):
            with self.subTest(derived_id=derived_id):
                with self.assertRaises(UnknownCarry):
                    read_carry(self.db, derived_id)


class CarryFailureTests(CarryCase):
    def test_commit_failure_leaves_nothing_and_retries(self):
        before = {
            table: self.db.execute(f'SELECT count(*) FROM {table}').fetchone()
            for table in ('observation_revision', 'observation_reading', 'carry_batch', 'carry_match')
        }
        with fail_observation_commit(self.db):
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
                carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
            self.assertFalse(self.db.in_transaction)
        after = {
            table: self.db.execute(f'SELECT count(*) FROM {table}').fetchone()
            for table in ('observation_revision', 'observation_reading', 'carry_batch', 'carry_match')
        }
        self.assertEqual(after, before)
        batch_id = carry_observations(self.db, self.cases.full_source_id, self.cases.new_layout_id)
        self.assertEqual(read_carry(self.db, batch_id)['matches'], (('M', 'S', False),))
        incident_id = freeze_incident(self.db, self.cases.new_layout_id, batch_id)
        self.assertIs(load_incident(self.db, incident_id).observations.reading_for('S'), False)


class CarryModuleTests(DatabaseCase):
    def test_seed_and_fault_fixture(self):
        cases = seed_cases(self.db)
        check_seed(self.db, cases)
        check_fault_fixture(self.db, cases)

    def test_documented_helpers_all_pass(self):
        cases = seed_cases(self.db)
        check_carry_example(self.db, cases)
        check_carry_fault(self.db, cases)
        self.assertEqual(check_reopened_carry(self.db, cases)['matches'], (('M', 'S', False),))

    def test_fault_fixture_rejects_then_allows(self):
        cases = seed_cases(self.db)
        before = self.db.execute('SELECT revision_id FROM observation_revision ORDER BY revision_id').fetchall()
        with fail_observation_commit(self.db):
            with self.assertRaises(sqlite3.IntegrityError):
                put_observations(self.db, INCIDENT_KEY, cases.new_layout_id, {'S': False})
        self.assertEqual(
            self.db.execute('SELECT revision_id FROM observation_revision ORDER BY revision_id').fetchall(),
            before,
        )
        self.assertIsInstance(put_observations(self.db, INCIDENT_KEY, cases.new_layout_id, {'S': False}), int)


class DocumentedExampleTests(DatabaseCase):
    def test_carry_example_module_sequence(self):
        cases = seed_cases(self.db)
        self.assertEqual(
            eligible_stage_pairs(self.db, cases.old_layout_id, cases.new_layout_id),
            (('Z', 'R'), ('A', 'R'), ('M', 'S')),
        )
        batch_id = carry_observations(self.db, cases.full_source_id, cases.new_layout_id)
        incident_id = freeze_incident(self.db, cases.new_layout_id, batch_id)
        readings = load_incident(self.db, incident_id).observations
        self.assertIsNone(readings.reading_for('R'))
        self.assertIs(readings.reading_for('S'), False)
        self.assertEqual(read_carry(self.db, batch_id), {
            'source_observation_id': cases.full_source_id,
            'old_layout_id': cases.old_layout_id,
            'new_layout_id': cases.new_layout_id,
            'matches': (('M', 'S', False),),
        })
        self.assertEqual(PARTIAL_READINGS, (('A', False),))
        self.assertEqual(FULL_READINGS, (('Z', True), ('A', False), ('M', False)))
