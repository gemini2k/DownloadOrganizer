# DownloadOrganizer

다운로드 폴더를 안전하게 분석/분류하고, 정리 결과를 Markdown/HTML/Excel로 생성하는 Python 프로그램입니다.

## 포함 기능

- 다운로드 폴더 스캔 (기본 최상위, `--recursive`로 하위폴더까지)
- 파일 유형별 분류 + **확장자별/날짜별 하위 분류** 옵션 (예: `문서/pdf/2025/`)
- 정리 전 미리보기 (기본 dry-run)
- **3단계 실행**: `analyze`(미리보기·토큰 발급) → `apply`(계획 토큰 확인) → `undo`(되돌리기)
- **선택적 적용**: 파일/분류 단위로 일부만 이동
- 이동 이력 저장 + 되돌리기(+ `--preview`로 사전 확인)
- **휴지통 정리(`clean`)**: 중복 사본(그룹당 1개 보존)·오래된 파일·선택 분류를 **휴지통으로**(영구 삭제 아님, 복구 가능)
- 중복 파일 그룹 탐지 (`strict`/`fast` 모드, 자동 삭제 없음)
- 오래된 파일 탐지, 오래된/중복 파일 **분리 폴더 라우팅**(`_old_files`/`_duplicates`) 옵션
- Chrome/Edge 북마크 분석 (도메인/카테고리, URL 쿼리 마스킹·도메인 제외 옵션)
- 타임스탬프 Markdown/HTML/Excel 보고서 생성 (다운로드/북마크 분리)
- 사용자 **설정 파일(config.json)**: 분류 규칙·기준 일수·차단 경로·북마크 카테고리 override
- 운영 로깅(스캔/이동/실패/되돌리기)
- Streamlit 웹 UI (지표·탭·페이징·다운로드)
- PyInstaller EXE 빌드 스크립트(`build_exe.ps1`)

## 안전 원칙

- 기본값은 dry-run
- 사용자 확인 없이는 이동 금지
- **영구 삭제 금지** — 코드 어디에도 영구 삭제(`remove`/`unlink`/`rmtree`)가 없습니다. 정리는 `shutil.move`, 삭제는 `clean` 명령의 **휴지통 이동(`send2trash`, 복구 가능)** 만 사용합니다.
- 중복파일 자동삭제 금지(`clean`은 항상 그룹당 1개 보존, 기본 미리보기)
- **선택한 다운로드 폴더 밖의 파일은 절대 건드리지 않음** — 실제 이동 시 모든 원본이 스캔 폴더 내부인지 한 번 더 검증합니다(`ensure_source_within_scan_root`).
- 시스템/개인 경로 차단 (`C:\Windows`, `Program Files`, `ProgramData`, `AppData`, `Desktop`, `Documents`)
- 되돌리기 시 원위치에 동일 이름 파일이 있으면 덮어쓰지 않고 건너뜀
- 이동은 한 건씩 history에 기록되어, 중간에 실패해도 이미 이동된 파일을 되돌릴 수 있음

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## CLI 사용법

실행은 **analyze → apply → undo** 3단계로 분리됩니다.

**1) 분석 (미리보기, 파일 이동 없음).** 보고서를 생성하고 이 계획의 **확인 토큰**을 출력합니다.

```bash
download-organizer analyze --scan-root "C:\Users\USER\Downloads"
# ... "hint": "To move files: download-organizer apply --confirm-code <TOKEN>"
```

**2) 실제 이동.** analyze가 출력한 토큰을 `--confirm-code`로 넘겨야만 실행됩니다. 토큰이 없거나 틀리면 100% 차단됩니다. 또한 토큰은 *그 계획*에 묶여 있어, analyze 이후 폴더가 바뀌면 토큰이 달라져 오래된 계획이 실수로 적용되지 않습니다.

```bash
download-organizer apply --scan-root "C:\Users\USER\Downloads" --confirm-code <TOKEN>
```

**3) 되돌리기.** `--preview`로 무엇이 복원/건너뜀될지 먼저 확인할 수 있습니다(이동 없음).

```bash
download-organizer undo --history-file "workspace\history\move_history_YYYYMMDD_HHMMSS.json" --preview
download-organizer undo --history-file "workspace\history\move_history_YYYYMMDD_HHMMSS.json"
```

**(선택) 휴지통 정리.** 중복 사본/오래된 파일/특정 분류를 **휴지통(복구 가능)** 으로 보냅니다. analyze/apply와 동일하게 토큰 2단계 확인이며, `--confirm-code` 없이는 미리보기만 합니다. 영구 삭제는 하지 않습니다.

```bash
download-organizer clean --scan-root "C:\Users\USER\Downloads" --trash-duplicates          # 미리보기(토큰 출력)
download-organizer clean --scan-root "C:\Users\USER\Downloads" --trash-duplicates --confirm-code <TOKEN>
# 옵션: --trash-old, --trash-category 문서 (반복 가능)
```

