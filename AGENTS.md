# AGENTS.md

## Project Name

**DownloadOrganizer**

## Project Summary

DownloadOrganizer는 사용자의 다운로드 폴더를 분석하여 파일을 유형, 날짜, 크기, 중복 여부에 따라 체계적으로 분류하고, 정리 결과를 Markdown, HTML, Excel 문서로 생성하는 Python 기반 도구이다.

또한 Chrome, Edge 등 웹브라우저의 북마크 파일을 분석하여 도메인별, 주제별, 중복 URL별로 정리하고 북마크 보고서를 생성한다.

본 프로젝트는 다음 두 가지 실행 형태를 제공한다.

1. Python 단독 실행 CLI 버전
2. Streamlit 기반 웹 버전

향후 PyInstaller를 활용하여 Windows EXE 파일로 패키징할 수 있도록 구성한다.

---

## 구현 현황 (현재 버전, 본 문서 갱신 기준)

아래 본문 중 일부(설계 초안·역할 프롬프트 등)는 기획 단계 기록이며, **현재 구현은 다음과 같다.**

- **3단계 안전 실행**: `analyze`(미리보기·계획 토큰 발급) → `apply`(토큰 일치 시에만 이동) → `undo`(되돌리기, `--preview` 지원). 토큰은 계획에 바인딩되어 오래된 계획 적용을 차단.
- **분류 폴더는 한글**(문서/이미지/동영상/오디오/압축파일/실행파일/코드/기타), 확장자 기준. `--ext-grouping`·`--date-grouping`으로 하위 분류, `--route-old/--route-duplicates`로 분리 폴더.
- **삭제는 영구 삭제 없이 휴지통(send2trash)만**: `clean`(중복 1개 보존/오래된/선택), `--remove-empty-dirs`(이동 후 빈 폴더). 모두 복구 가능.
- **중복 탐지** strict(전체 해시)/fast(앞 1MB), 크기 선그룹화. **선택적 적용**(분류/파일 단위).
- **보고서** Markdown/HTML/Excel(타임스탬프, 다운로드/북마크 분리). **운영 로깅**.
- **설정 파일(config.json)**: 분류 규칙·기준일·차단경로 추가·북마크 카테고리 override.
- **웹 UI(Streamlit)**: 체크박스 표 선택, 진행바, 이동 후 결과 폴더 구조(요약+트리), 다크모드 대응. 북마크 탭·일괄 휴지통 탭은 기본 숨김(토글).
- **배포**: GitHub Pages 소개 페이지(`docs/`), Streamlit Cloud 데모, EXE 빌드 스크립트. 시크릿/개인정보 미포함(보안 점검 완료).
- **테스트**: pytest 57개 통과.

---

## Core Goals

1. 다운로드 폴더를 안전하게 분석한다.
2. 파일을 체계적인 폴더 구조로 분류한다.
3. 정리 전 미리보기 기능을 제공한다.
4. 기본값은 Dry-run으로 설정하여 실제 파일 이동 전 사용자 확인을 받는다.
5. 실제 이동 시 이동 이력을 기록한다.
6. 필요 시 되돌리기 기능을 제공한다.
7. 중복파일을 탐지하되 자동 삭제하지 않는다.
8. 오래된 파일을 탐지하여 별도 분류 후보로 제시한다.
9. Chrome, Edge 브라우저 북마크를 분석한다.
10. 정리 결과와 북마크 분석 결과를 문서화한다.

---

## Recommended Folder Name

프로젝트 폴더명은 다음을 권장한다.

```text
DownloadOrganizer
```

대체 후보는 다음과 같다.

```text
download-organizer
smart-file-organizer
file-bookmark-organizer
pc-cleanup-assistant
```

최종 권장명은 **DownloadOrganizer**이다.

---

## Target Users

- 다운로드 폴더가 자주 어지러워지는 일반 사용자
- 업무자료를 자주 다운로드하는 공공기관 직원
- 문서, 이미지, 압축파일, 설치파일을 체계적으로 정리하고 싶은 사용자
- 브라우저 북마크를 문서로 백업·정리하고 싶은 사용자

---

## Main Features

### 1. Download Folder Scanner

다운로드 폴더를 스캔하여 다음 정보를 수집한다.

- 파일명
- 파일 경로
- 확장자
- 파일 크기
- 생성일
- 수정일
- 마지막 접근일
- 파일 유형
- 해시값
- 중복 여부
- 오래된 파일 여부

