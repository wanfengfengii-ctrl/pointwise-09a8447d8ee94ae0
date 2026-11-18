import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog import put_asset
from evidence import EvidenceRepository, put_observations
from tests.fixtures import initialize_database
from topology import AssetReference, Route, Stage, load_layout_revision, save_layout


INCIDENT_KEY = "冷却改版巡检"
FULL_READINGS = (("Z", True), ("A", False), ("M", False))
PARTIAL_READINGS = (("A", False),)
CROSSED_READINGS = (("U", False), ("V", False))


@dataclass(frozen=True)
class CarryCases:
    old_layout_id: int
    new_layout_id: int
    no_match_layout_id: int
    full_source_id: int
    partial_source_id: int
    crossed_old_layout_id: int
    crossed_new_layout_id: int
    crossed_source_id: int


def _stage(name: str, *routes: tuple[AssetReference, ...]) -> Stage:
    return Stage(name, tuple(Route(f"{name}-{i}", refs) for i, refs in enumerate(routes, 1)))


def seed_cases(db: sqlite3.Connection) -> CarryCases:
    p, q, t = (
        AssetReference(name, put_asset(db, name, f"巡检部件 {name}", Fraction(1, 2)))
        for name in ("P", "Q", "T")
    )
    old = save_layout(db, (_stage("Z", (p,)), _stage("A", (p,)), _stage("M", (q,))))
    full = put_observations(db, INCIDENT_KEY, old, reversed(FULL_READINGS))
    partial = put_observations(db, INCIDENT_KEY, old, PARTIAL_READINGS)
    corrected_p = AssetReference("P", put_asset(db, "P", "改版时更正参数", Fraction(2, 3)))
    new = save_layout(db, (_stage("R", (corrected_p, corrected_p)),
                           _stage("S", (t, q, q), (q,), (q,))))
    no_match = save_layout(db, (_stage("Z", (corrected_p, t)),))
    crossed_old = save_layout(db, (_stage("U", (p,)), _stage("V", (q,))))
    crossed_new = save_layout(db, (_stage("V", (q,)), _stage("U", (corrected_p,))))
    crossed = put_observations(db, INCIDENT_KEY, crossed_old, CROSSED_READINGS)
    return CarryCases(old, new, no_match, full, partial, crossed_old, crossed_new, crossed)


@contextmanager
def fail_observation_commit(db: sqlite3.Connection) -> Iterator[None]:
    """Use a deferred foreign key to reject a fixture observation at commit."""
    if db.in_transaction or db.execute("PRAGMA foreign_keys").fetchone() != (1,):
        raise ValueError("fixture needs an idle connection with foreign keys enabled")
    db.executescript("""
        CREATE TEMP TABLE carry_fixture_parent (id INTEGER PRIMARY KEY);
        CREATE TEMP TABLE carry_fixture_child (
            id INTEGER NOT NULL REFERENCES carry_fixture_parent(id) DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TEMP TRIGGER carry_fixture_reject AFTER INSERT ON main.observation_revision
        BEGIN
            INSERT INTO carry_fixture_child (id) VALUES (NEW.revision_id);
        END;
    """)
    try:
        yield
    finally:
        db.execute("DROP TRIGGER temp.carry_fixture_reject")
        db.execute("DROP TABLE temp.carry_fixture_child")
        db.execute("DROP TABLE temp.carry_fixture_parent")


def check_seed(db: sqlite3.Connection, cases: CarryCases) -> None:
    expected_orders = (
        (cases.old_layout_id, ("Z", "A", "M")),
        (cases.new_layout_id, ("R", "S")),
        (cases.no_match_layout_id, ("Z",)),
        (cases.crossed_old_layout_id, ("U", "V")),
        (cases.crossed_new_layout_id, ("V", "U")),
    )
    for layout_id, expected in expected_orders:
        actual = tuple(stage.name for stage in load_layout_revision(db, layout_id).stages)
        if actual != expected:
            raise AssertionError(f"layout {layout_id} has stage order {actual!r}")
    repository = EvidenceRepository(db)
    expected_sources = (
        (cases.full_source_id, cases.old_layout_id, FULL_READINGS),
        (cases.partial_source_id, cases.old_layout_id, PARTIAL_READINGS),
        (cases.crossed_source_id, cases.crossed_old_layout_id, CROSSED_READINGS),
    )
    for source_id, layout_id, readings in expected_sources:
        source = repository.find_observations(source_id)
        if source is None or (source.incident_key, source.layout_revision_id, source.readings) != (
            INCIDENT_KEY, layout_id, readings
        ):
            raise AssertionError(f"unexpected observation batch {source!r}")


def check_fault_fixture(db: sqlite3.Connection, cases: CarryCases) -> None:
    before = db.execute("SELECT revision_id FROM observation_revision ORDER BY revision_id").fetchall()
    with fail_observation_commit(db):
        try:
            put_observations(db, INCIDENT_KEY, cases.new_layout_id, {"S": False})
        except sqlite3.IntegrityError as exc:
            if str(exc) != "FOREIGN KEY constraint failed":
                raise
        else:
            raise AssertionError("fixture did not reject the commit")
        if db.in_transaction:
            raise AssertionError("failed commit left an active transaction")
    after = db.execute("SELECT revision_id FROM observation_revision ORDER BY revision_id").fetchall()
    if after != before:
        raise AssertionError("failed commit changed the observation batches")


def main() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "carry.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            initialize_database(db)
            cases = seed_cases(db)
            check_fault_fixture(db, cases)
        with closing(sqlite3.connect(path)) as db:
            check_seed(db, cases)
            source = EvidenceRepository(db).find_observations(cases.full_source_id)
            target = load_layout_revision(db, cases.new_layout_id)
            print(json.dumps({
                "source_layout_id": source.layout_revision_id,
                "source_readings": source.readings,
                "target_layout_id": target.revision_id,
                "target_stages": [stage.name for stage in target.stages],
            }, ensure_ascii=False))


if __name__ == "__main__":
    main()
