#!/usr/bin/env python3
"""archive.yml + projects/retro/manifest.json → index.html

뼈대 1 — 작업이 1급. 홈은 작업 / 회고 / 소개 세 갈래이고,
각 항목은 덱 한 벌을 가리킨다. 클릭하면 슬라이드 뷰어가 열린다.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parent.parent
DECKS = ROOT / "projects" / "retro"


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def url(rel: str) -> str:
    return quote(rel, safe="/-_.~")


def human(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


def main() -> None:
    cfg = yaml.safe_load((ROOT / "archive.yml").read_text(encoding="utf-8"))
    site, sections, about = cfg["site"], cfg["sections"], cfg.get("about", [])
    man = json.loads((DECKS / "manifest.json").read_text(encoding="utf-8"))
    by_base = {it["base"]: it for it in man["items"]}

    nav = "".join(
        f'<li><a href="#{sid}">{esc(t)}</a></li>'
        for sid, t in [("work", site["nav"][0]), ("retro", site["nav"][1]), ("about", site["nav"][2])]
    )

    out = []
    for sec in sections:
        rows = []
        for e in sec["entries"]:
            it = by_base.get(e["base"])
            if it is None:
                print(f"  ! manifest 에 '{e['base']}' 가 없다 — 건너뜀", file=sys.stderr)
                continue
            view = it.get("web") or it.get("pdf") or it["original"]
            args = (f"f=../projects/retro/{url(view)}"
                    f"&t={quote(e['title'])}"
                    f"&o=../projects/retro/{url(it['original'])}"
                    f"&p=../index.html")
            href = f"viewer/slides.html?{args}"
            thumb = it["thumbs"][0] if it.get("thumbs") else None
            shot = (f'<a class="shot" href="{href}"><img src="projects/retro/{url(thumb)}" alt="" loading="lazy" '
                    f'width="960" height="540"></a>') if thumb else '<div class="shot"></div>'
            pages = f'{it["pages"]}쪽' if it.get("pages") else ""
            size = human(it["size"])
            rows.append(f"""      <li class="entry">
        {shot}
        <div>
          <div class="ehead"><span class="k">{esc(e['kicker'])}</span><span class="y">{esc(e['year'])} · {esc(e['meta'])}</span></div>
          <h3><a href="{href}">{esc(e['title'])}</a></h3>
          <p class="goal">{esc(e['goal'])}</p>
          <p class="steps">{esc(e['steps'])}</p>
          <div class="links">
            <a href="{href}">넘겨 보기 →</a>
            <a class="sub" href="projects/retro/{url(it['original'])}" download>원본 PDF</a>
            <span class="d">{pages} · {size}</span>
          </div>
        </div>
      </li>""")
        out.append(f"""  <section class="sec" id="{esc(sec['id'])}">
    <div class="sechead"><h2>{esc(sec['title'])}</h2><span class="n">{len(rows)}</span><span class="rule"></span></div>
    <p class="seclead">{esc(sec['lead'])}</p>
    <ul class="list">
{chr(10).join(rows)}
    </ul>
  </section>""")

    abt = []
    for line in about:
        if isinstance(line, dict) and "email" in line:
            m = line["email"]
            abt.append(f'    <p class="c">연락은 <a class="mail" href="mailto:{esc(m)}">{esc(m)}</a> 으로.</p>')
        else:
            abt.append(f"    <p>{esc(line)}</p>")

    page = f"""<!DOCTYPE html>
<html lang="{esc(site.get('lang', 'ko'))}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(site['name'])} — {esc(site['kicker'])}</title>
<meta name="description" content="{esc(site['decl_muted_1'])} {esc(site['decl_ink'])}">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<div class="wrap">
  <nav class="nav"><a class="me" href="#top">{esc(site['name'])}</a><ul>{nav}</ul></nav>

  <header class="mast" id="top">
    <p class="kicker">{esc(site['kicker'])}</p>
    <h1 class="decl">{esc(site['decl_muted_1'])} <b>{esc(site['decl_ink'])}</b></h1>
    <p class="sub">{esc(site['sub'])}</p>
  </header>

{chr(10).join(out)}

  <section class="sec about" id="about">
    <div class="sechead"><h2>{esc(site['nav'][2])}</h2><span class="rule"></span></div>
{chr(10).join(abt)}
  </section>

  <footer class="foot"><span>{esc(site['footer_left'])}</span><span>{esc(site['footer_right'])}</span></footer>
</div>
</body>
</html>
"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    n = sum(len(s["entries"]) for s in sections)
    print(f"build: index.html — {len(sections)}개 섹션 · {n}개 항목")


if __name__ == "__main__":
    main()