### 2. File Classification

확장자와 규칙을 기준으로 파일을 분류한다.

기본 분류 예시는 다음과 같다.

```text
Downloads_Organized/
├─ 01_Documents/
│  ├─ PDF/
│  ├─ Word/
│  ├─ Excel/
│  ├─ PowerPoint/
│  └─ Text/
├─ 02_Images/
├─ 03_Videos/
├─ 04_Audio/
├─ 05_Compressed/
├─ 06_Installers/
├─ 07_Code/
├─ 08_Work_Files/
├─ 09_Old_Files/
├─ 10_Duplicates/
└─ 99_Etc/
```

### 3. Dry-run Preview

실제 파일 이동 전 다음 내용을 미리 보여준다.

- 이동 대상 파일
- 현재 위치
- 이동 예정 위치
- 분류 사유
- 중복 여부
- 오래된 파일 여부

기본 실행은 반드시 Dry-run이어야 한다.

### 4. File Move Execution

사용자가 명시적으로 승인한 경우에만 파일을 이동한다.

필수 조건:

- 원본 파일 삭제 금지
- 중복파일 자동 삭제 금지
- 동일 이름 파일 충돌 시 안전한 이름으로 변경
- 이동 실패 시 오류 로그 기록
- 이동 성공 시 history 파일 기록

### 5. Undo Feature

이동 이력 JSON 파일을 기반으로 파일 이동을 되돌린다.

조건:

- 되돌리기 전에 미리보기 제공
- 원래 위치에 동일 이름 파일이 있으면 덮어쓰기 금지
- 충돌 시 사용자에게 알림 또는 안전한 이름으로 복원

### 6. Duplicate Detection

파일 해시값을 기준으로 중복파일을 탐지한다.

주의:

- 중복파일은 자동 삭제하지 않는다.
- 보고서에 중복 후보로만 표시한다.
- 사용자가 직접 판단할 수 있게 파일 경로와 크기를 제공한다.

### 7. Old File Detection

기본 기준으로 180일 이상 수정되지 않은 파일을 오래된 파일 후보로 표시한다.

설정 가능 항목:

- 오래된 파일 기준 일수
- 제외할 확장자
- 제외할 폴더

### 8. Bookmark Organizer

Chrome, Edge 브라우저의 북마크 파일을 분석한다.

기능:

- 북마크 JSON 파일 읽기
- URL 추출
- 제목 추출
- 도메인 추출
- 폴더 구조 추출
- 중복 URL 탐지
- 도메인별 분류
- 키워드 기반 카테고리 분류
- 북마크 보고서 생성

브라우저별 기본 북마크 경로 예시:

```text
Chrome:
%LOCALAPPDATA%/Google/Chrome/User Data/Default/Bookmarks

Edge:
%LOCALAPPDATA%/Microsoft/Edge/User Data/Default/Bookmarks
```

### 9. Report Generation

다음 형식의 보고서를 생성한다.

- Markdown
- HTML
- Excel

보고서 항목:

- 정리 실행 일시
- 대상 폴더
- 전체 파일 수
- 전체 파일 용량
- 파일 유형별 개수
- 파일 유형별 용량
- 중복파일 후보
- 오래된 파일 후보
- 이동 예정 목록
- 실제 이동 결과
- 실패 목록
- 최종 폴더 구조
- 북마크 도메인별 통계
- 북마크 중복 URL 목록
- 북마크 카테고리별 목록

---

## Technology Stack

### Language

```text
Python 3.11+
```

### Core Libraries

```text
pathlib
shutil
hashlib
json
csv
datetime
logging
```

### External Libraries (현재 사용)

```text
pandas        # 표/보고서
openpyxl      # Excel 보고서
streamlit     # 웹 UI
send2trash    # 휴지통 이동(영구 삭제 대체)
pytest        # 테스트(dev)
pyinstaller   # EXE 빌드(선택)
```

> 참고: jinja2/markdown/rich/click/plotly/watchdog 는 현재 미사용(표준 라이브러리 + 위 목록만 사용).

---

## Project Structure

실제 구현 구조(현재):

