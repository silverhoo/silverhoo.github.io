#!/usr/bin/env python3
"""맥의 결과물 폴더 → projects/<slug>/ 로 복사 · 변환 · 압축 · 썸네일 · 페이지 생성.

사용:
  python3 tools/sync.py <slug>            # sources.local.yml 의 폴더에서 가져온다
  python3 tools/sync.py <slug> --source 경로   # 폴더를 직접 지정 (시험용)
  python3 tools/sync.py <slug> --dry-run  # 무엇이 바뀔지만 보여준다
  python3 tools/sync.py <slug> --force    # 바뀌지 않은 파일도 다시 처리한다

프로젝트 폴더 구조 (생성 결과):
  projects/<slug>/index.html      프로젝트 페이지 (build.py 가 만든다)
  projects/<slug>/manifest.json   결과물 목록 (이 스크립트가 만든다)
  projects/<slug>/files/          원본 (내려받기용)
  projects/<slug>/pdf/            PPT·워드에서 만든 PDF (원본이 PDF 면 없음)
  projects/<slug>/web/            보기용 압축 PDF (원본이 가벼우면 없음)
  projects/<slug>/thumbs/         페이지 썸네일 (WebP)
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_lib import (PROJECTS_DIR, have, human_size, load_archive, load_manifest,  # noqa: E402
                         load_sources, nfc, pdf_pages, project_by_slug, resolve_source,
                         run, save_manifest, sha256_of, slugify)

OFFICE_EXT = {"pptx", "ppt", "docx", "doc", "odp", "odt", "key"}
WEB_THRESHOLD = 3 * 1024 * 1024      # 이보다 크면 보기용 압축본을 만든다
THUMB_PAGES = 6                      # 썸네일로 뽑을 앞 페이지 수
THUMB_WIDTH = 960


def log(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- 소스 파일 수집
def collect(src_dir: Path, include: list[str], exclude: list[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    walker = os.walk(src_dir) if recursive else [(str(src_dir), [], os.listdir(src_dir))]
    for base, dirs, names in walker:
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if name.startswith(".") or name.startswith("~$"):
                continue
            p = Path(base) / name
            if not p.is_file():
                continue
            n = nfc(name).lower()
            if not any(fnmatch.fnmatch(n, pat.lower()) for pat in include):
                continue
            if any(fnmatch.fnmatch(n, pat.lower()) for pat in exclude):
                continue
            files.append(p)
    return sorted(files, key=lambda p: nfc(p.name))


# ---------------------------------------------------------------- 변환 도구
def office_to_pdf(src: Path, out_dir: Path) -> Path | None:
    if not have("soffice"):
        log(f"  ! soffice 가 없어 {nfc(src.name)} 을 PDF 로 바꾸지 못했습니다")
        return None
    r = run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(src)], timeout=900)
    cand = out_dir / (src.stem + ".pdf")
    if r.returncode != 0 or not cand.exists():
        log(f"  ! 변환 실패: {nfc(src.name)}\n{r.stderr[-400:]}")
        return None
    return cand


def compress_pdf(src: Path, dst: Path) -> bool:
    """Ghostscript 로 화면용(가로 1920px 기준) 압축본을 만든다. 성공하고 충분히 작아졌을 때만 True."""
    if not have("gs"):
        return False
    r = run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5",
             "-dPDFSETTINGS=/ebook", "-dDownsampleColorImages=true", "-dColorImageResolution=72",
             "-dGrayImageResolution=72", "-dMonoImageResolution=150",
             "-dColorImageDownsampleThreshold=1.0", "-dGrayImageDownsampleThreshold=1.0",
             f"-sOutputFile={dst}", str(src)], timeout=1800)
    if r.returncode != 0 or not dst.exists():
        log(f"  ! 압축 실패: {nfc(src.name)}")
        return False
    if dst.stat().st_size > src.stat().st_size * 0.85:
        dst.unlink()          # 별로 안 줄면 원본을 그대로 쓴다
        return False
    return True


def make_thumbs(pdf: Path, out_dir: Path, base: str, n_pages: int | None) -> list[str]:
    if not have("pdftoppm"):
        return []
    try:
        from PIL import Image
    except ImportError:
        log("  ! Pillow 가 없어 썸네일을 만들지 못했습니다 (pip install pillow)")
        return []
    last = min(THUMB_PAGES, n_pages or THUMB_PAGES)
    with tempfile.TemporaryDirectory() as td:
        prefix = Path(td) / "p"
        r = run(["pdftoppm", "-png", "-f", "1", "-l", str(last), "-scale-to-x", str(THUMB_WIDTH),
                 "-scale-to-y", "-1", str(pdf), str(prefix)], timeout=600)
        if r.returncode != 0:
            log(f"  ! 썸네일 실패: {nfc(pdf.name)}")
            return []
        pngs = sorted(Path(td).glob("p-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
        out_dir.mkdir(parents=True, exist_ok=True)
        for old in out_dir.glob(f"{base}-*.webp"):
            old.unlink()
        names = []
        for i, png in enumerate(pngs, 1):
            dst = out_dir / f"{base}-{i}.webp"
            with Image.open(png) as im:
                im.convert("RGB").save(dst, "WEBP", quality=80, method=4)
            names.append(f"thumbs/{dst.name}")
        return names


def html_warnings(path: Path) -> list[str]:
    warns = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return [f"읽기 실패: {e}"]
    if 'src="/' in text or "src='/" in text or 'href="/' in text or "href='/" in text:
        warns.append("루트 경로(/...) 참조가 있어 하위 폴더에서 깨질 수 있음")
    if "file://" in text:
        warns.append("file:// 참조가 있음")
    return warns


# ---------------------------------------------------------------- 본체
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug")
    ap.add_argument("--source", help="소스 폴더를 직접 지정 (sources.local.yml 대신)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args()

    archive = load_archive()
    proj = project_by_slug(archive, args.slug)
    cfg = load_sources().get(args.slug, {})
    if args.source:
        src_dir = Path(os.path.expanduser(args.source)).resolve()
    elif cfg.get("source"):
        src_dir = resolve_source(cfg["source"])
    else:
        sys.exit(f"sources.local.yml 에 '{args.slug}' 의 source 가 없습니다. --source 로 지정할 수도 있습니다.")
    include = cfg.get("include") or ["*.pdf", "*.pptx", "*.docx", "*.html"]
    exclude = cfg.get("exclude") or []
    recursive = bool(cfg.get("recursive", False))

    log(f"[{args.slug}] {proj['title']}")
    log(f"  소스: {nfc(str(src_dir))}")
    files = collect(src_dir, include, exclude, recursive)
    if not files:
        sys.exit("  포함 규칙에 맞는 파일이 없습니다.")

    # 같은 이름의 PPT/워드 + PDF 쌍은 하나로 묶는다 (PDF 를 그 문서의 보기용으로)
    stems = {}
    for f in files:
        stems.setdefault(nfc(f.stem), {})[f.suffix.lower().lstrip(".")] = f
    plan = []          # (원본 Path, 짝 PDF Path|None)
    for stem, by_ext in stems.items():
        office = [e for e in by_ext if e in OFFICE_EXT]
        if office:
            for e in office:
                plan.append((by_ext[e], by_ext.get("pdf")))
        else:
            for e, f in by_ext.items():
                plan.append((f, None))
    plan.sort(key=lambda t: nfc(t[0].name))

    pdir = PROJECTS_DIR / args.slug
    old = load_manifest(args.slug)
    old_by_name = {it["source_name"]: it for it in old["items"]}
    used_slugs: set[str] = set()
    new_items = []
    added, updated, unchanged = [], [], []

    for src, pair_pdf in plan:
        name = nfc(src.name)
        ext = src.suffix.lower().lstrip(".")
        stem = nfc(src.stem)
        digest = sha256_of(src)
        pair_digest = sha256_of(pair_pdf) if pair_pdf else None
        base = slugify(stem)
        k = 2
        while base in used_slugs:
            base = f"{slugify(stem)}-{k}"
            k += 1
        used_slugs.add(base)

        prev = old_by_name.get(name)
        if prev and not args.force and prev.get("sha256") == digest and prev.get("pair_sha256") == pair_digest \
                and prev.get("base") == base and (pdir / prev["original"]).exists():
            new_items.append(prev)
            unchanged.append(name)
            continue

        (added if prev is None else updated).append(name)
        if args.dry_run:
            continue

        kind = "pdf" if ext == "pdf" else "office" if ext in OFFICE_EXT else "html" if ext in {"html", "htm"} else "other"
        item = {
            "name": stem, "source_name": name, "base": base, "ext": ext, "kind": kind,
            "size": src.stat().st_size, "sha256": digest, "pair_sha256": pair_digest,
            "original": f"files/{base}.{ext}", "pdf": None, "web": None, "web_size": None,
            "pages": None, "thumbs": [], "warnings": [],
            "updated": dt.date.today().isoformat(),
        }
        log(f"  → {name}")
        (pdir / "files").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, pdir / item["original"])

        pdf_path: Path | None = None
        if kind == "pdf":
            pdf_path = pdir / item["original"]
            item["pdf"] = item["original"]
        elif kind == "office":
            (pdir / "pdf").mkdir(parents=True, exist_ok=True)
            target = pdir / "pdf" / f"{base}.pdf"
            if pair_pdf is not None:
                shutil.copyfile(pair_pdf, target)
                log(f"     짝 PDF 사용: {nfc(pair_pdf.name)}")
            else:
                with tempfile.TemporaryDirectory() as td:
                    conv = office_to_pdf(src, Path(td))
                    if conv:
                        shutil.copyfile(conv, target)
                        log("     LibreOffice 로 PDF 변환 (글꼴 대체 여부 확인 필요)")
            if target.exists():
                pdf_path = target
                item["pdf"] = f"pdf/{base}.pdf"
        elif kind == "html":
            item["warnings"] = html_warnings(src)
            for w in item["warnings"]:
                log(f"     ! {w}")

        if pdf_path is not None:
            item["pages"] = pdf_pages(pdf_path)
            if pdf_path.stat().st_size > WEB_THRESHOLD:
                (pdir / "web").mkdir(parents=True, exist_ok=True)
                wp = pdir / "web" / f"{base}.pdf"
                if compress_pdf(pdf_path, wp):
                    item["web"] = f"web/{base}.pdf"
                    item["web_size"] = wp.stat().st_size
                    log(f"     보기용 압축 {human_size(pdf_path.stat().st_size)} → {human_size(item['web_size'])}")
            item["thumbs"] = make_thumbs(pdf_path, pdir / "thumbs", base, item["pages"])
            log(f"     {item['pages']}쪽 · 썸네일 {len(item['thumbs'])}장")
        new_items.append(item)

    # 사라진 원본 정리
    removed = [n for n in old_by_name if n not in {nfc(s.name) for s, _ in plan}]
    if not args.dry_run:
        for n in removed:
            it = old_by_name[n]
            for rel in [it.get("original"), it.get("pdf"), it.get("web"), *it.get("thumbs", [])]:
                if rel and (pdir / rel).exists():
                    (pdir / rel).unlink()
        new_items.sort(key=lambda it: it["source_name"])
        save_manifest(args.slug, {"slug": args.slug, "updated": dt.date.today().isoformat(), "items": new_items})

    log("")
    log(f"  추가 {len(added)} · 갱신 {len(updated)} · 그대로 {len(unchanged)} · 삭제 {len(removed)}"
        + ("  (dry-run: 실제로 바꾸지 않음)" if args.dry_run else ""))
    for n in added:
        log(f"    + {n}")
    for n in updated:
        log(f"    ~ {n}")
    for n in removed:
        log(f"    - {n}")

    if not args.dry_run and not args.no_build:
        import build  # noqa: E402  (같은 폴더)
        build.main()


if __name__ == "__main__":
    main()
