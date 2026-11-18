from fractions import Fraction

from catalog import (InvalidAsset, UnknownAssetRevision, get_asset_revision,
                     get_current_asset_revision, put_asset)
from topology import (AssetReference, InvalidLayout, Route, Stage, UnknownLayoutRevision,
                      load_layout_revision, save_layout)

from tests.fixtures import DatabaseCase, register_components, shared_stages


class ConfigurationTests(DatabaseCase):
    def setUp(self):
        super().setUp()
        self.refs = register_components(self.db)
        self.stages = shared_stages(self.refs)
        self.layout_id = save_layout(self.db, self.stages)

    def test_fixed_layout(self):
        original = self.refs['X']
        corrected = put_asset(self.db, 'X', '更正参数', Fraction(2, 3))
        self.assertNotEqual(corrected, original.revision_id)
        current = get_current_asset_revision(self.db, 'X')
        self.assertEqual((current.revision_id, current.availability), (corrected, Fraction(2, 3)))
        loaded = load_layout_revision(self.open_database(), self.layout_id)
        self.assertEqual(loaded.stages, self.stages)
        self.assertEqual(loaded.member_ids(), ('X', 'A', 'B'))
        shared_references = [reference for stage in loaded.stages for route in stage.routes
                             for reference in route.components if reference.asset_id == 'X']
        self.assertEqual(shared_references, [original, original])
        self.assertEqual([get_asset_revision(self.db, ref.revision_id).availability
                          for ref in shared_references], [Fraction(1, 3), Fraction(1, 3)])

    def test_asset_fraction_roundtrip(self):
        rates = (Fraction(1, 3), Fraction((1 << 93) + 17, (1 << 137) + 9), Fraction(0), Fraction(1))
        ids = [put_asset(self.db, '精确参数', f'参数 {i}', rate) for i, rate in enumerate(rates)]
        self.db.close()
        reopened = self.open_database()
        for index, (revision_id, expected) in enumerate(zip(ids, rates, strict=True)):
            with self.subTest(index=index):
                revision = get_asset_revision(reopened, revision_id)
                self.assertEqual((revision.asset_id, revision.description), ('精确参数', f'参数 {index}'))
                self.assertEqual(revision.availability, expected)
                self.assertIsInstance(revision.availability, Fraction)
        self.assertEqual(get_current_asset_revision(reopened, '精确参数').revision_id, ids[-1])
        with self.assertRaises(UnknownAssetRevision):
            get_asset_revision(reopened, ids[-1] + 1)

    def test_invalid_asset(self):
        previous = get_current_asset_revision(self.db, 'X')
        cases = (
            ('', '说明', Fraction(1, 2)), (' X ', '说明', Fraction(1, 2)),
            (1, '说明', Fraction(1, 2)), ('X', None, Fraction(1, 2)),
            ('X', '说明', Fraction(-1, 3)), ('X', '说明', Fraction(4, 3)),
            ('X', '说明', 0.5), ('X', '说明', True),
        )
        for asset_id, description, rate in cases:
            with self.subTest(asset_id=asset_id, rate=rate, description=description):
                with self.assertRaises(InvalidAsset):
                    put_asset(self.db, asset_id, description, rate)
        self.assertEqual(get_current_asset_revision(self.db, 'X'), previous)
        self.assertEqual(self.db.execute('SELECT count(*) FROM asset_revision').fetchone(), (3,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM asset_identity').fetchone(), (3,))

    def test_mixed_asset_revision(self):
        corrected = AssetReference('X', put_asset(self.db, 'X', '检修', Fraction(2, 3)))
        mixed = (self.stages[0], Stage('polish', (Route('supply', (corrected, self.refs['B'])),)))
        with self.assertRaisesRegex(InvalidLayout, 'different revisions'):
            save_layout(self.db, mixed)
        self._assert_only_original_layout()
        replacement = save_layout(self.db, shared_stages({**self.refs, 'X': corrected}))
        self.assertEqual(load_layout_revision(self.db, replacement).stages[0].routes[0].components, (corrected,))

    def test_invalid_layout(self):
        stage = self.stages[0]
        cases = (
            (), (stage, stage), (Stage('intake', ()),),
            (Stage('intake', (stage.routes[0], stage.routes[0])),),
            (Stage('intake', (Route('empty', ()),)),),
            (Stage('', stage.routes),), (Stage('intake', (Route('', (self.refs['A'],)),)),),
        )
        for case in cases:
            with self.subTest(stages=case):
                with self.assertRaises(InvalidLayout):
                    save_layout(self.db, case)
                self._assert_only_original_layout()

    def test_unknown_revision(self):
        for reference in (AssetReference('X', 9000), AssetReference('X', self.refs['A'].revision_id)):
            with self.subTest(reference=reference):
                with self.assertRaises(InvalidLayout):
                    save_layout(self.db, (Stage('intake', (Route('feed', (reference,)),)),))
                self._assert_only_original_layout()
        with self.assertRaises(UnknownLayoutRevision):
            load_layout_revision(self.db, 9000)

    def _assert_only_original_layout(self):
        rows = self.db.execute('SELECT revision_id FROM layout_revision').fetchall()
        self.assertEqual(rows, [(self.layout_id,)])
        self.assertEqual(load_layout_revision(self.db, self.layout_id).stages, self.stages)
