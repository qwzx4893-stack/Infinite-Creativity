import tempfile
import unittest
from pathlib import Path
from infinite_creativity.catalog import Catalog
from infinite_creativity.policy import acceptable
from infinite_creativity.policy import BLOCKED_URLS
from infinite_creativity.service import resolve, recommend
from infinite_creativity.adapters import polyhaven, github_tree,discover_partitions
from infinite_creativity.locking import SyncLock

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=Catalog(Path(self.tmp.name)/"test.sqlite")
    def tearDown(self):
        self.c.close(); self.tmp.cleanup()
    def put(self,title="minimal outline button",source="fixture",**kwargs):
        return self.c.upsert(source,title,title,"ui-component","https://example.com/"+title.replace(' ','-'),license="MIT",license_url="https://example.com/LICENSE",platforms=["web"],access_url="https://example.com/component.tsx",**kwargs)
    def test_license_mode_and_resolve(self):
        self.put()
        a=self.c.search("button")["items"][0]
        self.assertTrue(a["usable"])
        self.assertEqual(resolve(self.c,a["id"])["license"],"MIT")
        self.put("paid button",mode="reference")
        paid=self.c.search("paid",mode="reference")["items"][0]
        with self.assertRaises(ValueError): resolve(self.c,paid["id"])
        self.c.upsert("unknown","x","unknown button","ui-component","https://example.com/unknown",license="unknown",license_url="")
        self.assertEqual(self.c.search("unknown")["total"],0)
    def test_screening(self):
        for title in ["NSFW template","nude-model","pornographic scene","middle-finger","إباحي"]:
            self.assertFalse(acceptable(title))
            self.assertFalse(self.put(title))
        self.assertTrue(self.put("ordinary wood chair"))
    def test_durable_exclusion_blocks_existing_resolution(self):
        self.put()
        asset=self.c.search()["items"][0]
        BLOCKED_URLS.add(asset["canonical_url"])
        try:
            with self.assertRaises(ValueError): resolve(self.c,asset["id"])
            self.assertFalse(self.put())
        finally: BLOCKED_URLS.remove(asset["canonical_url"])
    def test_dedupe_update_and_tombstone(self):
        self.put(run="old"); self.put(run="new")
        self.assertEqual(self.c.stats()["active_assets"],1)
        self.c.reconcile("fixture","new")
        self.assertEqual(self.c.stats()["active_assets"],1)
        self.c.reconcile("fixture","empty-success")
        self.assertEqual(self.c.search()["total"],0)
    def test_second_writer_is_rejected(self):
        with SyncLock(self.c.path):
            with self.assertRaises(RuntimeError):
                with SyncLock(self.c.path): pass
        with SyncLock(self.c.path): pass
    def test_metadata_changes_replace_search_index(self):
        url="https://example.com/stable"
        for title in ["minimal oldword", "industrial newword"]:
            self.c.upsert("fixture","stable",title,"ui-component",url,license="MIT",license_url="https://example.com/LICENSE")
        self.assertEqual(self.c.search("oldword")["total"],0)
        self.assertEqual(self.c.search("newword",style="industrial")["total"],1)
    def test_pagination_and_filters(self):
        for i in range(8): self.put(f"minimal button {i}")
        p=self.c.search("button",style="minimal",platform="web",limit=3)
        self.assertEqual(p["total"],8)
        self.assertEqual(p["next_offset"],3)
        pages=[]; cursor=""
        while True:
            data=self.c.browse(after_id=cursor,limit=3)
            pages.extend(a["id"] for a in data["items"])
            if not data["next_cursor"]: break
            cursor=data["next_cursor"]
        self.assertEqual(len(set(pages)),8)
        self.assertEqual(self.c.search('" OR *')["total"],0)
        with self.assertRaises(ValueError): self.c.search(limit=101)
    def test_style_postings_keep_exact_membership_and_signed_browse_order(self):
        for i in range(5):self.put('minimal outline button '+str(i))
        self.put('outline-like text',tags=['ordinary'])
        first=self.c.seek(style='minimal',limit=2)
        following=self.c.seek(style='minimal',after_id=first['next']['id'],limit=10)
        self.assertEqual(len(first['items'])+len(following['items']),5)
        self.assertEqual(self.c.search(style='minimal')['total'],5)
        self.assertEqual(self.c.search(style='minimal" OR *')['total'],0)
    def test_recommendations_and_arabic(self):
        self.put()
        self.assertEqual(self.c.search("زر")["total"],1)
        r=recommend(self.c,"بسيط outline",["ui-component"],"web")
        self.assertTrue(r["items"])
        self.assertIn("minimal",r["inferred_styles"])
    def test_unrestricted_shortlist_samples_media_despite_icon_volume(self):
        for i in range(120):
            self.c.upsert("icon-source-"+str(i),str(i),"minimal outline icon", "icon", "https://example.com/icon/"+str(i),license="MIT",license_url="https://example.com/LICENSE")
        self.c.upsert("models","chair","minimal outline chair","model-3d","https://example.com/chair",license="CC0-1.0",license_url="https://example.com/CC0")
        self.put()
        result=recommend(self.c,"minimal outline",limit=8)
        self.assertIn("model-3d",{a['kind'] for a in result['items']})
        self.assertIn("ui-component",{a['kind'] for a in result['items']})
        self.assertLessEqual(sum(a['kind']=='icon' for a in result['items']),2)
        self.assertTrue(all(a['resource_uri'].startswith('creativity://asset/') for a in result['items']))
    def test_partial_source_failure_preserves_previous(self):
        self.put(run="old")
        class Broken:
            def json(self,url): raise RuntimeError("offline")
        with self.assertRaises(RuntimeError): polyhaven(self.c,Broken(),"new")
        self.assertEqual(self.c.stats()["active_assets"],1)
    def test_successful_polyhaven_and_font_inventory(self):
        class Data:
            def json(self,url):
                if 'polyhaven' in url:
                    return {'chair':{'name':'Wood chair','type':2,'authors':{'Artist':'All'},'tags':['wood']}}
                if 'trees' in url:
                    return {'tree':[{'type':'blob','path':'ofl/testfont/METADATA.pb','sha':'meta'}, {'type':'blob','path':'ofl/testfont/Font.ttf','sha':'font'}, {'type':'blob','path':'ofl/testfont/OFL.txt','sha':'license'}]}
                return {'default_branch':'main','license':None}
        self.assertEqual(polyhaven(self.c,Data(),'run'),1)
        self.assertEqual(github_tree(self.c,Data(),{'id':'google-fonts','repo':'google/fonts','kind':'font','path_pattern':r'/METADATA\.pb$','license_scope_reviewed':True},'run'),1)
        a=self.c.search(kind='font')['items'][0]
        self.assertEqual(a['formats'],['ttf'])
        self.assertTrue(a['usable'])
    def test_truncated_tree_never_reconciles(self):
        self.put(source="tree",run="old")
        class Truncated:
            def json(self,url):
                return {"truncated":True} if "trees" in url else {"default_branch":"main"}
        with self.assertRaises(RuntimeError): github_tree(self.c,Truncated(),{"id":"tree","repo":"a/b"},"new")
        self.assertEqual(self.c.stats()["active_assets"],1)
    def test_partition_queue_splits_and_resumes(self):
        class Oversized:
            def json(self,url): return {'total_count':2001,'items':[]}
        class Empty:
            def json(self,url): return {'total_count':0,'items':[]}
        discover_partitions(self.c,Oversized(),'run',['topic:icons'],budget=1)
        self.assertEqual(self.c.db.execute('select count(*) from discovery_queue').fetchone()[0],2)
        discover_partitions(self.c,Empty(),'run',['topic:icons'],budget=1)
        self.assertEqual(self.c.db.execute('select count(*) from discovery_queue').fetchone()[0],1)

if __name__ == "__main__": unittest.main()