```text
DownloadOrganizer/
├─ src/
│  └─ download_organizer/
│     ├─ __init__.py
│     ├─ config.py        # 분류 규칙·차단 경로·설정 파일 로드
│     ├─ models.py        # FileRecord/MovePlanItem/CleanPlanItem 등 데이터클래스
│     ├─ analyzer.py      # 스캔(재귀 옵션)·분류·중복 탐지(strict/fast)
│     ├─ organizer.py     # 이동 계획/실행(토큰)·되돌리기·빈폴더 정리 진입
│     ├─ cleaner.py       # 휴지통 정리(send2trash)·빈 폴더 정리
│     ├─ bookmarks.py     # Chrome/Edge 북마크 분석·마스킹
│     ├─ reports.py       # Markdown/HTML/Excel 보고서
│     ├─ safety.py        # 시스템 경로 차단·스캔폴더 내부 검증
│     ├─ logging_utils.py # 로깅
│     ├─ service.py       # build_preview/run_organizer/run_clean 오케스트레이션
│     └─ cli.py           # analyze/apply/undo/clean/init-config
├─ tests/                 # pytest 57개 (분류·중복·이동/되돌리기·토큰·휴지통 등)
├─ docs/                  # GitHub Pages 정적 소개 페이지
├─ benchmarks/            # fast/strict 성능 측정
├─ demo_downloads/        # 합성 데모 데이터
├─ streamlit_app.py       # 웹 UI (저장소 루트)
├─ pyinstaller_entry.py   # EXE 진입점
├─ build_exe.ps1          # EXE 빌드 스크립트
├─ requirements.txt / pyproject.toml
├─ render.yaml / Procfile / .streamlit/config.toml   # 배포
├─ .env.example / .gitignore
├─ README.md / 실행방법.md / DEPLOY.md / RELEASE_NOTES.md
└─ AGENTS.md

# 실행 시 생성: workspace/{organized_files, reports, history, logs}
```

---

## Role Instructions

> 아래 역할/프롬프트와 일부 모듈명(scanner.py·classifier.py·web_app.py 등)은 **기획 단계의 작업 지시 기록**입니다.
> 실제 구현 구조·동작은 위의 **"구현 현황"** 과 **Project Structure** 를 참고하세요.

## 1. Sisyphus - Ultraworker

### Role

Sisyphus는 실제 코드를 구현하는 주 작업자이다.

### Responsibilities

- Python 프로젝트 구조 생성
- 다운로드 폴더 스캔 기능 구현
- 파일 분류 로직 구현
- Dry-run 미리보기 구현
- 실제 파일 이동 기능 구현
- 이동 이력 저장 기능 구현
- 되돌리기 기능 구현
- 중복파일 탐지 구현
- 오래된 파일 탐지 구현
- Chrome/Edge 북마크 분석 구현
- Markdown/HTML/Excel 보고서 생성 구현
- CLI 실행 기능 구현
- Streamlit 웹 UI 구현
- 테스트 코드 작성
- README 작성

### Implementation Prompt

```text
너는 Sisyphus - Ultraworker 역할이다.

DownloadOrganizer 프로그램을 실제로 구현해줘.

목표:
다운로드 폴더를 분석하고 파일을 체계적으로 분류하며, 정리 결과를 문서화하는 Python 프로그램을 만든다. 또한 Chrome/Edge 브라우저 북마크를 분석하여 북마크 정리 보고서를 생성한다.

기술스택:
- Python 3.11+
- Streamlit
- pandas
- openpyxl
- jinja2
- markdown
- pytest
- pyinstaller

필수 구현:
1. 다운로드 폴더 스캔
2. 확장자 기반 파일 분류
3. 날짜, 용량, 중복 여부 분석
4. 정리 전 Dry-run 미리보기
5. 사용자 승인 후 실제 파일 이동
6. 이동 이력 JSON 저장
7. 되돌리기 기능
8. Chrome/Edge 북마크 JSON 파일 읽기
9. 북마크 도메인별 분류
10. 북마크 중복 URL 탐지
11. Markdown/HTML/Excel 보고서 생성
12. Streamlit 웹 UI
13. CLI 실행 명령
14. 테스트 코드
15. README 작성

중요 원칙:
- 원본 파일 삭제 금지
- 중복파일 자동 삭제 금지
- Dry-run 기본값 true
- 사용자 확인 없이 파일 이동 금지
- 시스템 폴더 접근 제한
- Windows 한글 경로 지원
- 오류 발생 시 logs 폴더에 기록
- 파일명 충돌 시 덮어쓰기 금지
```

