"""Exclusive primary sections and real packs; artistic style remains an independent facet."""
import hashlib
import json
import re
from urllib.parse import quote

LEAVES={
 'interface/components/controls':('Controls','أدوات التحكم'),
 'interface/components/navigation':('Navigation','التنقل'),
 'interface/components/forms':('Forms','النماذج'),
 'interface/components/data-display':('Data display','عرض البيانات'),
 'interface/components/feedback':('Feedback','التنبيهات والحالات'),
 'interface/components/layout':('Layouts','التخطيطات'),
 'interface/components/other':('Other components','عناصر واجهة أخرى'),
 'interface/visual-kits':('Visual UI kits','حزم الواجهات البصرية'),
 'interface/icons':('Icons','الأيقونات'),
 'interface/templates':('Web and app templates','قوالب المواقع والتطبيقات'),
 'motion/interface':('Interface motion','حركة الواجهات'),
 'motion/graphics':('Motion graphics','الموشن جرافيكس'),
 'motion/vector-animation':('Vector animation','التحريك المتجهي'),
 'motion/particles':('Particles and effects','الجزيئات والمؤثرات'),
 'motion/shaders':('Shaders','المظللات'),
 'editing/transitions':('Video transitions','انتقالات المونتاج'),
 'editing/color-luts':('Color LUTs','معالجة الألوان'),
 'editing/project-templates':('Editing projects','مشاريع المونتاج'),
 'editing/footage':('Footage','لقطات الفيديو'),
 'editing/overlays':('Overlays','طبقات المونتاج'),
 'three-d/characters/humanoid':('Humanoid characters','شخصيات بشرية'),
 'three-d/characters/creatures':('Animals and creatures','الحيوانات والمخلوقات'),
 'three-d/characters/robots':('Robots and machines','الروبوتات والآلات'),
 'three-d/environments/nature':('Nature environments','البيئات الطبيعية'),
 'three-d/environments/architecture':('Architecture','العمارة والمباني'),
 'three-d/props/vehicles':('Vehicles','المركبات'),
 'three-d/props/furniture':('Furniture','الأثاث'),
 'three-d/props/equipment':('Equipment','المعدات'),
 'three-d/props/other':('Other props','مجسمات أخرى'),
 'three-d/animation/rigs':('Rigs','هياكل التحريك'),
 'three-d/animation/clips':('Animation clips','مقاطع التحريك'),
 'three-d/scenes':('Complete scenes','المشاهد الكاملة'),
 'three-d/volumes':('Volumes and simulation','الحجوم والمحاكاة'),
 'two-d/characters':('2D characters','شخصيات ثنائية الأبعاد'),
 'two-d/tilesets':('Tilesets','خرائط البلاطات'),
 'two-d/backgrounds':('Backgrounds','الخلفيات'),
 'two-d/effects':('2D effects','المؤثرات ثنائية الأبعاد'),
 'two-d/sprites':('Other sprites','رسومات الألعاب'),
 'two-d/illustrations':('Illustrations','الرسوم التوضيحية'),
 'two-d/animation':('2D animation projects','مشاريع التحريك ثنائي الأبعاد'),
 'surfaces/materials':('PBR materials','مواد PBR'),
 'surfaces/textures':('Textures','الخامات'),
 'surfaces/decals':('Decals','الملصقات'),
 'surfaces/atlases':('Texture atlases','أطالس الخامات'),
 'surfaces/terrain':('Terrain','التضاريس'),
 'surfaces/brushes':('Brushes','الفُرَش'),
 'lighting/hdri':('HDRI lighting','إضاءة HDRI'),
 'audio/effects/environment':('Environmental sounds','أصوات البيئة'),
 'audio/effects/foley':('Foley','المؤثرات الحركية'),
 'audio/effects/interface':('UI sounds','أصوات الواجهات'),
 'audio/effects/other':('Sound effects','المؤثرات الصوتية'),
 'audio/music':('Music','الموسيقى'),
 'audio/voice':('Voice','الصوت البشري'),
 'typography/fonts':('Fonts','الخطوط'),
 'inspiration/animation':('Animation inspiration','تنمية بصرية: الأنيميشن'),
 'inspiration/interface':('Interface inspiration','تنمية بصرية: الواجهات'),
 'inspiration/three-d':('3D inspiration','تنمية بصرية: ثلاثي الأبعاد'),
 'inspiration/motion':('Motion inspiration','تنمية بصرية: الحركة'),
 'inspiration/illustration':('Illustration inspiration','تنمية بصرية: الرسوم'),
 'discovery/repositories':('Unreviewed repositories','مستودعات تحتاج مراجعة'),
 'discovery/providers':('Provider discovery','اكتشاف المصادر'),
 'other/assets':('Other assets','أصول أخرى'),
}
ROOTS={'interface':('Interfaces','الواجهات'),'motion':('Motion','الحركة'),'editing':('Video editing','المونتاج'),'three-d':('3D','ثلاثي الأبعاد'),'two-d':('2D','ثنائي الأبعاد'),'surfaces':('Materials and textures','المواد والخامات'),'lighting':('Lighting','الإضاءة'),'audio':('Audio','الصوت'),'typography':('Typography','الخطوط'),'inspiration':('Visual inspiration','التنمية البصرية'),'discovery':('Discovery','الاكتشاف'),'other':('Other','أخرى')}
LEAVES['discovery/collections']=('Curated collection folders','مجموعات الأصول المنتقاة')
LEAVES.update({
 'interface/mockups':('Mockups','نماذج العرض'),
 'motion/compositions':('Motion compositions','تركيبات الحركة'),
 'editing/titles':('Video titles and captions','عناوين الفيديو والترجمات'),
 'editing/compositing':('Compositing and VFX','التركيب البصري والمؤثرات'),
 'three-d/characters/hair':('Hair and grooming','الشعر وتجهيزه'),
 'three-d/environments/interiors':('Interior environments','البيئات الداخلية'),
 'three-d/environments/urban':('Urban environments','البيئات الحضرية'),
 'three-d/props/wearables':('Clothing and accessories','الملابس والإكسسوارات'),
 'three-d/props/food':('Food and beverages','الأطعمة والمشروبات'),
 'three-d/props/instruments':('Musical instruments','الآلات الموسيقية'),
 'three-d/props/technology':('Technology props','المجسمات التقنية'),
 'three-d/animation/mocap':('Motion capture','التقاط الحركة'),
 'three-d/animation/poses':('Pose libraries','مكتبات الوضعيات'),
 'three-d/procedural':('Procedural geometry','الهندسة الإجرائية'),
 'lighting/profiles':('Photometric light profiles','ملفات الإضاءة الضوئية'),
 'audio/music/loops':('Music loops','الحلقات الموسيقية'),
 'audio/music/stems':('Music stems','المسارات الموسيقية المنفصلة'),
 'audio/music/tracks':('Music tracks','المقطوعات الموسيقية'),
 'two-d/vector-packs':('Vector illustration packs','حزم الرسوم المتجهية'),
})
LEAVES.pop('audio/music',None)