주요 옵션 (analyze/apply 공통):

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--scan-root` | 정리할 다운로드 폴더 | 사용자 Downloads |
| `--output-root` | 보고서/이력 출력 폴더 | `.\workspace` |
| `--old-days` | 오래된 파일 기준(일) | `180` |
| `--dup-mode strict\|fast` | 중복 탐지: strict=전체 해시(정확), fast=앞 1MB(빠름, 과다검출 가능) | `strict` |
| `--recursive` / `--no-recursive` | 하위폴더까지 스캔(기본 on). 정리 분류 폴더는 자동 제외. 최상위만 하려면 `--no-recursive` | on |
| `--exclude-dir NAME` | 재귀 스캔 시 건너뛸 폴더명(반복 가능) | 없음 |
| `--ext-grouping` | 분류 폴더 아래 확장자 하위 폴더(예: `문서/pdf/`) | off |
| `--date-grouping none\|year\|month` | (확장자) 폴더 아래 수정일 기준 하위 폴더(예: `문서/pdf/2025/`) | `none` |
| `--include-category CAT` | 해당 분류만 이동(반복 가능). 미지정 시 전체 | 전체 |
| `--exclude-category CAT` | 해당 분류는 이동 제외(반복 가능) | 없음 |
| `--route-old` | 오래된 파일 후보를 `_old_files` 검토 폴더로 분리 | off |
| `--route-duplicates` | 중복 후보를 `_duplicates` 검토 폴더로 분리(삭제 아님) | off |
| `--no-bookmarks` | 북마크 분석 제외(개인정보 보호) | 포함 |

> **선택적 적용**: `analyze`와 `apply`에 동일한 `--include-category`/`--exclude-category`를 주면, 토큰이 *선택된 부분 집합* 기준으로 계산되어 그 부분만 안전하게 이동됩니다. 웹 UI에서는 "이동 미리보기" 탭에서 파일을 직접 제외할 수 있습니다.
| `--mask-bookmark-query` | 북마크 URL의 쿼리스트링/프래그먼트 제거 | off |
| `--exclude-domain DOMAIN` | 해당 문자열이 포함된 도메인 북마크 제외(반복 가능) | 없음 |

> `run` 명령은 deprecated 별칭으로 `analyze`와 동일하게 동작하며, `run --apply`는 차단되고 `apply`로 안내됩니다.

## 설정 파일 (config.json)

분류 규칙·오래된 파일 기준·추가 차단 경로·북마크 카테고리를 코드 수정 없이 바꿀 수 있습니다.

```bash
download-organizer init-config --path download_organizer.config.json   # 기본 설정 생성
download-organizer analyze --config download_organizer.config.json
```

config.json 키:

| 키 | 동작 |
|----|------|
| `old_days` | 오래된 파일 기준(일) |
| `file_categories` | `{ "분류명": [".확장자", ...] }` — 있으면 **전체 교체** |
| `bookmark_categories` | `{ "카테고리": ["키워드", ...] }` — 있으면 **전체 교체** |
| `extra_blocked_roots` | 차단 경로 **추가**(내장 차단 경로는 제거 불가 — 안전) |

> 명령행 옵션(`--old-days` 등)은 설정 파일보다 **우선**합니다. 웹 UI는 사이드바의 "설정 파일 경로"에 입력하면 적용됩니다.

## Streamlit 사용법

```bash
streamlit run streamlit_app.py
```

웹 UI는 사이드바에서 경로/기준/중복모드/북마크 마스킹·제외 도메인을 설정하고 **분석(미리보기)** 을 누르면, 요약 지표·이동 미리보기 표·중복/오래된 파일 목록·북마크 차트를 탭으로 보여줍니다. 보고서 다운로드와 되돌리기도 같은 화면에서 가능하며, 실제 이동은 **체크박스 + 계획 확인 토큰 입력**의 2단계 게이트를 거쳐야만 실행됩니다(CLI와 동일한 토큰).

## 테스트

```bash
pip install -e ".[dev]"
pytest -q
```

중복 탐지 fast/strict 성능 비교(합성 데이터, 실제 폴더 미접근):

```bash
python benchmarks/bench_dup_mode.py --count 30 --size-mb 20
```

## 출력 위치

- `workspace/reports/download_organizer_report_YYYYMMDD_HHMMSS.{md,html,xlsx}`
- `workspace/reports/bookmark_report_YYYYMMDD_HHMMSS.{md,html,xlsx}` (북마크 분석 시)
- `workspace/organized_files/_old_files/`, `workspace/organized_files/_duplicates/` (라우팅 옵션 사용 시)
- `workspace/history/move_history_*.json` (실제 이동 시)
- `workspace/history/trash_history_*.json` (휴지통 정리 시; 복구는 휴지통에서)
- `workspace/logs/download_organizer.log` (스캔/이동/실패/되돌리기/휴지통 정리 기록)

## PyInstaller EXE 빌드

CLI 단일 실행파일(`dist\download-organizer.exe`)을 빌드합니다(Streamlit 웹 UI는 서버 앱이라 EXE에 포함되지 않음):

```powershell
.\build_exe.ps1            # 빌드
.\build_exe.ps1 -Clean     # build/ dist/ 정리 후 빌드
```

내부적으로 `pyinstaller_entry.py`를 진입점으로 사용합니다(패키지 상대 임포트 때문에 cli.py를 직접 실행하지 않음).

## 주의사항

- 실행 전 반드시 대상 폴더를 확인하세요.
- `apply`(계획 토큰 입력) 시 실제 파일 이동이 일어납니다. 먼저 `analyze`로 미리보기하세요.
- 북마크 분석은 로컬 Chrome/Edge 기본 프로필 파일만 대상으로 합니다. 보고서에 개인 사이트 정보가 포함될 수 있으니 공유 시 `--mask-bookmark-query`/`--no-bookmarks`를 활용하세요.

## 알려진 제한사항

- Windows 경로(`C:\...`) 기준으로 설계되었습니다. 시스템/개인 폴더(`Windows`/`Program Files`/`AppData`/`Desktop`/`Documents`)는 스캔 대상에서 제외됩니다.
- 북마크는 Chrome/Edge 기본 프로필만 지원합니다(Whale/Firefox 미지원).
- 분류는 확장자 기준입니다(내용 기반 분석 없음).

## 향후 개선 계획

- 빈/0바이트·초대용량 파일 탐지 보고
- 북마크 링크 유효성(접속 가능 여부) 검사
- Whale/Firefox 북마크 지원
- 예약 정리(watch) 모드
