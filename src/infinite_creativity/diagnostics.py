"""Local readiness evidence. Never downloads software or probes all providers."""
import hashlib
import importlib.metadata
import importlib.util
import sys
from pathlib import Path


def model_status(path,expected,verify=False):
    missing=[];mismatched=[];present=0
    for name,definition in expected.items():
        digest=definition['sha256'] if isinstance(definition,dict) else definition[1] if isinstance(definition,(tuple,list)) else definition
        target=Path(path)/name
        if not target.is_file():missing.append(name);continue
        present+=1
        if verify:
            with target.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=digest:mismatched.append(name)
    return {'state':'missing' if missing else 'invalid' if mismatched else 'verified' if verify else 'present-not-hash-verified',
            'present_files':present,'missing_files':missing,'mismatched_files':mismatched}


def readiness(verify_models=False):
    from .vision import MODEL
    from .live_admission import model_path
    from .live_media_review import SPEECH_MODEL,speech_path
    from .live_visual_rank import MODEL as STYLE,model_path as style_path
    from .specialized_media import blender_path
    from .request_scope import runtime_status
    packages={}
    for name in ['mcp','Pillow','httpx','onnxruntime','av','faster-whisper','trimesh','tree-sitter','tree-sitter-typescript']:
        try:packages[name]={'version':importlib.metadata.version(name)}
        except importlib.metadata.PackageNotFoundError:packages[name]={'state':'not-installed'}
    try:blender={'state':'installed-not-runtime-probed' if blender_path() else 'not-installed'}
    except ValueError:blender={'state':'invalid-configured-executable'}
    return {'python':sys.version.split()[0],'packages':packages,
            'models':{'vision':model_status(model_path(),MODEL['files'],verify_models),
                      'speech':model_status(speech_path(),SPEECH_MODEL['files'],verify_models),
                      'style':model_status(style_path(),STYLE['files'],verify_models)},
            'native_blender':blender,
            'runtime':runtime_status(),'provider_health':'Not inferred from local readiness. Use probe_library_sources for bounded live evidence.',
            'next_actions':['Install .[media,quality] for local readers and source parsing',
                            'prepare-live-vision / prepare-live-media / prepare-live-style for missing pinned software',
                            'Use original-author public registries for account-free UI/motion delivery'],
            'storage':'No original assets downloaded or retained by this diagnostic.'}