---

## 2. Hephaestus - Deep Agent

### Role

Hephaestus는 품질, 보안, 안정성, 사용자 안전성을 검토하는 심층 검토자이다.

### Responsibilities

- 데이터 손실 위험 검토
- 파일 이동 로직 검토
- 되돌리기 기능 검토
- 경로 보안 검토
- 시스템 폴더 접근 제한 검토
- 브라우저 북마크 개인정보 노출 가능성 검토
- 보고서 민감정보 포함 여부 검토
- 대용량 폴더 처리 성능 검토
- 오류 처리 및 로그 검토
- 테스트 보완

### Review Prompt

```text
너는 Hephaestus - Deep Agent 역할이다.

DownloadOrganizer의 품질, 보안, 안정성, 사용자 안전성을 검토해줘.

검토 항목:
1. 파일 이동 중 데이터 손실 가능성
2. Dry-run 기본 적용 여부
3. 사용자 승인 없이 실제 이동되는 코드가 있는지 여부
4. 되돌리기 기능 정상 동작 여부
5. 시스템 폴더 접근 제한 여부
6. 중복파일 자동삭제 금지 여부
7. 파일명 충돌 시 덮어쓰기 방지 여부
8. 북마크 개인정보 노출 가능성
9. 보고서에 민감정보가 과도하게 포함되는지 여부
10. Windows 한글 경로 처리
11. 대용량 다운로드 폴더 처리 성능
12. Streamlit 웹 버전의 경로 입력 보안
13. 예외 발생 시 로그 기록
14. README의 주의사항 충분성
15. 테스트 코드의 핵심 시나리오 포함 여부

문제가 있으면 수정안을 제시하고 직접 보완해줘.
최종적으로 안전하게 배포 가능한 MVP인지 판단해줘.
```

---

## 3. Prometheus - Plan Builder

### Role

Prometheus는 전체 설계와 구현 계획을 수립하는 기획자이다.

### Responsibilities

- 전체 아키텍처 설계
- 기능 범위 정의
- MVP와 확장 기능 구분
- 데이터 흐름 설계
- 파일 분류 규칙 설계
- 북마크 분석 규칙 설계
- 보고서 구성 설계
- 안전정책 설계
- 구현 순서 제시

### Planning Prompt

```text
너는 Prometheus - Plan Builder 역할이다.

DownloadOrganizer 프로그램의 전체 설계와 구현 계획을 수립해줘.

목표:
다운로드 폴더와 브라우저 북마크를 체계적으로 정리하고, 정리 결과를 문서화하는 Python 프로그램을 설계한다.

구현 형태:
1. Python 단독 실행 CLI 버전
2. Streamlit 기반 웹 버전
3. 추후 PyInstaller EXE 패키징 가능 구조

핵심 기능:
- 다운로드 폴더 파일 분석
- 파일 확장자, 유형, 날짜, 용량 기준 자동 분류
- 정리 전 미리보기
- Dry-run 모드
- 실제 파일 이동
- 이동 이력 로그 저장
- 되돌리기 기능
- 중복파일 탐지
- 오래된 파일 탐지
- 정리 결과 Markdown/HTML/Excel 문서 생성
- Chrome, Edge 북마크 분석
- 북마크 도메인별/카테고리별 분류
- 북마크 중복 URL 탐지
- 북마크 정리 보고서 생성

다음 내용을 상세히 설계해줘:
1. 전체 아키텍처
2. 프로젝트 폴더 구조
3. 주요 모듈 역할
4. 데이터 흐름
5. 파일 분류 규칙
6. 북마크 분류 규칙
7. 보고서 항목
8. 안전정책
9. MVP 범위
10. 확장 기능
11. 구현 순서
12. 테스트 전략
```

---

## 4. Atlas - Plan Executor

### Role

Atlas는 Prometheus가 수립한 계획을 실제 작업 단위로 분해하고 실행 순서를 관리하는 역할이다.

### Responsibilities

- 작업 단위 분해
- 파일 생성 순서 관리
- 단계별 구현 확인
- 테스트 실행 관리
- 누락 기능 점검
- 최종 산출물 확인

### Execution Prompt

