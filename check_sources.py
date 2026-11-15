"""Watch the archived sources for change, link rot and recovered downloads.

The watcher reads `sources/manifest.json`, which already records every source
this edition was built from, and compares it with what those addresses serve
today. It never downloads report data into the repository, never edits the
report and never republishes.

Data files (CSV, JSON, spreadsheets) are compared by SHA-256, because a changed
byte there is a changed figure. Web pages are only checked for availability:
their markup churns for reasons that have nothing to do with the statistics, so
hashing them would raise a weekly false alarm. Sources that already failed when
the edition was archived are re-checked, so a download that becomes available
again is reported rather than forgotten.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "sources" / "manifest.json"
USER_AGENT = "aloysius109-source-watch/1.0 (+https://github.com/aloysius109/sexual-violence-report)"
TIMEOUT = 120
DATA_SUFFIXES = {".csv", ".json", ".xlsx", ".xls", ".ods", ".zip"}
HOST_DELAY = 2.0
RATE_LIMIT_PAUSE = 20.0


def read(url, last_call):
    """Fetch a URL, pacing requests to one host. HTTP error statuses are returned."""
    host = urllib.parse.urlparse(url).netloc
    waited = time.monotonic() - last_call.get(host, 0.0)
    if waited < HOST_DELAY:
        time.sleep(HOST_DELAY - waited)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, body = error.code, b""
    last_call[host] = time.monotonic()
    return status, body


def fetch(url, last_call):
    """Fetch once, then retry a rate-limited address after a pause."""
    status, body = read(url, last_call)
    if status == 429:
        time.sleep(RATE_LIMIT_PAUSE)
        status, body = read(url, last_call)
    return status, body


def classify(source):
    if not source.get("file"):
        return "recheck"
    return "data" if Path(source["file"]).suffix.lower() in DATA_SUFFIXES else "page"


def inspect(source, last_call):
    kind = classify(source)
    result = {"id": source["id"], "label": source["id"], "url": source["url"], "kind": kind}
    try:
        status, body = fetch(source["url"], last_call)
    except Exception as error:  # DNS, TLS, timeout, connection reset
        return {**result, "state": "unreachable", "detail": f"Could not be fetched: {error}"}
    if status == 429:
        return {**result, "state": "skipped", "detail": "Rate-limited by the host; not checked this run."}
    if kind == "recheck":
        if status == 200:
            return {**result, "state": "changed",
                    "detail": (f"Now downloads (HTTP 200, {len(body):,} bytes). It failed when this edition was "
                               f"archived: {source.get('error', 'no copy was saved')}")}
        return {**result, "state": "unchanged",
                "detail": f"Still unavailable (HTTP {status}), as recorded when the edition was archived."}
    if kind == "page":
        # Any 2xx counts as reachable: some sites answer an automated request with 202 rather than 200.
        if 200 <= status < 300:
            return {**result, "state": "unchanged", "detail": f"Reachable (HTTP {status}, {len(body):,} bytes)."}
        return {**result, "state": "unreachable",
                "detail": f"HTTP {status}: the archived page is no longer served at this address."}
    if status != 200:
        return {**result, "state": "unreachable",
                "detail": f"HTTP {status}: the archived source is no longer served at this address."}
    found = hashlib.sha256(body).hexdigest()
    if found == source.get("sha256"):
        return {**result, "state": "unchanged", "detail": f"{len(body):,} bytes, sha256 unchanged."}
    return {**result, "state": "changed",
            "detail": (f"Data changed: now sha256 `{found}` ({len(body):,} bytes), recorded "
                       f"`{source.get('sha256')}` ({source.get('bytes', 0):,} bytes).")}


def fingerprint(drift):
    """A stable identifier for which sources are in which state, ignoring sizes and dates."""
    state = ";".join(sorted(f"{result['id']}:{result['state']}" for result in drift))
    return hashlib.sha256(state.encode("utf-8")).hexdigest()[:12]


def report_markdown(results, retrieved):
    stamp = datetime.now(timezone.utc).strftime("%d %B %Y")
    changed = [result for result in results if result["state"] == "changed"]
    unreachable = [result for result in results if result["state"] == "unreachable"]
    skipped = [result for result in results if result["state"] == "skipped"]
    unchanged = [result for result in results if result["state"] == "unchanged"]
    data = [result for result in results if result["kind"] == "data"]
    lines = [f"## Sexual violence report — source watch — {stamp}", "",
             f"{len(unchanged)} of {len(results)} archived sources unchanged since the {retrieved} edition "
             f"({len(data)} of them compared byte for byte; web pages are checked for availability only).", ""]
    for heading, group in (("Changed upstream", changed),
                           ("No longer available", unreachable),
                           ("Not checked this run", skipped)):
        if group:
            lines.append(f"### {heading}")
            for result in group:
                lines.append(f"- **{result['id']}** — {result['detail']}")
                lines.append(f"  <{result['url']}>")
            lines.append("")
    if unchanged:
        lines.append("<details><summary>Unchanged</summary>")
        lines.append("")
        lines += [f"- {result['id']} — {result['detail']}" for result in unchanged]
        lines += ["", "</details>", ""]
    if changed or unreachable:
        lines += ["### What this means", "",
                  "The report has not been changed. A changed data file means a figure quoted in the prose may now",
                  "disagree with its source, and `check_report.py` pins those figures deliberately, so adopting a",
                  "revision is an editorial decision. A source that has gone means the citation needs a replacement",
                  "or an archived link. Re-archive with `python build_report.py` when a change is adopted, which",
                  "rewrites `sources/manifest.json` and the recorded hashes.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 when a source has changed or gone")
    parser.add_argument("--report", type=Path, help="Also write the Markdown report to this file")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    last_call = {}
    results = [inspect(source, last_call) for source in manifest["sources"]]
    drift = [result for result in results if result["state"] in {"changed", "unreachable"}]
    report = report_markdown(results, manifest.get("retrieved_date", "archived"))
    if drift:
        report += f"\n<!-- source-watch:{fingerprint(drift)} -->\n"
    print(report)

    if args.report:
        args.report.write_text(report + "\n", encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"drift={'true' if drift else 'false'}\n")

    if drift and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
