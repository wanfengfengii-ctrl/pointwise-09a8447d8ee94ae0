import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from catalog import put_asset
from evidence import (EvidenceRepository, carry_observations, freeze_incident, load_incident,
                      put_observations, read_carry)
from tests.fixtures import initialize_database
from topology import (AssetReference, Route, Stage, eligible_stage_pairs, load_layout_revision,
                      save_layout)


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


def check_carry_example(db: sqlite3.Connection, cases: CarryCases) -> None:
    """Exercise the documented alignment, ambiguity, empty batch and fault retry."""
    candidates = eligible_stage_pairs(db, cases.old_layout_id, cases.new_layout_id)
    if candidates != (("Z", "R"), ("A", "R"), ("M", "S")):
        raise AssertionError(f"unexpected candidates {candidates!r}")
    full_id = carry_observations(db, cases.full_source_id, cases.new_layout_id)
    incident_id = freeze_incident(db, cases.new_layout_id, full_id)
    readings = load_incident(db, incident_id).observations
    if readings.reading_for("R") is not None or readings.reading_for("S") is not False:
        raise AssertionError(f"unexpected carried readings {readings.readings!r}")
    expected = {
        "source_observation_id": cases.full_source_id,
        "old_layout_id": cases.old_layout_id,
        "new_layout_id": cases.new_layout_id,
        "matches": (("M", "S", False),),
    }
    if read_carry(db, full_id) != expected:
        raise AssertionError(f"unexpected carry record {read_carry(db, full_id)!r}")
    partial_id = carry_observations(db, cases.partial_source_id, cases.new_layout_id)
    if read_carry(db, partial_id)["matches"] != ():
        raise AssertionError("a partial source with no explicit aligned reading must carry nothing")
    if EvidenceRepository(db).find_observations(partial_id).readings != ():
        raise AssertionError("the partial derived batch must stay empty")
    empty_id = carry_observations(db, cases.full_source_id, cases.no_match_layout_id)
    if read_carry(db, empty_id)["matches"] != ():
        raise AssertionError("a target with no equivalent stages must carry nothing")
    crossed_id = carry_observations(db, cases.crossed_source_id, cases.crossed_new_layout_id)
    if read_carry(db, crossed_id)["matches"] != ():
        raise AssertionError("two competing maximum alignments must carry nothing")
    crossed_incident = freeze_incident(db, cases.crossed_new_layout_id, crossed_id)
    crossed_readings = load_incident(db, crossed_incident).observations
    if (crossed_readings.reading_for("U"), crossed_readings.reading_for("V")) != (None, None):
        raise AssertionError("ambiguous stages must stay unobserved")


def check_carry_fault(db: sqlite3.Connection, cases: CarryCases) -> None:
    """A failed commit leaves no derived batch or source and a retry succeeds."""
    before = {
        table: db.execute(f"SELECT count(*) FROM {table}").fetchone()
        for table in ("observation_revision", "observation_reading", "carry_batch", "carry_match")
    }
    with fail_observation_commit(db):
        try:
            carry_observations(db, cases.full_source_id, cases.new_layout_id)
        except sqlite3.IntegrityError as exc:
            if str(exc) != "FOREIGN KEY constraint failed":
                raise
        else:
            raise AssertionError("fixture did not reject the carry commit")
        if db.in_transaction:
            raise AssertionError("failed carry commit left an active transaction")
    after = {
        table: db.execute(f"SELECT count(*) FROM {table}").fetchone()
        for table in ("observation_revision", "observation_reading", "carry_batch", "carry_match")
    }
    if after != before:
        raise AssertionError("failed carry commit left a derived batch or source behind")
    retried_id = carry_observations(db, cases.full_source_id, cases.new_layout_id)
    if read_carry(db, retried_id)["matches"] != (("M", "S", False),):
        raise AssertionError("retry after the fault did not publish the carried match")


def check_reopened_carry(db: sqlite3.Connection, cases: CarryCases) -> dict:
    """Read the published derivation back by number without recomputing."""
    full_id = carry_observations(db, cases.full_source_id, cases.new_layout_id)
    published = read_carry(db, full_id)
    reopened = read_carry(db, full_id)
    if reopened != published:
        raise AssertionError(f"reopened carry record changed: {reopened!r}")
    return published


def demo() -> None:
    """Show the real endpoints: candidates, explicit False carry, ambiguity, empty batch, reopen."""
    with TemporaryDirectory() as directory:
        path = Path(directory) / "demo.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            initialize_database(db)
            cases = seed_cases(db)
            candidates = eligible_stage_pairs(db, cases.old_layout_id, cases.new_layout_id)
            full_id = carry_observations(db, cases.full_source_id, cases.new_layout_id)
            incident_id = freeze_incident(db, cases.new_layout_id, full_id)
            readings = load_incident(db, incident_id).observations
            crossed_id = carry_observations(db, cases.crossed_source_id, cases.crossed_new_layout_id)
            crossed_incident = freeze_incident(db, cases.crossed_new_layout_id, crossed_id)
            crossed_readings = load_incident(db, crossed_incident).observations
            empty_id = carry_observations(db, cases.full_source_id, cases.no_match_layout_id)
            before_supplement = {
                "candidates": candidates,
                "r_reading": readings.reading_for("R"),
                "s_reading": readings.reading_for("S"),
                "full_carry": read_carry(db, full_id),
                "crossed_carry": read_carry(db, crossed_id),
                "crossed_u": crossed_readings.reading_for("U"),
                "crossed_v": crossed_readings.reading_for("V"),
                "empty_carry": read_carry(db, empty_id),
                "empty_incident": load_incident(
                    db, freeze_incident(db, cases.no_match_layout_id, empty_id)).observations.readings,
            }
            put_observations(db, INCIDENT_KEY, cases.new_layout_id, (("S", True),))
        with closing(sqlite3.connect(path)) as db:
            reopened = read_carry(db, full_id)
            source = EvidenceRepository(db).find_observations(reopened["source_observation_id"])
            old_layout = load_layout_revision(db, reopened["old_layout_id"])
            new_layout = load_layout_revision(db, reopened["new_layout_id"])
            after_supplement = {
                "reopened_full_carry": reopened,
                "source_readings": EvidenceRepository(db).find_observations(
                    cases.full_source_id).readings,
                "source_still": source.readings,
                "old_stages": [stage.name for stage in old_layout.stages],
                "new_stages": [stage.name for stage in new_layout.stages],
                "per_stage_sources": {
                    old_name: {"new_stage": new_name, "reading": value}
                    for old_name, new_name, value in reopened["matches"]
                },
            }
    print(json.dumps({"demo": before_supplement, "reopened": after_supplement}, ensure_ascii=False))


def main() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "carry.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            initialize_database(db)
            cases = seed_cases(db)
            check_seed(db, cases)
            check_fault_fixture(db, cases)
            check_carry_example(db, cases)
            check_carry_fault(db, cases)
        with closing(sqlite3.connect(path)) as db:
            published = check_reopened_carry(db, cases)
            source = EvidenceRepository(db).find_observations(cases.full_source_id)
            target = load_layout_revision(db, cases.new_layout_id)
            print(json.dumps({
                "source_layout_id": source.layout_revision_id,
                "source_readings": source.readings,
                "target_layout_id": target.revision_id,
                "target_stages": [stage.name for stage in target.stages],
                "reopened_carry": published,
            }, ensure_ascii=False))


if __name__ == "__main__":
    main()
