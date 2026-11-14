"""Stage or validate the exact reviewed Quarto site for manual Pages publication."""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "_site"
DEST = ROOT / "docs"
REVIEW_MANIFEST = ROOT / "review-manifest.json"
PUBLICATION_MANIFEST = "publication.json"
REQUIRED = [
    "index.html",
    "worldwide.html",
    "uk.html",
    "children.html",
    "justice.html",
    "methods.html",
    "medium/article.html",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Unsafe publication path: {relative}")
    return path


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ["src", "href", "data-profile-src"] and value:
                self.refs.append(value)


def check_links(root):
    broken = []
    for page in root.rglob("*.html"):
        parser = Links()
        parser.feed(page.read_text(encoding="utf-8"))
        for reference in parser.refs:
            url = urlsplit(reference)
            if url.hostname in ["localhost", "127.0.0.1"]:
                broken.append((page.relative_to(root).as_posix(), reference))
                continue
            if url.scheme or url.netloc or not url.path:
                continue
            relative = unquote(url.path)
            if relative.startswith("/sexual-violence-report/"):
                target = root / relative.removeprefix("/sexual-violence-report/")
            elif relative.startswith("/"):
                continue
            else:
                target = page.parent / relative
            if not target.exists():
                broken.append((page.relative_to(root).as_posix(), reference))
    if broken:
        raise ValueError("Broken local publication links: " + repr(broken[:20]))


def load_reviewed_files():
    if not REVIEW_MANIFEST.is_file():
        raise ValueError("review-manifest.json is missing; validate the report first")
    manifest = json.loads(REVIEW_MANIFEST.read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("review-manifest.json has no valid files mapping")
    return manifest, files


def source_files():
    if not SOURCE.is_dir():
        raise ValueError("Render and review the Quarto report first")
    entries = list(SOURCE.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("Publication cannot include symbolic links")
    files = [path for path in entries if path.is_file()]
    for name in REQUIRED:
        if not (SOURCE / name).is_file():
            raise ValueError(f"Render the whole report first: missing {name}")
    return files


def verify_source():
    files = source_files()
    _, reviewed = load_reviewed_files()
    current = {path.relative_to(SOURCE).as_posix(): digest(path) for path in files}
    if current != reviewed:
        missing = sorted(set(reviewed) - set(current))
        extra = sorted(set(current) - set(reviewed))
        changed = sorted(name for name in set(current) & set(reviewed) if current[name] != reviewed[name])
        raise ValueError(
            "_site does not match review-manifest.json; "
            f"missing={missing[:5]}, extra={extra[:5]}, changed={changed[:5]}"
        )
    check_links(SOURCE)
    return files, current


def validate():
    _, current = verify_source()
    for name in REQUIRED:
        if not (DEST / name).is_file():
            raise ValueError(f"Required published page missing: {name}")
    manifest_path = DEST / PUBLICATION_MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        path.relative_to(DEST).as_posix()
        for path in DEST.rglob("*")
        if path.is_file() and path.name != PUBLICATION_MANIFEST
    }
    if actual != set(manifest["files"]):
        raise ValueError("Publication files do not match docs/publication.json")
    if actual != set(current):
        raise ValueError("docs/ does not contain the exact reviewed _site file set")
    review_manifest, _ = load_reviewed_files()
    if manifest.get("review_edition") != review_manifest.get("review_edition"):
        raise ValueError("Publication edition differs from review-manifest.json")
    for relative, expected in manifest["files"].items():
        path = safe_path(DEST, relative)
        if path.is_symlink() or digest(path) != expected or expected != current[relative]:
            raise ValueError(f"Reviewed file changed or differs from _site: {relative}")
    check_links(DEST)
    print(f"Verified {len(actual)} reviewed publication files, matching _site and local HTML links.")


def stage():
    files, current = verify_source()
    review_manifest, _ = load_reviewed_files()
    previous_path = DEST / PUBLICATION_MANIFEST
    previous = json.loads(previous_path.read_text(encoding="utf-8"))["files"] if previous_path.is_file() else {}

    DEST.mkdir(parents=True, exist_ok=True)
    for source in files:
        relative = source.relative_to(SOURCE)
        target = safe_path(DEST, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    for relative in set(previous) - set(current):
        path = safe_path(DEST, relative)
        if path.is_file() or path.is_symlink():
            path.unlink()

    manifest = {
        "review_edition": review_manifest["review_edition"],
        "staged_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": current,
    }
    (DEST / PUBLICATION_MANIFEST).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate the staged publication without rebuilding it")
    args = parser.parse_args()
    validate() if args.check else stage()