```text
너는 Atlas - Plan Executor 역할이다.

Prometheus가 설계한 DownloadOrganizer 계획을 실제 작업 단위로 분해하고 단계별로 실행해줘.

작업 순서:
1. 프로젝트 폴더 구조 생성
2. pyproject.toml 또는 requirements.txt 작성
3. Python 패키지 구조 생성
4. 설정 파일 작성
5. 파일 분석 모듈 scanner.py 구현
6. 분류 규칙 모듈 classifier.py 구현
7. 중복 탐지 모듈 duplicate.py 구현
8. 파일 이동 모듈 organizer.py 구현
9. 이동 이력 모듈 history.py 구현
10. 안전 검증 모듈 safety.py 구현
11. 북마크 분석 모듈 bookmark.py 구현
12. 보고서 생성 모듈 reporter.py 구현
13. CLI 실행 파일 cli.py 구현
14. Streamlit 웹 화면 web_app.py 구현
15. 테스트 코드 작성
16. README 작성
17. PyInstaller 빌드 안내 작성
18. 전체 기능 테스트
19. 최종 누락 항목 점검

각 단계마다 다음을 명확히 알려줘:
- 생성 또는 수정할 파일명
- 구현할 함수 또는 클래스
- 입력값과 출력값
- 테스트 방법
- 완료 기준
```

---

## MVP Scope

MVP에서는 다음 기능을 반드시 구현한다.

```text
1. 다운로드 폴더 선택
2. 파일 목록 스캔
3. 확장자 기반 분류
4. Dry-run 미리보기
5. 사용자 승인 후 파일 이동
6. 이동 이력 저장
7. 되돌리기 기능
8. 중복파일 탐지
9. 오래된 파일 탐지
10. Chrome/Edge 북마크 분석
11. Markdown/HTML/Excel 보고서 생성
12. CLI 실행
13. Streamlit 웹 실행
```

---

## Future Enhancements

향후 확장 기능은 다음과 같다.

```text
1. AI 기반 파일명 자동 요약
2. AI 기반 업무/개인/학습 파일 분류
3. OCR 기반 이미지/PDF 내용 분석
4. 중복파일 시각 비교
5. 예약 정리 기능
6. OneDrive/Google Drive 폴더 지원
7. Whale/Firefox 북마크 지원
8. 북마크 접속 가능 여부 검사
9. 태그 기반 정리 기능
10. 조직 표준 폴더 템플릿 적용
```

---

## Safety Rules

이 프로젝트에서 가장 중요한 것은 사용자 파일 보호이다.

반드시 다음 규칙을 준수한다.

```text
1. 기본 실행은 Dry-run이다.
2. 사용자 확인 없이 파일을 이동하지 않는다.
3. 원본 파일을 삭제하지 않는다.
4. 중복파일을 자동 삭제하지 않는다.
5. 시스템 폴더는 정리 대상에서 제외한다.
6. 파일명 충돌 시 덮어쓰지 않는다.
7. 모든 이동 작업은 history 파일에 기록한다.
8. 되돌리기 기능을 제공한다.
9. 오류 발생 시 로그를 남긴다.
10. 북마크 보고서에는 민감한 정보가 포함될 수 있음을 README에 명시한다.
```

---

## System Folder Protection

다음 경로는 기본적으로 정리 대상에서 제외한다.

```text
C:/Windows
C:/Program Files
C:/Program Files (x86)
C:/ProgramData
C:/Users/*/AppData
C:/Users/*/Desktop
C:/Users/*/Documents
```

설정 파일(config.json)의 `extra_blocked_roots` 로 차단 경로를 **추가**할 수 있으나 내장 차단은 제거 불가.
또한 실제 이동/삭제 직전, 모든 원본이 선택한 스캔 폴더 내부인지 한 번 더 검증한다(`ensure_source_within_scan_root`).

---

## Default Classification Rules

분류명(=정리 폴더명)은 **한글**이며 확장자 기준이다(소문자). 매칭 안 되면 **기타**.
(config.json `file_categories` 로 전체 교체 가능)

```text
문서:    .pdf, .doc, .docx, .hwp, .hwpx, .txt, .ppt, .pptx, .xls, .xlsx, .csv
이미지:  .jpg, .jpeg, .png, .gif, .bmp, .webp, .svg
동영상:  .mp4, .mkv, .avi, .mov, .wmv
오디오:  .mp3, .wav, .flac, .m4a
압축파일: .zip, .rar, .7z, .tar, .gz
실행파일: .exe, .msi, .bat, .cmd, .ps1
코드:    .py, .js, .ts, .java, .cpp, .c, .cs, .go, .rs, .ipynb
기타:    위에 없는 모든 확장자
```

