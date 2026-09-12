#!/usr/bin/env python3
"""archive.yml + projects/*/manifest.json → index.html, projects/<slug>/index.html

사용: python3 tools/build.py
비공개(visibility: private) 프로젝트는 페이지도 카드도 만들지 않는다.
"""
from __future__ import annotations

import datetime as dt
import html
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_lib import PROJECTS_DIR, ROOT, human_size, load_archive, load_manifest  # noqa: E402

KIND_LABEL = {"pdf": "PDF", "office": "문서", "html": "HTML", "other": "파일"}
EXT_LABEL = {"pptx": "PowerPoint", "ppt": "PowerPoint", "docx": "Word", "doc": "Word",
             "key": "Keynote", "odp": "프레젠테이션", "odt": "문서", "pdf": "PDF", "html": "HTML", "htm": "HTML"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def url(rel: str) -> str:
    return quote(rel, safe="/-_.~")


def status_chip(status: str) -> str:
    cls = "status done" if status == "완료" else "status"
    return f'<span class="{cls}">{esc(status)}</span>'


def page(site: dict, title: str, body: str, depth: int, active: str = "") -> str:
    up = "../" * depth
    year = dt.date.today().year
    author = site.get("author") or site.get("title", "")
    nav_items = [("index", f'<a class="{"active" if active == "index" else ""}" href="{up}index.html">{esc(site.get("title", "Archive"))}</a>')]
    right = f'<span>{esc(site.get("nav_right", "PROJECTS"))}</span>'
    return f"""<!DOCTYPE html>
<html lang="{esc(site.get('lang', 'ko'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(site.get('description', ''))}">
<link rel="stylesheet" href="{up}assets/site.css">
</head>
<body>
<div class="wrap">
  <nav class="top">{nav_items[0][1]}{right}</nav>
{body}
  <footer class="foot">
    <span>© {year} {esc(author)}</span>
    <span>{esc(site.get('footer', ''))}</span>
  </footer>
</div>
</body>
</html>
"""


def build_index(archive: dict, visible: list[dict], manifests: dict) -> None:
    site = archive["site"]
    rows = []
    for i, p in enumerate(visible, 1):
        m = manifests.get(p["slug"])
        items = m["items"] if m else []
        cover = None
        main_name = p.get("main")
        for it in items:
            if it.get("thumbs") and (main_name is None or it["source_name"] == main_name or it["name"] == main_name):
                cover = it["thumbs"][0]
                if main_name is not None and (it["source_name"] == main_name or it["name"] == main_name):
                    break
        href = f"projects/{p['slug']}/index.html"
        thumb = (f'<a class="thumb" href="{href}"><img src="projects/{p["slug"]}/{url(cover)}" alt="" loading="lazy"></a>'
                 if cover else f'<a class="thumb empty" href="{href}">{"결과물 준비 중" if not items else ""}</a>')
        meta_bits = []
        if p.get("date"):
            meta_bits.append(esc(p["date"]))
        if items:
            meta_bits.append(f"결과물 {len(items)}")
        if m and m.get("updated"):
            meta_bits.append(f"갱신 {esc(m['updated'])}")
        meta = '<span class="sep">·</span>'.join(meta_bits)
        rows.append(f"""    <li class="row">
      <div class="num">{i:02d}</div>
      <div>
        <h2><a href="{href}">{esc(p['title'])}</a>{status_chip(p['status'])}</h2>
        <p>{esc(p.get('summary', ''))}</p>
        <div class="meta">{meta}</div>
      </div>
      {thumb}
    </li>""")
    body = f"""  <header class="mast">
    <p class="kicker">{esc(site.get('kicker', 'ARCHIVE'))}</p>
    <h1>{esc(site.get('title', 'Archive'))}</h1>
    <p class="lead">{esc(site.get('intro', ''))}</p>
  </header>
  <ol class="list">
{chr(10).join(rows) if rows else '    <li class="row"><div class="num">—</div><div><p>아직 올린 프로젝트가 없다.</p></div></li>'}
  </ol>"""
    (ROOT / "index.html").write_text(page(site, site.get("title", "Archive"), body, 0, "index"), encoding="utf-8")


def build_project(archive: dict, p: dict, m: dict, order: int) -> None:
    site = archive["site"]
    items_html = []
    main_name = p.get("main")
    items = sorted(m["items"], key=lambda it: (0 if main_name in (it["source_name"], it["name"]) else 1, it["source_name"]))
    for it in items:
        base_url = url(it["original"])
        kind_label = EXT_LABEL.get(it["ext"], KIND_LABEL.get(it["kind"], "파일"))
        meta_bits = [kind_label]
        if it.get("pages"):
            meta_bits.append(f"{it['pages']}쪽")
        meta_bits.append(human_size(it["size"]))
        if it.get("updated"):
            meta_bits.append(esc(it["updated"]))
        meta = '<span class="sep">·</span>'.join(meta_bits)

        links = []
        view_pdf = it.get("web") or it.get("pdf")
        if view_pdf:
            q = (f"f=../../projects/{p['slug']}/{url(view_pdf)}"
                 f"&t={quote(it['name'])}"
                 f"&o=../../projects/{p['slug']}/{base_url}"
                 f"&p=../../projects/{p['slug']}/index.html")
            links.append(f'<a href="../../viewer/pdf.html?{q}">보기 →</a>')
            if it["kind"] == "office":
                links.append(f'<a class="sub" href="{url(it["pdf"])}" target="_blank" rel="noopener">PDF</a>')
        elif it["kind"] == "html":
            links.append(f'<a href="{base_url}" target="_blank" rel="noopener">열기 →</a>')
        links.append(f'<a class="sub" href="{base_url}" download>원본 내려받기 ({esc(it["ext"].upper())})</a>')

        cover = (f'<a class="thumb" href="{links[0].split(chr(34))[1] if links else "#"}"><img src="{url(it["thumbs"][0])}" alt="" loading="lazy"></a>'
                 if it.get("thumbs") else f'<div class="thumb empty">{esc(kind_label)}</div>')
        strip = ""
        if len(it.get("thumbs", [])) > 1:
            strip = '<div class="strip">' + "".join(f'<img src="{url(t)}" alt="" loading="lazy">' for t in it["thumbs"]) + "</div>"
        warn = "".join(f'<div class="warn">! {esc(w)}</div>' for w in it.get("warnings", []))
        items_html.append(f"""    <li class="item">
      {cover}
      <div>
        <h3>{esc(it['name'])}</h3>
        <div class="meta">{meta}</div>
        <div class="links">{' '.join(links)}</div>
        {strip}{warn}
      </div>
    </li>""")

    body = f"""  <header class="head">
    <p class="kicker">{order:02d} · {esc(p['status'])}{(' · ' + esc(p['date'])) if p.get('date') else ''}</p>
    <h1>{esc(p['title'])}</h1>
    <p class="lead">{esc(p.get('summary', ''))}</p>
  </header>
  <p class="section-title">결과물 {len(m['items'])}</p>
  <ul class="list">
{chr(10).join(items_html) if items_html else '    <li class="item"><div class="thumb empty">준비 중</div><div><p class="meta">아직 올린 결과물이 없다.</p></div></li>'}
  </ul>"""
    out = PROJECTS_DIR / p["slug"] / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(site, f"{p['title']} — {site.get('title', 'Archive')}", body, 2), encoding="utf-8")


def main() -> None:
    archive = load_archive()
    visible = [p for p in archive["projects"] if p.get("visibility", "public") == "public"]
    manifests = {p["slug"]: load_manifest(p["slug"]) for p in visible}
    build_index(archive, visible, manifests)
    for i, p in enumerate(visible, 1):
        build_project(archive, p, manifests[p["slug"]], i)
    hidden = [p["slug"] for p in archive["projects"] if p.get("visibility") != "public"]
    print(f"build: index + 프로젝트 {len(visible)}장 생성" + (f" (비공개 제외: {', '.join(hidden)})" if hidden else ""))


if __name__ == "__main__":
    main()
