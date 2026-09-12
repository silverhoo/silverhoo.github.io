#!/usr/bin/env python3
"""archive.yml + projects/retro/manifest.json → index.html

뼈대 1 — 작업이 1급. 좌측 고정 칼럼(이름·선언문·내비·근황)과 우측 목록.
각 항목은 덱 한 벌을 가리키고, 표지에 손을 올리면 앞장 여섯 장이 넘어간다.
누르면 슬라이드 뷰어가 열린다.
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
PREVIEW = 6  # 표지 포함, 호버로 넘겨 보는 앞장 수

SCRIPT = """
// 1) 표지에 손을 올리면 덱의 앞장이 넘어간다. 손을 떼면 표지로 돌아온다.
// 2) 왼쪽 내비는 지금 읽고 있는 섹션을 표시한다.
(function () {
  var slow = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.querySelectorAll('.entry').forEach(function (entry) {
    var shot = entry.querySelector('.shot[data-n]');
    if (!shot) return;
    var imgs = shot.querySelectorAll('img');
    var ticks = shot.querySelectorAll('.ticks i');
    var n = imgs.length, at = 0, timer = null;

    function go(i) {
      if (i === at) return;
      imgs[at].classList.remove('on');
      ticks[at].classList.remove('on');
      at = i;
      imgs[at].classList.add('on');
      ticks[at].classList.add('on');
    }
    function start() {
      if (slow || n < 2 || timer) return;
      for (var i = 0; i < n; i++) imgs[i].loading = 'eager';
      timer = setInterval(function () { go((at + 1) % n); }, 680);
    }
    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
      go(0);
    }
    entry.addEventListener('mouseenter', start);
    entry.addEventListener('mouseleave', stop);
    entry.addEventListener('focusin', start);
    entry.addEventListener('focusout', stop);
  });

  var links = {}, order = [], visible = {};
  document.querySelectorAll('.snav a').forEach(function (a) {
    var id = a.getAttribute('href').slice(1);
    var sec = document.getElementById(id);
    if (!sec) return;
    links[id] = a;
    order.push(sec);
  });
  if (!order.length || !('IntersectionObserver' in window)) return;

  function paint() {
    var cur = null;
    for (var i = 0; i < order.length; i++) {
      if (visible[order[i].id]) { cur = order[i].id; break; }
    }
    for (var id in links) {
      if (id === cur) links[id].setAttribute('aria-current', 'true');
      else links[id].removeAttribute('aria-current');
    }
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting; });
    paint();
  }, { rootMargin: '-12% 0px -68% 0px', threshold: 0 });
  order.forEach(function (s) { io.observe(s); });
})();
"""


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def url(rel: str) -> str:
    return quote(rel, safe="/-_.~")


def human(n: int) -> str:
    return f"{n / 1048576:.1f} MB" if n >= 1048576 else f"{max(1, round(n / 1024))} KB"


def shot_html(href: str, thumbs: list) -> str:
    if not thumbs:
        return '<span class="shot"></span>'
    imgs = []
    for i, t in enumerate(thumbs):
        cls = ' class="on"' if i == 0 else ""
        lazy = "" if i == 0 else ' loading="lazy"'
        imgs.append(f'<img src="projects/retro/{url(t)}" alt=""{cls}{lazy} width="960" height="540">')
    ticks = "".join(('<i class="on"></i>' if i == 0 else "<i></i>") for i in range(len(thumbs)))
    return (f'<a class="shot" href="{href}" tabindex="-1" aria-hidden="true" data-n="{len(thumbs)}">'
            f'{"".join(imgs)}<span class="ticks">{ticks}</span></a>')


def main() -> None:
    cfg = yaml.safe_load((ROOT / "archive.yml").read_text(encoding="utf-8"))
    site, sections, about = cfg["site"], cfg["sections"], cfg.get("about", [])
    news = cfg.get("news", [])
    man = json.loads((DECKS / "manifest.json").read_text(encoding="utf-8"))
    by_base = {it["base"]: it for it in man["items"]}

    counts, blocks = {}, []
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
            pages = f'{it["pages"]}쪽' if it.get("pages") else ""
            rows.append(f"""      <li class="entry">
        {shot_html(href, (it.get("thumbs") or [])[:PREVIEW])}
        <div>
          <p class="ehead"><span class="k">{esc(e['kicker'])}</span><span class="y">{esc(e['year'])} · {esc(e['meta'])}</span></p>
          <h3><a href="{href}">{esc(e['title'])}</a></h3>
          <p class="goal">{esc(e['goal'])}</p>
          <p class="steps">{esc(e['steps'])}</p>
          <p class="links">
            <a class="go" href="{href}">넘겨 보기 →</a>
            <a class="sub" href="projects/retro/{url(it['original'])}" download>원본 PDF</a>
            <span class="d">{pages} · {human(it['size'])}</span>
          </p>
        </div>
      </li>""")
        counts[sec["id"]] = len(rows)
        blocks.append(f"""    <section class="sec" id="{esc(sec['id'])}">
      <div class="sechead"><h2>{esc(sec['title'])}</h2><span class="n">{len(rows)}</span><span class="rule"></span></div>
      <p class="seclead">{esc(sec['lead'])}</p>
      <ul class="list">
{chr(10).join(rows)}
      </ul>
    </section>""")

    nav = "".join(
        f'<li><a href="#{sid}">{esc(t)}'
        + (f'<span class="n">{counts[sid]}</span>' if sid in counts else "")
        + "</a></li>"
        for sid, t in [("work", site["nav"][0]), ("retro", site["nav"][1]), ("about", site["nav"][2])]
    )

    news_html = ""
    if news:
        items = "".join(f'<li><time>{esc(n["date"])}</time><span>{esc(n["text"])}</span></li>'
                        for n in news)
        news_html = (f'\n      <div class="news">\n        <p class="lab">근황</p>'
                     f'\n        <ul>{items}</ul>\n      </div>')

    abt, mail = [], ""
    for line in about:
        if isinstance(line, dict) and "email" in line:
            mail = line["email"]   # 연락처는 좌측 칼럼에만 둔다 — 소개에서 되풀이하지 않는다
        else:
            abt.append(f"      <p>{esc(line)}</p>")
    mail_html = (f'\n      <p class="mail"><a href="mailto:{esc(mail)}">{esc(mail)}</a></p>'
                 if mail else "")

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
  <div class="shell">

    <header class="side" id="top">
      <a class="me" href="#top">{esc(site['name'])}</a>
      <p class="role">{esc(site['sub'])}</p>
      <div class="hr"></div>
      <p class="decl">{esc(site['decl_muted_1'])} <b>{esc(site['decl_ink'])}</b></p>
      <nav aria-label="섹션"><ul class="snav">{nav}</ul></nav>{news_html}{mail_html}
    </header>

    <main class="main">
{chr(10).join(blocks)}

    <section class="sec about" id="about">
      <div class="sechead"><h2>{esc(site['nav'][2])}</h2><span class="rule"></span></div>
{chr(10).join(abt)}
    </section>

    <footer class="foot"><span>{esc(site['footer_left'])}</span><span>{esc(site['footer_right'])}</span></footer>
    </main>

  </div>
</div>

<script>{SCRIPT}</script>
</body>
</html>
"""
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"build: index.html — {len(sections) + 1}개 섹션 · {sum(counts.values())}개 항목")


if __name__ == "__main__":
    main()
