"""Conservative metadata admission, not a visual moderation model."""
import re
import json
from importlib.resources import files
from urllib.parse import urlsplit

LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0", "CC-BY-4.0", "CC-BY-3.0", "OFL-1.1", "Unlicense", "0BSD", "Zlib"}
LICENSES.update({'CC-BY-1.0','CC-BY-2.0','CC-BY-2.5','CC-BY-SA-3.0','CC-BY-SA-4.0'})
EXCLUSIONS=json.loads(files("infinite_creativity").joinpath("data/exclusions.json").read_text(encoding="utf-8"))
BLOCKED_URLS=set(EXCLUSIONS["blocked_urls"])
BLOCKED_SOURCES=set(EXCLUSIONS["blocked_sources"])
DENIED = re.compile(r"(?i)(?:\b(?:nsfw|porn\w*|xxx|hentai|erotic\w*|nude|nudes|nudity|sex|sexual\w*|sexy|fetish\w*|penis|vagina|dildo|vibrator|genital\w*|orgasm\w*|breasts?|boobs?|fuck\w*|shit|bitch|middle[-_ ]finger)\b|إباح|اباح|جنسي|عاري)")
REVIEW = re.compile(r'(?i)\b(?:lewd|ecchi|ahegao|pinup|pin up|seductive|suggestive|boudoir|lingerie|striptease|undress|adult only)\b|إيحاء جنسي|اغراء|إغراء')

def review_terms(text):return bool(REVIEW.search(text.replace('_',' ').replace('-',' ')))
STYLE_RULES = {
    "minimal": ["minimal", "simple", "clean", "lucide", "feather"],
    "glassmorphism": ["glass", "frosted", "blur"],
    "neumorphism": ["neumorph", "soft-ui"],
    "brutalism": ["brutal", "raw", "bold"],
    "retro": ["retro", "vintage", "pixel", "8-bit", "arcade"],
    "organic": ["organic", "nature", "wood", "plant", "foliage"],
    "industrial": ["industrial", "metal", "concrete", "rust"],
    "cinematic": ["cinematic", "hdr", "sunset", "studio"],
    "outline": ["outline", "stroke", "line", "lucide", "feather", "tabler"],
    "solid": ["solid", "fill", "bold"],
    "playful": ["playful", "cartoon", "emoji", "colorful"],
    "luxury": ["luxury", "elegant", "marble", "gold"],
    "low-poly": ["low-poly", "lowpoly", "low poly"],
    "realistic": ["photogrammetry", "realistic", "pbr", "photo"],
    "motion": ["motion", "animated", "animation", "transition"],
    "dark": ["dark", "night", "black"],
    "geometric": ["geometric", "grid", "polygon"],
    "anime": ["anime", "manga", "cel-shad", "cel shad"],
    "cartoon": ["cartoon", "toon", "stylized character"],
    "ghibli": ["ghibli"],
    "fantasy": ["fantasy", "wizard", "mage", "medieval", "dungeon"],
    "sci-fi": ["sci-fi", "sci fi", "scifi", "spaceship", "cyberpunk"],
    "watercolor": ["watercolor", "watercolour"],
    "hand-drawn": ["hand-drawn", "hand drawn", "sketch", "ink drawing"],
    "isometric": ["isometric"],
}
ARABIC = {"بسيط":"minimal", "زجاجي":"glassmorphism", "قديم":"retro", "طبيعي":"organic", "صناعي":"industrial", "سينمائي":"cinematic", "واقعي":"realistic", "حركة":"motion", "داكن":"dark", "هندسي":"geometric", "أيقونة":"icon", "ايقونات":"icon", "خامة":"texture", "مجسم":"model-3d", "خط":"font", "زر":"button", "تنقل":"navigation", "قالب":"template"}

ARABIC.update({'انمي':'anime','أنمي':'anime','كرتوني':'cartoon','كرتون':'cartoon','فانتازيا':'fantasy','خيال':'fantasy','بيكسل':'retro','صوت':'audio','أصوات':'audio','اصوات':'audio','توضيحي':'illustration','ايزومتري':'isometric','بصري':'inspiration','مجسمات':'model-3d'})

def normalize_query(value):
    return " ".join(ARABIC.get(word, word) for word in value.lower().split())

def styles_for(text):
    text = text.lower()
    return [style for style, terms in STYLE_RULES.items() if any(term in text for term in terms)]

def acceptable(text):
    text=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',text)
    return not DENIED.search(text.replace("_", " ").replace("-", " "))

def public_https(url):
    p = urlsplit(url)
    return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password

def can_use(asset):
    return (not asset.get('duplicate_of') and asset.get('quality_state')!='rejected' and asset.get('safety_review') not in {'blocked','review-required'} and asset["source"] not in BLOCKED_SOURCES and asset["canonical_url"] not in BLOCKED_URLS and asset["mode"] == "usable" and (asset["license"] in LICENSES or (asset.get('end_product_only_verified') is True and asset['source'] in {'blendkit','blenderkit'} and asset['license']=='LicenseRef-Blendkit-RoyaltyFree'))
            and bool(asset.get("license_url")) and asset["safety"] == "metadata-screened"
            and asset["active"] == 1 and acceptable(asset["title"] + " " + " ".join(asset.get("tags", []))))
