"""공용 함수 — sync.py 와 build.py 가 함께 쓴다.

의존성: 파이썬 3.9+, PyYAML. (없으면 `pip install pyyaml`)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML 이 필요합니다: pip install pyyaml")

ROOT = Path(__file__).resolve().parent.parent      # 저장소 루트
ARCHIVE_YML = ROOT / "archive.yml"                 # 공개 목록 (커밋됨)
SOURCES_YML = ROOT / "sources.local.yml"           # 맥 폴더 연결 (커밋 안 됨)
PROJECTS_DIR = ROOT / "projects"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


# ---------------------------------------------------------------- 한글 로마자
_INITIALS = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "",
             "j", "jj", "ch", "k", "t", "p", "h"]
_MEDIALS = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae",
            "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i"]
_FINALS = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l",
           "p", "l", "m", "p", "p", "t", "t", "ng", "t", "t", "k", "t", "p", "t"]


def romanize(text: str) -> str:
    """한글 음절을 국어의 로마자 표기법(음절 단위)으로 바꾼다. 나머지 글자는 그대로."""
    out = []
    for ch in nfc(text):
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            ini, rest = divmod(idx, 21 * 28)
            med, fin = divmod(rest, 28)
            out.append(_INITIALS[ini] + _MEDIALS[med] + _FINALS[fin])
        else:
            out.append(ch)
    return "".join(out)


def slugify(name: str, max_len: int = 60) -> str:
    """파일 이름(확장자 제외)을 주소용 ASCII 슬러그로."""
    s = romanize(name).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    if not s:
        s = "file"
    return s[:max_len].rstrip("-")


# ---------------------------------------------------------------- 설정 파일
def load_archive() -> dict:
    data = yaml.safe_load(ARCHIVE_YML.read_text(encoding="utf-8")) or {}
    data.setdefault("site", {})
    data.setdefault("projects", [])
    for p in data["projects"]:
        p.setdefault("status", "진행 중")
        p.setdefault("visibility", "public")
    return data


def load_sources() -> dict:
    if not SOURCES_YML.exists():
        return {}
    return yaml.safe_load(SOURCES_YML.read_text(encoding="utf-8")) or {}


def project_by_slug(archive: dict, slug: str) -> dict:
    for p in archive["projects"]:
        if p["slug"] == slug:
            return p
    sys.exit(f"archive.yml 에 slug '{slug}' 가 없습니다.")


# ---------------------------------------------------------------- 경로 해석
def _walk_match(base: Path, comps: list[str]) -> Path | None:
    """base 아래로 comps 를 내려가되, 각 단계의 이름을 NFC 로 비교한다 (맥의 NFD 이름 대응)."""
    cur = base
    for comp in comps:
        found = None
        try:
            for entry in os.listdir(cur):
                if nfc(entry) == nfc(comp):
                    found = cur / entry
                    break
        except FileNotFoundError:
            return None
        if found is None:
            return None
        cur = found
    return cur


def resolve_source(mac_path: str) -> Path:
    """sources.local.yml 에 적힌 맥 경로를 실제로 읽을 수 있는 경로로.

    1) 그 경로가 그대로 있으면 (맥에서 직접 실행) 그대로.
    2) 맥에 연결된 작업 환경이면 ~/mnt/<연결된 폴더 이름>/... 로 옮겨 찾는다.
       연결된 폴더가 상위 폴더여도 된다.
    """
    p = Path(os.path.expanduser(mac_path))
    if p.is_dir():
        return p
    mnt = Path(os.path.expanduser("~/mnt"))
    if mnt.is_dir():
        comps = [nfc(c) for c in p.parts]
        best: Path | None = None
        for entry in os.listdir(mnt):
            n = nfc(entry)
            if n in comps:
                idx = len(comps) - 1 - comps[::-1].index(n)
                cand = _walk_match(mnt / entry, comps[idx + 1:])
                if cand is not None and cand.is_dir():
                    if best is None or len(str(cand)) > len(str(best)):
                        best = cand
        if best is not None:
            return best
        raise FileNotFoundError(
            f"'{mac_path}' 를 ~/mnt 아래에서 찾지 못했습니다. "
            f"연결된 폴더: {', '.join(nfc(e) for e in os.listdir(mnt)) or '(없음)'}")
    raise FileNotFoundError(f"'{mac_path}' 가 없습니다.")


# ---------------------------------------------------------------- 파일 도구
def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def pdf_pages(path: Path) -> int | None:
    if not have("pdfinfo"):
        return None
    r = run(["pdfinfo", str(path)], timeout=60)
    m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
    return int(m.group(1)) if m else None


def human_size(n: int) -> str:
    if n < 1024 * 1024:
        return f"{max(1, round(n / 1024))} KB"
    return f"{n / 1048576:.1f} MB"


# ---------------------------------------------------------------- manifest
def manifest_path(slug: str) -> Path:
    return PROJECTS_DIR / slug / "manifest.json"


def load_manifest(slug: str) -> dict:
    mp = manifest_path(slug)
    if mp.exists():
        return json.loads(mp.read_text(encoding="utf-8"))
    return {"slug": slug, "updated": None, "items": []}


def save_manifest(slug: str, data: dict) -> None:
    mp = manifest_path(slug)
    mp.parent.mkdir(parents=True, exist_ok=True)
    mp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
