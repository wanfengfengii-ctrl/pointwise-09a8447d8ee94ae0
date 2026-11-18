from itertools import groupby
from operator import itemgetter
from sqlite3 import Connection

from catalog.repository import is_revision_number, write_transaction

from .definition import AssetReference, LayoutRevision, Route, Stage


class LayoutRepository:
    def __init__(self, db: Connection):
        self.db = db

    def initialize(self) -> None:
        with write_transaction(self.db):
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS layout_revision (
                    revision_id INTEGER PRIMARY KEY
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS layout_stage (
                    layout_revision_id INTEGER NOT NULL REFERENCES layout_revision(revision_id),
                    stage_position INTEGER NOT NULL,
                    stage_name TEXT NOT NULL,
                    PRIMARY KEY (layout_revision_id, stage_position),
                    UNIQUE (layout_revision_id, stage_name)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS layout_route (
                    layout_revision_id INTEGER NOT NULL,
                    stage_position INTEGER NOT NULL,
                    route_position INTEGER NOT NULL,
                    route_name TEXT NOT NULL,
                    PRIMARY KEY (layout_revision_id, stage_position, route_position),
                    UNIQUE (layout_revision_id, stage_position, route_name),
                    FOREIGN KEY (layout_revision_id, stage_position)
                        REFERENCES layout_stage(layout_revision_id, stage_position)
                )
            ''')
            self.db.execute('''
                CREATE TABLE IF NOT EXISTS layout_component (
                    layout_revision_id INTEGER NOT NULL,
                    stage_position INTEGER NOT NULL,
                    route_position INTEGER NOT NULL,
                    component_position INTEGER NOT NULL,
                    asset_id TEXT NOT NULL,
                    asset_revision_id INTEGER NOT NULL,
                    PRIMARY KEY (layout_revision_id, stage_position, route_position, component_position),
                    FOREIGN KEY (layout_revision_id, stage_position, route_position)
                        REFERENCES layout_route(layout_revision_id, stage_position, route_position),
                    FOREIGN KEY (asset_id, asset_revision_id)
                        REFERENCES asset_revision(asset_id, revision_id)
                )
            ''')

    def insert_revision(self, stages: tuple[Stage, ...]) -> int:
        with write_transaction(self.db):
            revision_id = self.db.execute('INSERT INTO layout_revision DEFAULT VALUES').lastrowid
            for stage_position, stage in enumerate(stages):
                self.db.execute('''
                    INSERT INTO layout_stage (layout_revision_id, stage_position, stage_name)
                    VALUES (?, ?, ?)
                ''', (revision_id, stage_position, stage.name))
                for route_position, route in enumerate(stage.routes):
                    self.db.execute('''
                        INSERT INTO layout_route
                            (layout_revision_id, stage_position, route_position, route_name)
                        VALUES (?, ?, ?, ?)
                    ''', (revision_id, stage_position, route_position, route.name))
                    self.db.executemany('''
                        INSERT INTO layout_component
                            (layout_revision_id, stage_position, route_position,
                             component_position, asset_id, asset_revision_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        (revision_id, stage_position, route_position, position,
                         reference.asset_id, reference.revision_id)
                        for position, reference in enumerate(route.components)
                    ))
        return revision_id

    def find_revision(self, revision_id: int) -> LayoutRevision | None:
        if not is_revision_number(revision_id):
            return None
        rows = self.db.execute('''
            SELECT s.stage_name, r.route_name, c.asset_id, c.asset_revision_id
            FROM layout_stage AS s
            JOIN layout_route AS r USING (layout_revision_id, stage_position)
            JOIN layout_component AS c USING (layout_revision_id, stage_position, route_position)
            WHERE s.layout_revision_id = ?
            ORDER BY s.stage_position, r.route_position, c.component_position
        ''', (revision_id,))
        stages = []
        for stage_name, stage_rows in groupby(rows, key=itemgetter(0)):
            routes = []
            for route_name, route_rows in groupby(stage_rows, key=itemgetter(1)):
                components = tuple(AssetReference(row[2], row[3]) for row in route_rows)
                routes.append(Route(route_name, components))
            stages.append(Stage(stage_name, tuple(routes)))
        if not stages:
            return None
        return LayoutRevision(revision_id, tuple(stages))
