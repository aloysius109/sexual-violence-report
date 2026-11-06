"""Check the sexual violence Pages snapshot against its reviewed file hashes."""
import hashlib
import json
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Unsafe publication path: {relative}")
    return path


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.refs=[]
    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ["src","href","data-profile-src"] and value:
                self.refs.append(value)


def check_links(root):
    broken=[]
    for page in root.rglob("*.html"):
        parser=Links(); parser.feed(page.read_text(encoding="utf-8"))
        for reference in parser.refs:
            url=urlsplit(reference)
            if url.hostname in ["localhost","127.0.0.1"]:
                broken.append((page.relative_to(root).as_posix(),reference));continue
            if url.scheme or url.netloc or not url.path:
                continue
            # Root-absolute project links are checked against the GitHub Pages project prefix.
            relative=unquote(url.path)
            if relative.startswith("/sexual-violence-report/"):
                target=root/relative.removeprefix("/sexual-violence-report/")
            elif relative.startswith("/"):
                continue
            else:
                target=page.parent/relative
            if not target.exists():
                broken.append((page.relative_to(root).as_posix(),reference))
    if broken:
        raise ValueError("Broken local publication links: "+repr(broken[:20]))



ROOT = Path(__file__).resolve().parent
SITE = ROOT / 'docs'
manifest = json.loads((SITE / 'publication.json').read_text(encoding='utf-8'))
actual = {p.relative_to(SITE).as_posix() for p in SITE.rglob('*') if p.is_file() and p.name != 'publication.json'}
if actual != set(manifest['files']):
    raise ValueError('Sexual violence publication file set differs from reviewed manifest')
for name, expected in manifest['files'].items():
    path = safe_path(SITE, name)
    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f'Reviewed publication file changed: {name}')
for name in ['index.html', 'worldwide.html', 'uk.html', 'children.html', 'justice.html', 'methods.html', 'medium/article.html']:
    if not (SITE / name).is_file():
        raise ValueError(f'Missing page: {name}')
check_links(SITE)
print(f'Verified {len(actual)} sexual violence publication files and local links.')
