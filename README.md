# 아카이브 사이트

프로젝트 결과물(PDF · PPT · 워드 · HTML)을 한곳에 모아 두는 정적 사이트. GitHub Pages 로 배포한다.

## 구조

```
index.html                 첫 화면 (tools/build.py 가 만든다)
archive.yml                프로젝트 목록 — 제목 · 상태 · 공개 여부 · 요약
sources.local.yml          프로젝트 ↔ 맥 폴더 연결 (저장소에 올리지 않는다)
projects/<slug>/           프로젝트 하나
  index.html               프로젝트 페이지 (자동 생성)
  manifest.json            결과물 목록 (tools/sync.py 가 만든다)
  files/                   원본
  pdf/                     PPT·워드에서 만든 PDF
  web/                     보기용 압축 PDF
  thumbs/                  페이지 썸네일
viewer/pdf.html            PDF 뷰어 (PDF.js 동봉)
assets/site.css            조판 규칙
tools/sync.py              맥 폴더 → projects/ 복사 · 변환 · 압축 · 썸네일 · 페이지 생성
tools/build.py             페이지만 다시 생성
.github/workflows/deploy.yml   main 푸시 → Pages 배포 (환경 승인 후)
```

## 갱신

```
python3 tools/sync.py retro        # sources.local.yml 의 폴더에서 가져온다
python3 tools/sync.py retro --dry-run
git add -A && git commit -m "retro: 갱신" && git push
```

푸시하면 GitHub Actions 가 배포를 준비하고, 저장소 설정의 github-pages 환경에서 승인하면 반영된다.

## 필요한 것

파이썬 3.9+, PyYAML, Pillow, poppler(pdfinfo · pdftoppm), Ghostscript(압축, 없어도 됨), LibreOffice(PPT·워드 변환, PDF 가 이미 있으면 필요 없음).
