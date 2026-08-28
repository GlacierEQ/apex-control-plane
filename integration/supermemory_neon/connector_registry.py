"""
Connector registry — CRUD for connectors tracked in Neon.

A connector is any external integration (GitHub, Notion, Supabase, Sentry, etc.)
registered in the control plane.
"""

import os
import uuid
import json
from typing import Optional
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()
psycopg2.extras.register_uuid()


class ConnectorRegistry:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or os.environ["NEON_DATABASE_URL"]
        self._conn = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = False
        return self._conn

    def register(
        self, name: str, kind: str, config: dict, enabled: bool = True
    ) -> dict:
        """Register a new connector or update existing by name."""
        sql = """
            INSERT INTO connectors (id, name, kind, config, enabled)
            VALUES (%(id)s, %(name)s, %(kind)s, %(config)s, %(enabled)s)
            ON CONFLICT (name) DO UPDATE
                SET kind = EXCLUDED.kind,
                    config = EXCLUDED.config,
                    enabled = EXCLUDED.enabled,
                    updated_at = now()
            RETURNING *;
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                {
                    "id": uuid.uuid4(),
                    "name": name,
                    "kind": kind,
                    "config": json.dumps(config),
                    "enabled": enabled,
                },
            )
            row = dict(cur.fetchone())
            self.conn.commit()
            return row

    def list_active(self) -> list[dict]:
        """Return all enabled connectors."""
        sql = "SELECT * FROM connectors WHERE enabled = true ORDER BY name;"
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]

    def record_health(self, connector_id: str, status: str, details: dict) -> str:
        """Record a health check result for a connector."""
        sql = """
            INSERT INTO connector_health_log (id, connector_id, status, details)
            VALUES (%(id)s, %(connector_id)s, %(status)s, %(details)s)
            RETURNING id;
        """
        log_id = str(uuid.uuid4())
        with self.conn.cursor() as cur:
            cur.execute(
                sql,
                {
                    "id": log_id,
                    "connector_id": connector_id,
                    "status": status,
                    "details": json.dumps(details),
                },
            )
        sql_update = """
            UPDATE connectors
            SET last_health_at = now(), last_health_status = %(status)s
            WHERE id = %(id)s;
        """
        with self.conn.cursor() as cur:
            cur.execute(sql_update, {"id": connector_id, "status": status})
        self.conn.commit()
        return log_id
