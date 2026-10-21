"""Small native Cairo smoke check; no network or saved original files."""
import cairosvg

source=b'<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8"/></svg>'
result=cairosvg.svg2png(bytestring=source)
if not result.startswith(b'\x89PNG'):
    raise RuntimeError('Cairo did not return a PNG')
print('Native SVG renderer ready')
