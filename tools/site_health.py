#!/usr/bin/env python3
"""M&M Auto Center - site health check.

Checks the LIVE site (GitHub Pages) and the repository contents:

  1. every published page answers HTTP 200 with an HTML body
  2. every page still carries its social/SEO tags (viewport, canonical, og:*)
  3. every link and image referenced by those pages still resolves
     (internal targets are hard failures, external targets are warnings)
  4. retired pages stay retired (index-v2.html / index-v3.html are 404)
  5. no credential-looking string is present in the repository

Exit code 0 = healthy, 1 = at least one hard failure.
Optional env: SITE_BASE (default the live Pages URL), LOCAL_DIR (repo root).
"""

from __future__ import annotations

import concurrent.futures
import base64
import html.parser
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("SITE_BASE", "https://mamo390.github.io/mm-auto-center-website/").rstrip("/") + "/"
LOCAL_DIR = pathlib.Path(os.environ.get("LOCAL_DIR", pathlib.Path(__file__).resolve().parent.parent))
RETIRED = ["index-v2.html", "index-v3.html"]
REQUIRED_META = ["viewport", "canonical", "og:title", "og:description", "og:url"]
UA = "MMAutoCenter-site-health/1.0 (+https://github.com/mamo390/mm-auto-center-website)"
TIMEOUT = 25

failures: list[str] = []
warnings: list[str] = []


class PageParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.meta: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag in ("img", "script", "source") and a.get("src"):
            self.links.append(a["src"])
        elif tag == "link" and "icon" in a.get("rel", "").lower() and a.get("href", "").startswith("data:"):
            pass
        elif tag == "meta":
            key = a.get("property") or a.get("name") or ""
            key = key.lower()
            if key == "viewport":
                self.meta.add("viewport")
            elif key in ("og:title", "og:description", "og:url"):
                self.meta.add(key)

    # <link rel="canonical">
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)


def fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # DNS, TLS, timeout
        return 0, f"__ERROR__{type(e).__name__}: {e}"


def check_page(path: str) -> str | None:
    url = BASE + path
    status, body = fetch(url)
    if status != 200:
        failures.append(f"page {path} -> HTTP {status or body[:120]}")
        return None
    if "__ERROR__" in body[:40]:
        return None
    if "<html" not in body.lower():
        failures.append(f"page {path} -> served no HTML body")
        return None
    p = PageParser()
    p.feed(body)
    hrefs = [l for l in p.links if l.lower().startswith(("http", "/", "./", "../")) or l.lower().endswith(".html")]
    canon = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)', body, re.I)
    if canon:
        p.meta.add("canonical")
    missing = [m for m in REQUIRED_META if m not in p.meta]
    if missing:
        failures.append(f"page {path} -> missing meta: {', '.join(missing)}")
    if canon and (canon.group(1).rstrip("/") + "/").replace("index.html", "") != url.rstrip("/") + "/":
        warnings.append(f"page {path} -> canonical points elsewhere: {canon.group(1)}")
    return "\n".join(hrefs)


def check_target(src_page: str, link: str) -> None:
    if link.startswith(("mailto:", "tel:", "javascript:", "#", "data:")):
        return
    link = link.split("#", 1)[0].strip()
    if not link:
        return
    if link.startswith("/"):
        url = BASE.rstrip("/") + link
    elif link.startswith(("http://", "https://")):
        url = link
    else:
        url = BASE + link.lstrip("./")
    internal = url.startswith(BASE) or "mamo390.github.io" in url
    status, _ = fetch(url)
    if status and status < 400:
        return
    msg = f"{'page' if internal else 'external item'} {link} (from {src_page}) -> HTTP {status or 'unreachable'}"
    (failures if internal else warnings).append(msg)


def check_retired() -> None:
    for name in RETIRED:
        status, _ = fetch(BASE + name)
        if status == 200:
            failures.append(f"retired page {name} is still published (HTTP 200)")


SECRET_PATTERNS = [
    ("plain id:secret credential", re.compile(r"\b[A-Za-z0-9]{16,}:[A-Za-z0-9+/=_-]{32,}\b")),
    ("key/token assignment", re.compile(r"(?i)(api[_-]?key|auth[_-]?token|access[_-]?token|secret|password)\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{24,}['\"]")),
    ("key/token in a code span", re.compile(r"(?i)(auth[_-]?token|api[_-]?key|secret|password)[^\n]{0,20}`\s*([A-Za-z0-9+/=_-]{24,})\s*`")),
]

# base64 blob that decodes to "<id>:<secret>" - the shape n8n, Zapier MCP and
# most webhook providers hand out.
B64_BLOB = re.compile(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/]{40,}={0,2})(?![A-Za-z0-9+/=])")
DECODED_CREDENTIAL = re.compile(r"[A-Za-z0-9_-]{8,}:[A-Za-z0-9+/=_-]{16,}")


def looks_like_encoded_credential(blob: str) -> str | None:
    padded = blob + "=" * (-len(blob) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
    except Exception:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not all(32 <= ord(c) < 127 or c in "\r\n\t" for c in text):
        return None
    m = DECODED_CREDENTIAL.search(text)
    if m and len(text) < 400:
        return m.group(0)
    return None


def check_secrets() -> None:
    skip = {".git", "tools"}
    for f in LOCAL_DIR.rglob("*"):
        if not f.is_file() or any(part in skip for part in f.parts):
            continue
        if f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".zip", ".xlsx", ".ico", ".pdf"}:
            continue
        try:
            text = f.read_text(errors="ignore")
        except Exception:
            continue
        rel = f.relative_to(LOCAL_DIR)
        for label, rx in SECRET_PATTERNS:
            m = rx.search(text)
            if m:
                failures.append(f"possible credential in {rel} ({label}): {m.group(0)[:12]}…")
        for blob in B64_BLOB.findall(text):
            decoded = looks_like_encoded_credential(blob)
            if decoded:
                failures.append(
                    f"possible credential in {rel} (base64-encoded, decodes to): {decoded[:12]}…"
                )


def main() -> int:
    print(f"site base: {BASE}")
    pages = sorted(p.name for p in LOCAL_DIR.glob("*.html"))
    if not pages:
        print("FATAL: no html pages found")
        return 1

    page_links: dict[str, list[str]] = {}
    for page in pages:
        body = check_page(page)
        if body is None:
            continue
        page_links[page] = [l for l in body.splitlines() if l]

    check_retired()
    check_secrets()

    jobs = {p: ls for p, ls in page_links.items()}
    targets: list[tuple[str, str]] = []
    for page, links in jobs.items():
        for l in set(links):
            targets.append((page, l))

    print(f"pages: {len(pages)} | links+assets to verify: {len(targets)}")
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        list(ex.map(lambda t: check_target(t[0], t[1]), targets))

    lines = ["## Site health - M&M Auto Center", "", f"Base: {BASE}", f"Pages checked: {len(pages)}", f"Links/assets checked: {len(targets)}", ""]
    if failures:
        lines += [f"### Failed: {len(failures)}", ""] + [f"- {f}" for f in failures] + [""]
    if warnings:
        lines += [f"### Warnings: {len(warnings)}", ""] + [f"- {w}" for w in warnings] + [""]
    lines.append("### Result" if failures else "### Result: all green", )
    lines.append(("BROKEN - action needed" if failures else "OK - every page, link and asset answered correctly"))
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        pathlib.Path(summary).write_text(report + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