옵션: `--ext-grouping`(분류/확장자/), `--date-grouping`(분류/연 또는 연-월/).
라우팅: `--route-old` → `오래된파일/`, `--route-duplicates` → `중복파일/`.

---

## Bookmark Category Rules

북마크는 도메인과 키워드를 기준으로 1차 분류한다.
(현재 웹 UI의 북마크 탭은 기본 숨김 — CLI/백엔드/보고서에서는 지원. `SHOW_BOOKMARK_TAB=True`로 표시)

```text
AI: openai, claude, anthropic, gemini, huggingface, perplexity, ollama
Development: github, gitlab, stackoverflow, npm, pypi, docker, nodejs, visualstudio, localhost
Public: go.kr, data.go.kr, g2b.go.kr, law.go.kr, juso.go.kr
News: news, newspaper, bbc, cnn
Shopping: coupang, gmarket, 11st, amazon, aliexpress
Education: coursera, edx, inflearn, class, lecture
Finance: bank, finance, stock, securities
Reference: wikipedia, docs, documentation
Etc: unmatched
```

---

## Report Output Names

보고서 파일명은 실행 시각을 포함한다.

```text
reports/download_organizer_report_YYYYMMDD_HHMMSS.md
reports/download_organizer_report_YYYYMMDD_HHMMSS.html
reports/download_organizer_report_YYYYMMDD_HHMMSS.xlsx
reports/bookmark_report_YYYYMMDD_HHMMSS.md
reports/bookmark_report_YYYYMMDD_HHMMSS.html
reports/bookmark_report_YYYYMMDD_HHMMSS.xlsx
```

---

## CLI Examples

실행은 analyze → apply → undo 3단계(+ clean, init-config). apply는 analyze가 출력한 토큰 필요.

```bash
download-organizer analyze --scan-root "C:/Users/me/Downloads"
download-organizer apply   --scan-root "C:/Users/me/Downloads" --confirm-code <TOKEN>
download-organizer undo    --history-file "workspace/history/move_history_YYYYMMDD_HHMMSS.json" --preview
download-organizer undo    --history-file "workspace/history/move_history_YYYYMMDD_HHMMSS.json"
download-organizer clean   --scan-root "C:/Users/me/Downloads" --trash-duplicates --confirm-code <TOKEN>
download-organizer init-config --path download_organizer.config.json

# 주요 옵션: --recursive/--no-recursive, --ext-grouping, --date-grouping year|month,
#            --dup-mode strict|fast, --include-category/--exclude-category,
#            --route-old, --route-duplicates, --remove-empty-dirs, --no-bookmarks, --config
```

---

## Streamlit Run Example

```bash
streamlit run streamlit_app.py
```

---

## PyInstaller Build Example

```powershell
.\build_exe.ps1            # dist\download-organizer.exe (내부적으로 pyinstaller_entry.py 사용)
```

---

## README Requirements

README.md에는 반드시 다음 내용을 포함한다.

```text
1. 프로그램 소개
2. 주요 기능
3. 설치 방법
4. CLI 실행 방법
5. Streamlit 웹 실행 방법
6. 보고서 생성 위치
7. 되돌리기 방법
8. Chrome/Edge 북마크 경로 안내
9. 안전 주의사항
10. 알려진 제한사항
11. 향후 개선 계획
```

---

## Final Acceptance Criteria

최종 완료 기준은 다음과 같다.

```text
1. 다운로드 폴더 스캔이 정상 동작한다.
2. Dry-run 미리보기가 정상 동작한다.
3. 사용자 승인 후 파일 이동이 정상 동작한다.
4. 이동 이력이 JSON으로 저장된다.
5. 되돌리기가 정상 동작한다.
6. 중복파일 탐지가 동작한다.
7. 오래된 파일 탐지가 동작한다.
8. Chrome/Edge 북마크 분석이 동작한다.
9. Markdown/HTML/Excel 보고서가 생성된다.
10. CLI 실행이 가능하다.
11. Streamlit 웹 실행이 가능하다.
12. 테스트 코드가 포함된다.
13. README가 충분히 작성된다.
14. 사용자 파일을 삭제하는 코드가 없다.
15. API Key나 민감정보를 요구하지 않는다.
```
