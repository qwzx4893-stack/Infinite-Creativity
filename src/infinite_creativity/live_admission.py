"""Admission happens before a live card is emitted, without a saved verdict index."""
import hashlib
import io
import json
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from .policy import acceptable, review_terms


def model_path():
    return Path(os.environ.get('IC_VISION_MODEL', str(Path.home()/'.cache/infinite-creativity/nsfw-five-class')))


@lru_cache(maxsize=2)
def _screener(path):
    # Only pinned model software stays loaded; no item data or verdict survives.
    from .vision import Screener
    return Screener(path)

def screener(path):
    from .request_scope import CURRENT
    if CURRENT.get() is not None:
        from .media_process import RemoteScreener
        return RemoteScreener(path)
    return _screener(path)


def identities(a):
    result = ['item:' + hashlib.sha256((a['source']+'|'+a['key']+'|'+a.get('revision','')+'|'+a['license']).encode()).hexdigest()]
    if a.get('origin_identity'):result.append('origin-product:'+hashlib.sha256(a['origin_identity'].encode()).hexdigest())
    signatures=[]
    for f in a.get('files', []):
        if f.get('role') not in {'main', 'variant','dependency'}: continue
        signature=None
        for name in ('sha256', 'sha', 'md5'):
            if f.get(name):signature=name+':'+str(f[name]);break
        if signature:signatures.append(signature)
        else:signatures=[];break
    # A common mesh with different material dependencies is not a duplicate.
    if signatures:result.append('bundle:'+hashlib.sha256((a['license']+'|'+json.dumps(sorted(signatures))).encode()).hexdigest())
    if a.get('origin_url'): result.append('origin:'+hashlib.sha256((a['origin_url']+'|'+a.get('revision','')).encode()).hexdigest())
    return result