def initialize(c):
    c.db.executescript('''CREATE TABLE IF NOT EXISTS asset_sections(asset_id TEXT PRIMARY KEY,section_id TEXT NOT NULL,pack_id TEXT NOT NULL,reason TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS section_seek ON asset_sections(section_id,asset_id);
    CREATE INDEX IF NOT EXISTS pack_seek ON asset_sections(pack_id,asset_id);
    CREATE TABLE IF NOT EXISTS packs(id TEXT PRIMARY KEY,source_id TEXT,name TEXT,kind TEXT,data TEXT);
    CREATE TABLE IF NOT EXISTS curation(asset_id TEXT PRIMARY KEY,revision TEXT NOT NULL,quality_state TEXT NOT NULL,safety_state TEXT NOT NULL,duplicate_of TEXT NOT NULL,data TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS curation_duplicate ON curation(duplicate_of,asset_id);
    CREATE TABLE IF NOT EXISTS containers(id TEXT PRIMARY KEY,data TEXT NOT NULL);''')

def classify(a):
    kind=a['kind']; text=(a['title']+' '+' '.join(a['tags'])+' '+a['upstream_id']).lower()
    if kind=='visual-reference':
        role=a.get('reference_category','')
        return 'inspiration/'+(role if role in {'animation','interface','three-d','motion','illustration'} else 'illustration'),'reference purpose, never an original download'
    if kind=='collection-folder':return 'discovery/collections','Collection navigation only; members have their own rights and primary sections'
    direct={'ui-asset':'interface/visual-kits','icon':'interface/icons','font':'typography/fonts','motion':'motion/interface','model-3d':'three-d/props/other','scene-3d':'three-d/scenes','animation-3d':'three-d/animation/clips','volume-3d':'three-d/volumes','sprite':'two-d/sprites','illustration':'two-d/illustrations','image':'two-d/illustrations','animation-2d':'two-d/animation','material':'surfaces/materials','texture':'surfaces/textures','decal':'surfaces/decals','atlas':'surfaces/atlases','terrain':'surfaces/terrain','brush':'surfaces/brushes','hdri':'lighting/hdri','lut':'editing/color-luts','video':'editing/footage','video-transition':'editing/transitions','video-overlay':'editing/overlays','editing-template':'editing/project-templates','motion-graphic':'motion/graphics','vector-animation':'motion/vector-animation','particle':'motion/particles','shader':'motion/shaders','repository':'discovery/repositories','source-reference':'discovery/providers','template':'interface/templates'}
    section=direct.get(kind,'other/assets')
    direct.update({'mockup':'interface/mockups','motion-composition':'motion/compositions','video-title':'editing/titles','compositing-project':'editing/compositing','groom-3d':'three-d/characters/hair','mocap':'three-d/animation/mocap','pose-3d':'three-d/animation/poses','procedural-3d':'three-d/procedural','light-profile':'lighting/profiles','vector-pack':'two-d/vector-packs'})
    section=direct.get(kind,section)
    if kind=='volume-3d':section='three-d/volumes'
    def has(words): return bool(re.search(r'\b(?:'+words+r')\b',text.replace('_',' ').replace('-',' ')))
    if kind=='ui-component':
        section='interface/components/other'
        for slug,words in [('navigation','nav|menu|breadcrumb|pagination|tabs?|sidebar|stepper|command'),('forms','form|input|textarea|select|combobox|datepicker|validation|upload'),('feedback','toast|alert|dialog|modal|progress|skeleton|spinner|tooltip|notification'),('data-display','table|chart|avatar|badge|calendar|tree|list|grid'),('layout','container|layout|flex|stack|divider|separator|panel|card'),('controls','button|checkbox|radio|switch|slider|toggle')]:
            if has(words): section='interface/components/'+slug;break
    if kind=='model-3d':
        for path,words in [('characters/robots','robot|mech|android'),('characters/creatures','animal|creature|monster|dragon|dinosaur|cat|dog|fish|bird|bunny|skeleton|zombie'),('characters/humanoid','character|humanoid|hero|mage|knight|human|woman|man|npc|boy|girl'),('characters/hair','hair|groom|hairstyle'),('environments/interiors','interior|room|kitchen|bathroom'),('environments/urban','city|urban|street|downtown'),('environments/architecture','building|architecture|house|castle|tower|wall|roof|road|bridge'),('environments/nature','tree|plant|grass|rock|flower|bush|terrain'),('props/vehicles','vehicle|car|truck|ship|boat|aircraft|plane|spaceship|train'),('props/furniture','furniture|chair|table|sofa|couch|bed|shelf|cabinet'),('props/wearables','clothing|garment|jacket|dress|trousers|shoes|boots|hat'),('props/food','food|fruit|bread|meal|drink|vegetable|banana|apple'),('props/instruments','guitar|piano|violin|saxophone|musical instrument'),('props/technology','computer|laptop|phone|electronics|monitor|television'),('props/equipment','weapon|sword|axe|shield|helmet|tool|equipment')]:
            if has(words):section='three-d/'+path;break
    if kind=='sprite':
        for slug,words in [('effects','effect|particle|explosion|smoke|fire|vfx'),('characters','character|creature|monster|hero|enemy|npc|animal'),('tilesets','tileset|tilemap|terrain|tiles'),('backgrounds','background|skybox|backdrop|parallax')]:
            if has(words):section='two-d/'+slug;break
    if kind=='audio':
        section='audio/effects/other'
        for path,words in [('voice','speech|voice|dialogue|vocal'),('music','music|jingle|soundtrack|song|melody'),('effects/interface','interface|button|click|notification|ui|bleep'),('effects/environment','ambience|ambient|environment|rain|wind|forest|river|water|thunder'),('effects/foley','foley|footstep|door|cloth|impact|hit|movement')]:
            if has(words):section='audio/'+path;break
        if section=='audio/music' and has('loop|loops'):section='audio/music/loops'
        elif section=='audio/music' and has('stem|stems|multitrack'):section='audio/music/stems'
        elif section=='audio/music':section='audio/music/tracks'
    return section,'kind + ordered semantic roles; exactly one primary leaf, styles are independent facets'

