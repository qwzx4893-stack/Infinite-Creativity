"""Verify a release snapshot against a separately downloaded manifest, then restore."""
import gzip
import hashlib
import json
import sys
from pathlib import Path

folder=Path(sys.argv[1] if len(sys.argv)>1 else "snapshots")
manifest=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
name="catalog.sqlite.gz"
compressed=(folder/name).read_bytes()
if hashlib.sha256(compressed).hexdigest() != manifest["files"][name]["sha256"]:
    raise SystemExit("Snapshot checksum mismatch")
target=Path("state/catalog.sqlite")
target.parent.mkdir(parents=True,exist_ok=True)
tmp=target.with_suffix(".restore")
with gzip.open(folder/name,"rb") as src, tmp.open("wb") as dst:
    import shutil
    shutil.copyfileobj(src,dst)
tmp.replace(target)
print("Snapshot verified and restored")