class Admission:
    def __init__(self, http, seen=()):
        self.http=http; self.seen=set(seen);self.seen_order=list(seen); self.mode=os.environ.get('IC_SAFETY_MODE','strict')
        if self.mode not in {'strict','metadata'}: raise ValueError('IC_SAFETY_MODE must be strict or metadata')
        self.report={'examined':0,'admitted':0,'duplicates':0,'blocked_metadata':0,
                     'withheld_media':0,'invalid_media':0,'withheld_reasons':{}}
    def withhold(self, reason):
        self.last_withhold=reason
        self.report['withheld_media']+=1
        self.report['withheld_reasons'][reason]=self.report['withheld_reasons'].get(reason,0)+1
        return False
    def review_backend(self,a):
        configured=os.environ.get('IC_MEDIA_REVIEW_COMMAND')
        if not configured:return None
        argv=json.loads(configured)
        if not isinstance(argv,list) or not argv or not all(isinstance(v,str) for v in argv):raise ValueError('Reviewer command must be a JSON argv array')
        request={'version':1,'item':a,'required_revision':a['revision'],'required_checks':['sexual','suggestive','technical-quality'],
                 'notice':'Assess current original media, not only a thumbnail. Do not retain items.'}
        # This is a local operator-configured program, never a tool parameter or
        # a command obtained from upstream content. No shell is used.
        with tempfile.TemporaryFile() as output:
            result=subprocess.run(argv,input=json.dumps(request).encode(),stdout=output,stderr=subprocess.DEVNULL,timeout=15,check=False)
            output.seek(0); body=output.read(65537)
        if result.returncode or len(body)>65536:raise ValueError('Reviewer failed or returned excessive output')
        verdict=json.loads(body)
        if verdict.get('revision')!=a['revision']:raise ValueError('Reviewer did not bind verdict to the current revision')
        if verdict.get('decision')!='allow' or not set(request['required_checks']).issubset(set(verdict.get('checks',[]))):return {'state':'withheld','scope':'reviewer-incomplete-or-rejected'}
        return {'state':'reviewer-approved','scope':verdict.get('scope','original-media'),'evidence':str(verdict.get('evidence',''))[:600]}
    def accept(self,a):
        self.report['examined']+=1
        text=' '.join([a['title'],a['key'],a.get('description',''),*a.get('tags',[]),*[v.get('filename','') for v in a.get('files',[])]])
        if not acceptable(text) or review_terms(text) or a.get('provider_mature_flag'):
            self.report['blocked_metadata']+=1;return False
        keys=identities(a)
        if self.seen.intersection(keys):self.report['duplicates']+=1;return False
        evidence={'state':'metadata-screened','scope':'title,description,tags,filenames; no visual certification'}
        if self.mode=='strict' and not a.get('software_only') and a['kind'] not in {'font','asset-pack'}:
            duration=a.get('features',{}).get('declared_technical',{}).get('duration')
            if a['kind']=='audio' and isinstance(duration,(int,float)) and duration>90:return self.withhold('declared-duration-exceeds-browse-budget; use selected original review')
            try: reviewed=self.review_backend(a)
            except Exception: return self.withhold('local-reviewer-unavailable')
            if reviewed:
                if reviewed['state']=='withheld':return self.withhold(reviewed['scope'])
                evidence=reviewed
            else:
                # Built-in reviewers inspect selected originals locally. They
                # work without API keys or an external review service.
                from .live_media_review import review_original
                import time
                if hasattr(self.http,'started') and time.monotonic()-self.http.started>50:return self.withhold('request-review-budget-exhausted')
                builtin=None
                if a.get('files') and (a['kind'] in {'audio','video','animation-2d','animation-3d','model-3d','icon','vector-pack'} or 'svg' in a.get('formats',[])):
                    try:
                        classifier=None if a['kind']=='audio' else screener(str(model_path()))
                        builtin=review_original(self.http,a,classifier)
                    except Exception as e:return self.withhold(str(e)[:180] or 'original-media-review-unavailable')
                if builtin:
                    evidence=builtin
                    original_key='original-media:'+builtin['sha256']
                    if original_key in self.seen:self.report['duplicates']+=1;return False
                    keys.append(original_key)
                    structured=builtin.get('evidence',{}).get('structured_content_sha256')
                    if structured:
                        structured_key='structured-glb:'+structured
                        if structured_key in self.seen:self.report['duplicates']+=1;return False
                        keys.append(structured_key)
                # Speech, video frames, project files and geometry without a
                # preview require an actual reviewer; a cover image is insufficient.
                if not builtin and a['kind'] in {'audio','video','animation-2d','animation-3d','editing-template','volume-3d','vector-animation','mocap','pose-3d','groom-3d','procedural-3d','compositing-project'}:
                    return self.withhold('original-temporal-media-review-required')
                if builtin:
                    a['admission']={'safety':evidence,'quality':builtin['quality'],'dedup_scope':'Exact original bytes and current bundle identities; client cursor retains bounded digests only.'}
                    self.seen.update(keys);self.seen_order.extend(keys);self.report['admitted']+=1
                    return True
                previews=a.get('previews',[])
                raster=a['kind'] in {'illustration','image','texture','sprite','decal','atlas','terrain','brush','ui-asset'} and a.get('files') and set(a.get('formats',[]))&{'png','jpg','jpeg','webp'}
                if not previews and raster:previews=[{'url':a['files'][0]['url']}]
                if not previews:return self.withhold('no-screenable-preview')
                url=previews[0].get('url','')
                if raster:
                    url=a['files'][0]['url']
                if not url:return self.withhold('no-screenable-preview')
                try:
                    if raster and a['files'][0].get('archive_entry'):
                        from .content import ContentCache
                        with tempfile.TemporaryDirectory(prefix='infinite-creativity-member-screen-') as directory:
                            cache=ContentCache(directory,hosts=getattr(self.http,'hosts',()))
                            with cache.remote_zip(url) as archive:
                                selected=archive.getinfo(a['files'][0]['archive_entry'])
                                if selected.file_size>5*1024*1024 or selected.file_size>max(1,selected.compress_size)*500:raise ValueError('Original raster member exceeds review budget')
                                data=archive.read(selected)
                    elif raster:
                        from .live_media_review import original_bytes
                        data=original_bytes(self.http,a,a['files'][0],5*1024*1024)
                    else:data=self.http.read(url,5*1024*1024)
                    if data.lstrip().startswith((b'<svg',b'<?xml')):
                        if not acceptable(data.decode(errors='replace')) or review_terms(data.decode(errors='replace')):return self.withhold('vector-content-policy')
                        return self.withhold('vector-render-review-required')
                    with tempfile.TemporaryDirectory(prefix='infinite-creativity-admission-') as td:
                        path=Path(td)/'image.bin';path.write_bytes(data)
                        evidence=screener(str(model_path())).image(path)
                        if evidence['state']!='preview-screened':return self.withhold('image-sexual-or-suggestive-risk')
                        # Validate original visible pixels without rejecting small
                        # deliberate pixel art, simple icons, or low-poly styles.
                        if not evidence.get('decoder_isolation'):
                            from PIL import Image
                            with Image.open(io.BytesIO(data)) as image:image.verify()
                        if a['kind'] in {'illustration','image','texture','sprite','decal','atlas','terrain','brush','ui-asset'} and a.get('files') and url==a['files'][0]['url']:
                            pixel_key='original-raster:'+evidence['sha256']
                            if pixel_key in self.seen:self.report['duplicates']+=1;return False
                            keys.append(pixel_key);evidence['scope']='original-raster'
                            if evidence.get('decoded_pixel_sha256'):
                                decoded_key='decoded-pixels:'+evidence['decoded_pixel_sha256']
                                if decoded_key in self.seen:self.report['duplicates']+=1;return False
                                keys.append(decoded_key)
                except Exception as e:
                    if type(e).__name__ in {'UnidentifiedImageError','DecompressionBombError','DecompressionBombWarning'}:self.report['invalid_media']+=1
                    reason='classifier-unavailable' if isinstance(e,ImportError) or not (model_path()/'model.onnx').exists() else 'preview-invalid-or-unavailable'
                    return self.withhold(reason)
        a['admission']={'safety':evidence,'quality':{'state':'not-aesthetically-certified','policy':'Reject invalid media; preserve intentional minimal/pixel/low-poly styles.'},
                        'dedup_scope':'Exact current identities/original digests and bounded cursor receipts; not global visual similarity.'}
        self.seen.update(keys);self.seen_order.extend(keys);self.report['admitted']+=1
        return True
    def receipts(self):
        # Client-side navigation receipts are hashes only, never item metadata,
        # files, previews or licences. Their bounded scope is reported explicitly.
        return list(dict.fromkeys(self.seen_order))[-384:]