def pack_id(source,scope=''):return hashlib.sha256((source+'|'+scope).encode()).hexdigest()[:24]

def organize(c,sources=None):
    initialize(c); batch=[]; known=set();count=0
    source_info={row['id']:json.loads(row['data']) for row in c.db.execute('SELECT * FROM sources')}
    ids=list(dict.fromkeys(sources or []))
    where=' AND a.source IN ('+','.join('?' for _ in ids)+')' if ids else ''
    for row in c.db.execute('SELECT a.*,d.data AS details_json FROM assets a LEFT JOIN asset_details d ON d.asset_id=a.id WHERE active=1'+where,ids):
        a=dict(row);a['tags']=json.loads(a['tags']);d=json.loads(a.pop('details_json') or '{}')
        a['reference_category']=d.get('reference_category','')
        section,reason=classify(a)
        scope=d.get('pack_scope') or d.get('features',{}).get('pack_root','')
        pid=d.get('pack_id') or pack_id(a['source'],scope)
        if pid not in known:
            s=source_info.get(a['source'],{});name=d.get('pack_name') or d.get('features',{}).get('pack') or s.get('name',a['source'])
            data={'theme':d.get('theme',[]),'styles':json.loads(a['styles']),'license':a['license'],'license_url':a['license_url'],'author':a['author'],'resource_uri':'creativity://pack/'+pid}
            kind='pack' if scope or a['source'].startswith(('kenney-pack:','quaternius:','fsd50k:')) or s.get('adapter') in {'github-assets','blender-demos'} else 'collection'
            c.db.execute('INSERT OR REPLACE INTO packs VALUES (?,?,?,?,?)',(pid,a['source'],str(name)[:300],kind,json.dumps(data,ensure_ascii=False)));known.add(pid)
        batch.append((a['id'],section,pid,reason));count+=1
        if len(batch)>=1000:c.db.executemany('INSERT OR REPLACE INTO asset_sections VALUES (?,?,?,?)',batch);batch=[]
    if batch:c.db.executemany('INSERT OR REPLACE INTO asset_sections VALUES (?,?,?,?)',batch)
    c.db.commit();return count

