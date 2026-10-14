import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .policy import LICENSES, BLOCKED_URLS, BLOCKED_SOURCES, acceptable, can_use, normalize_query, styles_for, public_https

VISIBLE="coalesce(r.duplicate_of,'')='' AND coalesce(r.safety_state,'') NOT IN ('blocked','review-required') AND coalesce(r.quality_state,'')!='rejected'"

def now():
    return datetime.now(timezone.utc).isoformat()

class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path,timeout=30)
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
        CREATE INDEX IF NOT EXISTS assets_license ON assets(active,license);
        CREATE VIRTUAL TABLE IF NOT EXISTS assets_fts USING fts5(id UNINDEXED, title, tags, styles, tokenize='unicode61');
        CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_runs (id INTEGER PRIMARY KEY, source TEXT, started TEXT, completed TEXT, status TEXT, count INTEGER, error TEXT);
        CREATE TABLE IF NOT EXISTS asset_details (asset_id TEXT PRIMARY KEY,data TEXT NOT NULL);
        ''')
        from .organization import initialize
        initialize(self)

    def close(self):
        self.db.close()

    def source(self, item):
        previous=self.source_info(item['id'])
        self.db.execute("INSERT OR REPLACE INTO sources VALUES (?,?)", (item['id'], json.dumps({**previous,**item}, ensure_ascii=False)))

    def set_details(self,asset_id,data):
        previous=self.details(asset_id)
        def content_key(d):
            original=[]
            for f in d.get('files',[]):
                if f.get('role')=='provenance':continue
                original.append({k:f.get(k) for k in ('role','relative_path','filename','sha','sha256','bytes','crc32','archive_entry','container_id')})
                if not f.get('sha') and not f.get('sha256'):original[-1]['url']=f.get('url')
            return json.dumps({'files':original,'previews':d.get('previews',[]),'legal':d.get('legal',[]),'reference_preview':d.get('reference_preview')},sort_keys=True)
        if previous and content_key(previous)!=content_key(data):self.db.execute('DELETE FROM curation WHERE asset_id=?',(asset_id,))
        self.db.execute('INSERT OR REPLACE INTO asset_details VALUES (?,?)',(asset_id,json.dumps(data,ensure_ascii=False)))

    def details(self,asset_id):
        row=self.db.execute('SELECT data FROM asset_details WHERE asset_id=?',(asset_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def source_info(self,source_id):
        row=self.db.execute('SELECT data FROM sources WHERE id=?',(source_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    def facets(self,kind='',mode='usable',section='',pack=''):
        if mode not in {'usable','reference','all'}: raise ValueError('Invalid mode')
        where,args=['a.active=1',VISIBLE],[]
        for field,value in (('kind',kind),('mode','' if mode=='all' else mode)):
            if value: where.append('a.'+field+'=?'); args.append(value)
        if section:
            from .organization import LEAVES
            if section not in LEAVES and not any(x.startswith(section+'/') for x in LEAVES):raise ValueError('Unknown section ID')
            where.append('(s.section_id=? OR s.section_id LIKE ?)');args.extend([section,section+'/%'])
        if pack:where.append('s.pack_id=?');args.append(pack)
        clause=' WHERE '+' AND '.join(where)
        base=' FROM assets a LEFT JOIN curation r ON r.asset_id=a.id LEFT JOIN asset_sections s ON s.asset_id=a.id'
        groups={field:dict(self.db.execute('SELECT a.'+field+',count(*)'+base+clause+' GROUP BY a.'+field,args).fetchall()) for field in ('kind','license')}
        for field in ('styles','platforms','formats'):
            groups[field]=dict(self.db.execute('SELECT j.value,count(*)'+base+',json_each(a.'+field+') j'+clause+' GROUP BY j.value ORDER BY count(*) DESC LIMIT 100',args).fetchall())
        return groups

    def seek(self,query='',kind='',style='',platform='',mode='usable',source='',format='',section='',pack='',after_id='',after_score=None,limit=30):
        if mode not in {'usable','reference','all'} or not 1<=limit<=100: raise ValueError('Invalid browsing filters')
        terms=normalize_query(query).split()[:16]
        where,args=['a.active=1',"coalesce(r.duplicate_of,'')=''","coalesce(r.safety_state,'') NOT IN ('blocked','review-required')","coalesce(r.quality_state,'')!='rejected'"],[]
        join=' LEFT JOIN curation r ON r.asset_id=a.id LEFT JOIN asset_sections s ON s.asset_id=a.id'; score='0.0'; order='a.id'
        if terms:
            join+=' JOIN assets_fts ON assets_fts.rowid=a.rowid'
            where.append('assets_fts MATCH ?'); args.append(' AND '.join('"'+t.replace('"','""')+'"' for t in terms))
            score='bm25(assets_fts)'; order=score+',a.id'
        for field,value in (('kind',kind),('mode','' if mode=='all' else mode),('source',source)):
            if value: where.append('a.'+field+'=?'); args.append(value)
        if section:
            from .organization import LEAVES
            if section not in LEAVES and not any(x.startswith(section+'/') for x in LEAVES): raise ValueError('Unknown section ID')
            where.append('(s.section_id=? OR s.section_id LIKE ?)');args.extend([section,section+'/%'])
        if pack:where.append('s.pack_id=?');args.append(pack)
        for field,value in (('styles',normalize_query(style)),('platforms',platform),('formats',format)):
            if value: where.append('EXISTS(SELECT 1 FROM json_each(a.'+field+') WHERE value=?)'); args.append(value)
        if after_id:
            if terms:
                if after_score is None: raise ValueError('Search cursor needs its score')
                where.append('('+score+'>? OR ('+score+'=? AND a.id>?))'); args.extend([after_score,after_score,after_id])
            else: where.append('a.id>?'); args.append(after_id)
        rows=self.db.execute('SELECT a.*,s.section_id,s.pack_id,r.quality_state,r.safety_state AS safety_review,r.duplicate_of,'+score+' AS match_score FROM assets a'+join+' WHERE '+' AND '.join(where)+' ORDER BY '+order+' LIMIT ?',args+[limit+1]).fetchall()
        items=[self.decode(row) for row in rows[:limit]]
        return {'items':items,'next':{'id':items[-1]['id'],'score':items[-1]['match_score']} if len(rows)>limit else None}

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
        if previous and previous['revision']!=revision:
            self.db.execute('DELETE FROM curation WHERE asset_id=?',(item_id,))
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
        row = self.db.execute("SELECT a.*,s.section_id,s.pack_id,r.quality_state,r.safety_state AS safety_review,r.duplicate_of FROM assets a LEFT JOIN asset_sections s ON s.asset_id=a.id LEFT JOIN curation r ON r.asset_id=a.id WHERE a.id=? AND a.active=1", (asset_id,)).fetchone()
        return self.decode(row) if row else None

    def search(self, query="", kind="", style="", platform="", mode="usable", source="", license="", limit=20, offset=0, count_total=True):
        if mode not in {"usable", "reference", "all"}:
            raise ValueError("mode must be usable, reference, or all")
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000000:
            raise ValueError("limit must be 1..100 and offset 0..10000000")
        where, args = ["a.active=1",VISIBLE], []
        terms = normalize_query(query).split()[:16]
        join, order = " LEFT JOIN curation r ON r.asset_id=a.id", "a.id"
        if terms:
            # Quote each FTS token so arbitrary caller text cannot inject FTS operators.
            match = " AND ".join('"' + t.replace('"', '""') + '"' for t in terms)
            join += " JOIN assets_fts ON a.rowid=assets_fts.rowid"
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
        rows = self.db.execute("SELECT a.*,r.quality_state,r.safety_state AS safety_review,r.duplicate_of" + sql + f" ORDER BY {order} LIMIT ? OFFSET ?", args + [limit+1, offset]).fetchall()
        return {"total": count, "offset": offset, "next_offset": offset + limit if len(rows)>limit else None, "items": [self.decode(r) for r in rows[:limit]]}

    def browse(self, after_id="", kind="", source="", mode="usable", limit=50):
        if mode not in {"usable", "reference", "all"} or not 1 <= limit <= 100:
            raise ValueError("Invalid mode or page size")
        where,args=["a.active=1", "a.id>?",VISIBLE],[after_id]
        for field,value in (("kind",kind),("source",source),("mode","" if mode == "all" else mode)):
            if value:
                where.append('a.'+field+"=?"); args.append(value)
        rows=self.db.execute("SELECT a.*,r.quality_state,r.safety_state AS safety_review,r.duplicate_of FROM assets a LEFT JOIN curation r ON r.asset_id=a.id WHERE "+" AND ".join(where)+" ORDER BY a.id LIMIT ?",args+[limit+1]).fetchall()
        items=[self.decode(r) for r in rows[:limit]]
        return {"items":items,"next_cursor":items[-1]["id"] if len(rows)>limit else None}

    def sources(self, offset=0, limit=50):
        limit = min(100, max(1, limit))
        rows = self.db.execute("SELECT data FROM sources ORDER BY id LIMIT ? OFFSET ?", (limit, max(0, offset))).fetchall()
        return {"total": self.db.execute("SELECT count(*) FROM sources").fetchone()[0], "items": [json.loads(r[0]) for r in rows], "offset": offset}

    def stats(self):
        groups = lambda field: dict(self.db.execute(f"SELECT {field},count(*) FROM assets WHERE active=1 GROUP BY {field}").fetchall())
        health = [dict(r) for r in self.db.execute("SELECT source,status,count,completed,error FROM sync_runs r WHERE id=(SELECT max(id) FROM sync_runs x WHERE x.source=r.source) ORDER BY source")]
        from .curation import report
        visible=dict(self.db.execute('SELECT a.mode,count(*) FROM assets a LEFT JOIN curation r ON r.asset_id=a.id WHERE a.active=1 AND '+VISIBLE+' GROUP BY a.mode'))
        usable_kinds=dict(self.db.execute("SELECT a.kind,count(*) FROM assets a LEFT JOIN curation r ON r.asset_id=a.id WHERE a.active=1 AND a.mode='usable' AND "+VISIBLE+' GROUP BY a.kind'))
        return {"active_assets": self.db.execute("SELECT count(*) FROM assets WHERE active=1").fetchone()[0], "visible_records":sum(visible.values()),"visible_by_mode":visible,"usable_by_kind":usable_kinds,"usable_records_without_icons":sum(v for k,v in usable_kinds.items() if k!='icon'),"sources": self.db.execute("SELECT count(*) FROM sources").fetchone()[0], "by_kind": groups("kind"), "by_mode": groups("mode"), "by_license": groups("license"), "curation":report(self),"source_health":health, "latest_sync": [dict(r) for r in self.db.execute("SELECT * FROM sync_runs ORDER BY id DESC LIMIT 12")], "moderation": "Read curation coverage and evidence scope. Metadata, sampled previews and original-media checks are distinct. Unreviewed repositories are references. Automated classifiers cannot certify contextual safety.", "credit": "Powered by Poly Haven; upstream licenses remain authoritative."}
