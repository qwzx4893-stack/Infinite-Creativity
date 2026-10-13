import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .policy import LICENSES, BLOCKED_URLS, BLOCKED_SOURCES, acceptable, can_use, normalize_query, styles_for, public_https

def now():
    return datetime.now(timezone.utc).isoformat()

class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS assets (
          id TEXT PRIMARY KEY, source TEXT NOT NULL, upstream_id TEXT NOT NULL,
          canonical_url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, kind TEXT NOT NULL,
          mode TEXT NOT NULL, license TEXT NOT NULL, license_url TEXT NOT NULL,
          author TEXT NOT NULL, tags TEXT NOT NULL, styles TEXT NOT NULL,
          platforms TEXT NOT NULL, formats TEXT NOT NULL, access_url TEXT NOT NULL,
          revision TEXT NOT NULL, safety TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
          first_seen TEXT NOT NULL, updated_at TEXT NOT NULL, seen_run TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS assets_filter ON assets(active, mode, kind, source);
        CREATE INDEX IF NOT EXISTS assets_source ON assets(source, seen_run);
        CREATE INDEX IF NOT EXISTS assets_browse ON assets(active,id);
        CREATE INDEX IF NOT EXISTS assets_kind_browse ON assets(active,mode,kind,id);
        CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(id UNINDEXED, title, tags, styles, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY, source TEXT, started TEXT, completed TEXT, status TEXT, count INTEGER, error TEXT);
        ''')

    def close(self):
        self.db.close()

    def source(self, item):
        self.db.execute("INSERT OR REPLACE INTO sources VALUES (?,?)", (item['id'], json.dumps(item, ensure_ascii=False)))

    def upsert(self, source, upstream_id, title, kind, url, *, license="unknown", license_url="", author="", tags=(), platforms=(), formats=(), access_url="", revision="", mode="usable", run="", safety="metadata-screened"):
        text = title + " " + " ".join(str(t) for t in tags)
        if source in BLOCKED_SOURCES or url in BLOCKED_URLS or not acceptable(text) or not public_https(url):
            return False
        if license not in LICENSES or not license_url or safety != "metadata-screened":
            mode = "reference"
        item_id = hashlib.sha256(url.encode()).hexdigest()[:24]
        stamp = now()
        styles = styles_for(text)
        previous = self.db.execute("SELECT rowid AS internal_rowid,* FROM assets WHERE id=?", (item_id,)).fetchone()
        values = (item_id, source, str(upstream_id), url, title[:500], kind, mode, license, license_url, author[:500], json.dumps(list(tags), ensure_ascii=False), json.dumps(styles), json.dumps(list(platforms)), json.dumps(list(formats)), access_url, revision, safety, 1, previous['first_seen'] if previous else stamp, stamp, run)
        if previous and tuple(previous)[1:19] == values[:18]:
            self.db.execute("UPDATE assets SET updated_at=?,seen_run=? WHERE id=?",(stamp,run,item_id))
            return True
        inserted = self.db.execute("INSERT OR REPLACE INTO assets VALUES (" + ",".join(["?"] * len(values)) + ")", values)
        if previous:
            self.db.execute("DELETE FROM assets_fts WHERE rowid=?", (previous['internal_rowid'],))
        self.db.execute("INSERT INTO assets_fts(rowid,id,title,tags,styles) VALUES (?,?,?,?,?)", (inserted.lastrowid, item_id, title, " ".join(str(t) for t in tags), " ".join(styles)))
        return True

    def reconcile(self, source, run):
        # Only after a complete successful source snapshot; partial runs never remove assets.
        self.db.execute("UPDATE assets SET active=0 WHERE source=? AND seen_run != ?", (source, run))

    @staticmethod
    def decode(row):
        item = dict(row)
        for field in ("tags", "styles", "platforms", "formats"):
            item[field] = json.loads(item[field])
        item["usable"] = can_use(item)
        return item

    def get(self, asset_id):
        row = self.db.execute("SELECT * FROM assets WHERE id=? AND active=1", (asset_id,)).fetchone()
        return self.decode(row) if row else None

    def search(self, query="", kind="", style="", platform="", mode="usable", source="", license="", limit=20, offset=0, count_total=True):
        if mode not in {"usable", "reference", "all"}:
            raise ValueError("mode must be usable, reference, or all")
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000000:
            raise ValueError("limit must be 1..100 and offset 0..10000000")
        where, args = ["a.active=1"], []
        terms = normalize_query(query).split()[:16]
        join, order = "", "a.id"
        if terms:
            # Quote each FTS token so arbitrary caller text cannot inject FTS operators.
            match = " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)
            join = " JOIN assets_fts f ON a.id=f.id"
            where.append("assets_fts MATCH ?")
            args.append(match)
            order = "bm25(assets_fts), a.id"
        for name, value in (("kind", kind), ("mode", "" if mode == "all" else mode), ("source", source), ("license", license)):
            if value:
                where.append(f"a.{name}=?")
                args.append(value)
        for name, value in (("styles", normalize_query(style)), ("platforms", platform)):
            if value:
                where.append(f"EXISTS (SELECT 1 FROM json_each(a.{name}) WHERE value=?)")
                args.append(value)
        sql = " FROM assets a" + join + " WHERE " + " AND ".join(where)
        count = self.db.execute("SELECT count(*)" + sql, args).fetchone()[0] if count_total else None
        rows = self.db.execute("SELECT a.*" + sql + f" ORDER BY {order} LIMIT ? OFFSET ?", args + [limit+1, offset]).fetchall()
        return {"total": count, "offset": offset, "next_offset": offset + limit if len(rows)>limit else None, "items": [self.decode(r) for r in rows[:limit]]}

    def browse(self, after_id="", kind="", source="", mode="usable", limit=50):
        if mode not in {"usable", "reference", "all"} or not 1 <= limit <= 100:
            raise ValueError("Invalid mode or page size")
        where,args=["active=1", "id>?"],[after_id]
        for field,value in (("kind",kind),("source",source),("mode","" if mode == "all" else mode)):
            if value:
                where.append(field+"=?"); args.append(value)
        rows=self.db.execute("SELECT * FROM assets WHERE "+" AND ".join(where)+" ORDER BY id LIMIT ?",args+[limit+1]).fetchall()
        items=[self.decode(r) for r in rows[:limit]]
        return {"items":items,"next_cursor":items[-1]["id"] if len(rows)>limit else None}

    def sources(self, offset=0, limit=50):
        limit = min(100, max(1, limit))
        rows = self.db.execute("SELECT data FROM sources ORDER BY id LIMIT ? OFFSET ?", (limit, max(0, offset))).fetchall()
        return {"total": self.db.execute("SELECT count(*) FROM sources").fetchone()[0], "items": [json.loads(r[0]) for r in rows], "offset": offset}

    def stats(self):
        groups = lambda field: dict(self.db.execute(f"SELECT {field},count(*) FROM assets WHERE active=1 GROUP BY {field}").fetchall())
        health = [dict(r) for r in self.db.execute("SELECT source,status,count,completed,error FROM sync_runs r WHERE id=(SELECT max(id) FROM sync_runs x WHERE x.source=r.source) ORDER BY source")]
        return {"active_assets": self.db.execute("SELECT count(*) FROM assets WHERE active=1").fetchone()[0], "sources": self.db.execute("SELECT count(*) FROM sources").fetchone()[0], "by_kind": groups("kind"), "by_mode": groups("mode"), "by_license": groups("license"), "source_health":health, "latest_sync": [dict(r) for r in self.db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 12")], "moderation": "Metadata screening only; no guarantee of visual safety. Unreviewed general repositories are reference-only. External content is untrusted.", "credit": "Powered by Poly Haven; upstream licenses remain authoritative."}