def sections(c,parent='',include_empty=False,mode='usable'):
    if mode not in {'usable','reference','all'}:raise ValueError('Invalid mode')
    if parent and parent not in LEAVES and not any(x.startswith(parent+'/') for x in LEAVES):raise ValueError('Unknown section; use section IDs returned by library_sections')
    counts=dict(c.db.execute("SELECT s.section_id,count(*) FROM asset_sections s JOIN assets a ON a.id=s.asset_id LEFT JOIN curation r ON r.asset_id=a.id WHERE a.active=1 AND (?='all' OR a.mode=?) AND coalesce(r.duplicate_of,'')='' AND coalesce(r.safety_state,'') NOT IN ('blocked','review-required') AND coalesce(r.quality_state,'')!='rejected' GROUP BY s.section_id",(mode,mode)))
    ids=sorted({x.split('/')[0] if not parent else parent+'/'+x[len(parent)+1:].split('/')[0] for x in LEAVES if not parent or x.startswith(parent+'/')})
    result=[]
    for sid in ids:
        count=sum(v for k,v in counts.items() if k==sid or k.startswith(sid+'/'))
        if not count and not include_empty:continue
        title,arabic=LEAVES.get(sid,ROOTS.get(sid,(sid.rsplit('/',1)[-1].replace('-',' ').title(),sid.rsplit('/',1)[-1])))
        result.append({'id':sid,'title':title,'title_ar':arabic,'records':count,'leaf':sid in LEAVES,'resource_uri':'creativity://section/'+quote(sid,safe=''),'next_action':'open_library' if sid in LEAVES else 'library_sections','filters':{'section':sid,'mode':mode}})
    return {'parent':parent,'sections':result,'primary_placement':'Each item belongs to one primary leaf. Parent counts are rollups, not extra copies. Artistic direction, software, license and pack are separate filters.'}

def packs(c,after_id='',query='',section='',style='',mode='usable',limit=30):
    from .catalog import VISIBLE
    from .policy import normalize_query
    if not 1<=limit<=100 or mode not in {'usable','reference','all'}:raise ValueError('Invalid pack page')
    if section and section not in LEAVES and not any(x.startswith(section+'/') for x in LEAVES):raise ValueError('Unknown section ID')
    where=['p.kind=\'pack\'','p.id>?','a.active=1',VISIBLE];args=[after_id]
    if query:where.append('(p.name LIKE ? ESCAPE \'\\\' OR p.source_id LIKE ? ESCAPE \'\\\')');q='%'+normalize_query(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%';args.extend([q,q])
    if mode!='all':where.append('a.mode=?');args.append(mode)
    if section:where.append('(s.section_id=? OR s.section_id LIKE ?)');args.extend([section,section+'/%'])
    if style:where.append('EXISTS(SELECT 1 FROM json_each(a.styles) WHERE value=?)');args.append(normalize_query(style))
    rows=c.db.execute('SELECT p.*,count(*) records FROM packs p JOIN asset_sections s ON s.pack_id=p.id JOIN assets a ON a.id=s.asset_id LEFT JOIN curation r ON r.asset_id=a.id WHERE '+' AND '.join(where)+' GROUP BY p.id ORDER BY p.id LIMIT ?',args+[limit+1]).fetchall()
    items=[{'id':r['id'],'name':r['name'],'source_id':r['source_id'],'records':r['records'],'metadata':json.loads(r['data']),'filters':{'pack':r['id'],'mode':mode,'section':section,'style':style},'actions':['get_library_pack','open_library']} for r in rows[:limit]]
    return {'items':items,'next_cursor':items[-1]['id'] if len(rows)>limit else None,'scope':'Actual thematic packs with indexed members. Provider directories and unreviewed repositories are excluded.'}
