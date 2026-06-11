# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnusedCallResult=false, reportAny=false
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str((Path(__file__).resolve().parent / "src").resolve()))

from download_organizer.config import (
    apply_user_config,
    default_download_path,
    default_workspace,
    reset_user_config,
)
from download_organizer.logging_utils import setup_logger
from download_organizer.cleaner import compute_clean_token
from download_organizer.models import CleanPlanItem
from download_organizer.organizer import compute_plan_token, preview_undo, undo_move
from download_organizer.service import ConfirmationError, Preview, build_preview, run_clean, run_organizer

setup_logger(default_workspace() / "logs" / "download_organizer.log")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} TB"


def friendly_error(exc: Exception) -> str:
    """예외를 사용자 친화적인 한글 안내로 변환."""
    msg = str(exc)
    if "Blocked system path" in msg:
        return ("이 폴더는 보호 경로(Windows·Program Files·AppData·Desktop·Documents 등)라 "
                "정리할 수 없습니다. 다운로드 폴더처럼 안전한 폴더를 지정하세요.")
    if isinstance(exc, FileNotFoundError) or "find the path" in msg.lower() or "no such" in msg.lower():
        return "경로가 존재하지 않습니다. 스캔/출력 경로를 확인하세요."
    if isinstance(exc, NotADirectoryError):
        return "지정한 경로가 폴더가 아닙니다."
    if isinstance(exc, PermissionError):
        return "접근 권한이 없습니다. 다른 폴더를 선택하거나 권한을 확인하세요."
    return f"오류: {msg}"


def path_badge(path_str: str, must_be_dir: bool = True) -> str:
    """경로 존재 여부 배지 문자열."""
    try:
        p = Path(path_str)
        if p.exists() and (p.is_dir() or not must_be_dir):
            return "✅ 존재함"
        if p.exists():
            return "⚠️ 폴더가 아님"
        return "❌ 경로 없음"
    except OSError:
        return "❓ 확인 불가"


# 화면 표시용 한글 라벨 (폴더명/내부 키는 영문 유지 — 이동 동작·토큰 안전).
CATEGORY_KO: dict[str, str] = {
    "documents": "문서",
    "images": "이미지",
    "videos": "동영상",
    "audio": "오디오",
    "archives": "압축파일",
    "executables": "실행파일",
    "code": "코드",
    "others": "기타",
    "_old_files": "오래된 파일",
    "_duplicates": "중복 파일",
}

BOOKMARK_CATEGORY_KO: dict[str, str] = {
    "AI": "AI",
    "Development": "개발",
    "Public": "공공",
    "News": "뉴스",
    "Shopping": "쇼핑",
    "Education": "교육",
    "Finance": "금융",
    "Reference": "참고자료",
    "Etc": "기타",
}

BOOKMARK_COLUMNS_KO: dict[str, str] = {
    "browser": "브라우저",
    "folder": "폴더",
    "name": "이름",
    "url": "URL",
    "domain": "도메인",
    "category": "카테고리",
}


def ko_category(name: str) -> str:
    return CATEGORY_KO.get(name, name)


def ko_bookmark_category(name: str) -> str:
    return BOOKMARK_CATEGORY_KO.get(name, name)


UNDO_REASON_KO: dict[str, str] = {
    "original location occupied": "원위치에 동일 이름 파일 존재",
    "moved file no longer exists": "이동된 파일이 없음",
}


def undo_rows_ko(rows: list[dict]) -> pd.DataFrame:
    """Undo 행(src/dst/reason)을 한글 컬럼/사유로 표시용 변환."""
    out = []
    for r in rows:
        row = {"원위치": r.get("src", ""), "현재 위치": r.get("dst", "")}
        if "reason" in r:
            row["사유"] = UNDO_REASON_KO.get(r["reason"], r["reason"])
        out.append(row)
    return pd.DataFrame(out)


def history_files(output_root: Path) -> list[Path]:
    history_dir = output_root / "history"
    if not history_dir.exists():
        return []
    return sorted(history_dir.glob("move_history_*.json"), reverse=True)


def history_label(path: Path) -> str:
    """이력 파일을 '2026-06-11 17:36 · 이동 4건' 형태의 읽기 쉬운 라벨로."""
    label = path.stem.replace("move_history_", "")
    try:
        dt = datetime.strptime(label, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        dt = label
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = len(data.get("moved", []))
        return f"{dt}  ·  이동 {count}건"
    except (OSError, ValueError):
        return dt


def paginated_dataframe(df: pd.DataFrame, key: str, default_size: int = 20) -> None:
    """Render a dataframe with simple page-size + page-number controls."""
    total = len(df)
    c1, c2, c3 = st.columns([1, 2, 2])
    page_size = c1.selectbox("페이지당 행", [10, 20, 50, 100], index=[10, 20, 50, 100].index(default_size),
                             key=f"{key}_size")
    pages = max(1, (total + page_size - 1) // page_size)
    page = c2.number_input("페이지", min_value=1, max_value=pages, value=1, step=1, key=f"{key}_page")
    start = (int(page) - 1) * page_size
    end = min(start + page_size, total)
    c3.caption(f"{total:,}건 중 {start + 1:,}–{end:,} (페이지 {int(page)}/{pages})")
    st.dataframe(df.iloc[start:end], use_container_width=True, hide_index=True)


def make_progress(label: str):
    """진행률 표시줄과 콜백을 생성한다. 콜백은 (done, total, path) 형태."""
    bar = st.progress(0.0, text=f"{label} 준비 중...")

    def cb(done: int, total: int, path: str) -> None:
        frac = done / total if total else 1.0
        bar.progress(frac, text=f"{label} {done}/{total} — {Path(path).name}")

    return bar, cb


def _trash_confirm_and_run(selected: list[str], size_map: dict[str, int], params: dict, key: str) -> None:
    """선택된 경로 집합에 대한 토큰 확인 + 휴지통 이동 실행(공통)."""
    if not selected:
        st.caption("삭제할 파일의 체크박스를 선택하세요.")
        return
    token = compute_clean_token(
        [CleanPlanItem(path=Path(p), reason="selected", size=size_map[p]) for p in selected]
    )
    st.info(f"선택 **{len(selected)}건**  ·  휴지통으로 이동(복구 가능)")
    st.caption("아래 토큰을 복사해 입력하세요(오삭제 방지).")
    st.code(token, language=None)  # 복사 아이콘 제공
    ack = st.checkbox("선택한 파일을 휴지통으로 보냅니다.", key=f"{key}_ack")
    typed = st.text_input("확인 토큰 입력", placeholder=token, key=f"{key}_tok")
    sel_set = set(selected)
    if st.button("🗑️ 선택 휴지통으로", type="primary",
                 disabled=not (ack and typed.strip() == token), key=f"{key}_btn"):
        try:
            bar, cb = make_progress("휴지통 이동")
            res = run_clean(
                dry_run=False, confirm_code=typed.strip(),
                select=lambda r: str(r.path) in sel_set,
                protect_duplicate_groups=True,
                progress=cb,
                **clean_kwargs(params),
            )
            bar.empty()
            if res.failure_count:
                msg = f"휴지통으로 이동: {res.trashed_count}건 / 실패 {res.failure_count}건"
            else:
                msg = f"🗑️ 휴지통으로 이동 완료: {res.trashed_count}건 (복구는 Windows 휴지통에서)"
            st.session_state["last_action"] = msg
            st.session_state.pop("preview", None)  # scan now stale
            st.rerun()
        except ConfirmationError as exc:
            st.error(f"확인 차단: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"정리 실패 — {friendly_error(exc)}")


def trash_groups_ui(groups, params: dict, key: str) -> None:
    """중복 그룹별로 체크박스(전체 경로 표시) 선택 → 하단에서 한 번에 휴지통 이동.
    한 그룹의 모든 사본을 고르면 그 그룹은 제외하고 경고한다(최소 1개 보존)."""
    size_map: dict[str, int] = {}
    selected: list[str] = []
    for idx, group in enumerate(groups, start=1):
        for g in group:
            size_map[str(g.path)] = g.size
        with st.expander(f"그룹 {idx} — {len(group)}개 파일 ({human_size(group[0].size)})", expanded=True):
            df = pd.DataFrame([{"삭제": False, "경로": str(g.path), "크기": human_size(g.size)} for g in group])
            edited = st.data_editor(
                df, key=f"{key}_ed_{idx}", hide_index=True, use_container_width=True,
                column_config={
                    "삭제": st.column_config.CheckboxColumn("삭제", help="휴지통으로 보낼 사본 선택"),
                    "경로": st.column_config.TextColumn("경로", disabled=True, width="large"),
                    "크기": st.column_config.TextColumn("크기", disabled=True),
                },
            )
            picked = [str(r["경로"]) for _, r in edited.iterrows() if bool(r.get("삭제", False))]
            if picked and len(picked) == len(group):
                st.error(f"⚠️ 그룹 {idx}: 모든 사본을 선택했습니다. 최소 1개는 남겨주세요(이 그룹은 제외됩니다).")
            else:
                selected.extend(picked)
    st.divider()
    _trash_confirm_and_run(selected, size_map, params, key)


def trash_table_ui(records, params: dict, key: str) -> None:
    """단일 체크박스 표(전체 경로 표시) 선택 → 하단에서 한 번에 휴지통 이동(그룹 없음)."""
    size_map = {str(r.path): r.size for r in records}
    bcol1, bcol2, _bsp = st.columns([1, 1, 4])
    if bcol1.button("전체 선택", key=f"{key}_all_on", use_container_width=True):
        st.session_state[f"{key}_default"] = True
        st.session_state[f"{key}_rev"] = st.session_state.get(f"{key}_rev", 0) + 1
    if bcol2.button("전체 해제", key=f"{key}_all_off", use_container_width=True):
        st.session_state[f"{key}_default"] = False
        st.session_state[f"{key}_rev"] = st.session_state.get(f"{key}_rev", 0) + 1
    default = st.session_state.get(f"{key}_default", False)
    rev = st.session_state.get(f"{key}_rev", 0)

    df = pd.DataFrame(
        [
            {
                "삭제": default,
                "파일": r.path.name,
                "분류": ko_category(r.category),
                "크기": human_size(r.size),
                "수정일": pd.to_datetime(r.modified_ts, unit="s").strftime("%Y-%m-%d"),
                "경로": str(r.path),
            }
            for r in sorted(records, key=lambda r: r.modified_ts)
        ]
    )
    edited = st.data_editor(
        df, key=f"{key}_ed_{rev}", hide_index=True, use_container_width=True,
        column_config={
            "삭제": st.column_config.CheckboxColumn("삭제", help="휴지통으로 보낼 파일 선택"),
            "파일": st.column_config.TextColumn("파일", disabled=True),
            "분류": st.column_config.TextColumn("분류", disabled=True),
            "크기": st.column_config.TextColumn("크기", disabled=True),
            "수정일": st.column_config.TextColumn("수정일", disabled=True),
            "경로": st.column_config.TextColumn("경로", disabled=True, width="large"),
        },
    )
    selected = [str(r["경로"]) for _, r in edited.iterrows() if bool(r.get("삭제", False))]
    st.divider()
    _trash_confirm_and_run(selected, size_map, params, key)


def clean_kwargs(params: dict) -> dict:
    return {
        "scan_root": Path(params["scan_root"]),
        "output_root": Path(params["output_root"]),
        "old_days": params["old_days"],
        "dup_mode": params["dup_mode"],
        "recursive": params["recursive"],
        "exclude_dirs": params["exclude_dirs"],
    }


def run_kwargs(params: dict) -> dict:
    return {
        "scan_root": Path(params["scan_root"]),
        "output_root": Path(params["output_root"]),
        "old_days": params["old_days"],
        "include_bookmarks": params["include_bookmarks"],
        "dup_mode": params["dup_mode"],
        "mask_query": params["mask_query"],
        "exclude_domains": params["exclude_domains"],
        "recursive": params["recursive"],
        "exclude_dirs": params["exclude_dirs"],
        "date_grouping": params["date_grouping"],
        "ext_grouping": params["ext_grouping"],
        "route_old": params["route_old"],
        "route_duplicates": params["route_duplicates"],
        "remove_empty_dirs": params["remove_empty_dirs"],
    }


# --------------------------------------------------------------------------- #
# Page setup
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Download 폴더 관리자", page_icon="🗂️", layout="wide")

st.markdown(
    """
    <style>
      /* 테마 변수 기반 — 라이트/다크 모드 모두 자연스럽게 */
      .stMetric { background: var(--secondary-background-color);
                  border: 1px solid rgba(128,128,128,0.25); border-radius: 12px; padding: 12px 16px; }
      div[data-testid="stMetricValue"] { font-size: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🗂️ Download 폴더 관리자")
st.caption("기본은 **미리보기(Dry-run)** 입니다. 명시적으로 확인하기 전에는 어떤 파일도 이동하지 않습니다.")

# --- UI 탭 표시 토글 (다시 켜려면 True) ---
SHOW_BOOKMARK_TAB = False   # 북마크 기능 미사용 → 탭/옵션/지표/분석 모두 숨김
SHOW_CLEAN_TAB = False      # 일괄 휴지통 정리 탭(중복/오래된 탭에서 개별 정리 가능하므로 기본 숨김)

# --------------------------------------------------------------------------- #
# Sidebar — settings
# --------------------------------------------------------------------------- #
DEMO_DIR = Path(__file__).resolve().parent / "demo_downloads"


def _default_scan_root() -> str:
    """온라인 데모(또는 Downloads 폴더가 없을 때)는 샘플 폴더를 기본값으로."""
    downloads = default_download_path()
    if os.environ.get("DEMO_MODE") or (not downloads.exists() and DEMO_DIR.exists()):
        return str(DEMO_DIR)
    return str(downloads)


with st.sidebar:
    st.header("⚙️ 설정")
    if "scan_root_input" not in st.session_state:
        st.session_state["scan_root_input"] = _default_scan_root()
    scan_root = st.text_input("스캔 경로", key="scan_root_input", help="정리할 다운로드 폴더 경로")
    st.caption(f"스캔: {path_badge(scan_root)}")
    if DEMO_DIR.exists():
        st.button("📁 데모 샘플 폴더 사용", use_container_width=True,
                  help="합성 샘플(demo_downloads)로 기능을 안전하게 체험",
                  on_click=lambda: st.session_state.update(scan_root_input=str(DEMO_DIR)))
    output_root = st.text_input("출력 경로", value=str(default_workspace()),
                                help="보고서·이동 결과·이력·로그가 저장될 폴더")

    with st.expander("📂 정리 옵션", expanded=True):
        old_days = st.number_input("오래된 파일 기준 (일)", min_value=1, max_value=3650, value=180,
                                   help="이 일수 이상 수정되지 않은 파일을 '오래된 파일'로 표시")
        recursive = st.checkbox("하위폴더까지 검색 (재귀)", value=True,
                                help="하위폴더도 검색(기본 켜짐). 이미 정리된 분류 폴더는 자동 제외. 끄면 최상위만.")
        exclude_dirs_text = st.text_input("재귀 시 제외할 폴더명 (쉼표 구분)", value="",
                                          placeholder="node_modules, .git", disabled=not recursive,
                                          help="재귀 검색에서 건너뛸 폴더 이름")
        remove_empty_dirs = st.checkbox("이동 후 빈 폴더 정리 (휴지통)", value=False,
                                        help="재귀 정리로 비게 된 하위폴더를 휴지통으로 보냅니다(복구 가능, 빈 폴더만).")
        dup_mode = st.radio("중복 탐지 모드", options=["strict", "fast"], horizontal=True,
                            format_func=lambda x: {"strict": "정확(strict)", "fast": "빠름(fast)"}[x],
                            help="정확=전체 해시, 빠름=앞 1MB 해시(대용량에 빠르나 과다검출 가능)")
        ext_grouping = st.checkbox("확장자별 하위 분류", value=False,
                                   help="분류 폴더 아래 확장자 폴더를 추가. 예: 문서/pdf/, 이미지/png/")
        date_grouping = st.selectbox("날짜별 하위 분류", options=["none", "year", "month"],
                                     format_func=lambda x: {"none": "안 함", "year": "연도(YYYY)",
                                                            "month": "연·월(YYYY-MM)"}[x],
                                     help="분류(및 확장자) 폴더 아래 수정일 기준 하위 폴더. 예: 문서/2025/")
        route_old = st.checkbox("오래된 파일을 '오래된파일' 폴더로 분리", value=False)
        route_duplicates = st.checkbox("중복 파일을 '중복파일' 폴더로 분리", value=False,
                                       help="삭제하지 않고 검토용으로 한곳에 모읍니다.")

    if SHOW_BOOKMARK_TAB:
        with st.expander("🔖 북마크 옵션", expanded=False):
            include_bookmarks = st.checkbox("브라우저 북마크 분석 포함", value=True,
                                            help="Chrome/Edge 기본 프로필의 북마크를 읽습니다. 개인정보가 포함될 수 있습니다.")
            mask_query = st.checkbox("북마크 URL 쿼리 마스킹", value=True,
                                     help="보고서에서 ?뒤의 쿼리스트링/프래그먼트를 제거(토큰/ID 노출 방지).")
            exclude_text = st.text_input("북마크 제외 도메인 (쉼표 구분)", value="",
                                         placeholder="bank, mail.google.com",
                                         help="이 문자열이 도메인에 포함된 북마크는 분석에서 제외")
    else:
        include_bookmarks, mask_query, exclude_text = False, True, ""

    with st.expander("🛠️ 고급 (설정 파일)", expanded=False):
        config_path = st.text_input("설정 파일 경로 (선택)", value="",
                                    placeholder="download_organizer.config.json",
                                    help="분류 규칙·차단 경로 등을 덮어쓰는 config.json (비우면 기본값)")
        applied_cfg = st.session_state.get("applied_config")
        if applied_cfg:
            st.success(f"적용된 설정: {applied_cfg}")
            if st.button("↺ 기본 설정으로 초기화", use_container_width=True):
                reset_user_config()
                st.session_state.pop("applied_config", None)
                st.session_state.pop("preview", None)
                st.rerun()

    st.divider()
    analyze = st.button("🔍 분석 (미리보기)", type="primary", use_container_width=True)
    st.caption("분석은 파일을 읽기만 하며 이동하지 않습니다.")

# --------------------------------------------------------------------------- #
# Current settings (used both for analysis and stale-detection)
# --------------------------------------------------------------------------- #
current_settings = {
    "scan_root": scan_root,
    "output_root": output_root,
    "old_days": int(old_days),
    "include_bookmarks": include_bookmarks,
    "dup_mode": dup_mode,
    "mask_query": mask_query,
    "exclude_domains": [d.strip() for d in exclude_text.split(",") if d.strip()],
    "recursive": recursive,
    "exclude_dirs": [d.strip() for d in exclude_dirs_text.split(",") if d.strip()],
    "date_grouping": date_grouping,
    "ext_grouping": ext_grouping,
    "route_old": route_old,
    "route_duplicates": route_duplicates,
    "remove_empty_dirs": remove_empty_dirs,
}

# --------------------------------------------------------------------------- #
# Run analysis
# --------------------------------------------------------------------------- #
if analyze:
    try:
        if config_path.strip():
            apply_user_config(Path(config_path.strip()))
            st.session_state["applied_config"] = config_path.strip()
        with st.spinner("분석 중..."):
            preview = build_preview(
                scan_root=Path(scan_root),
                output_root=Path(output_root),
                old_days=current_settings["old_days"],
                include_bookmarks=include_bookmarks,
                dup_mode=dup_mode,
                mask_query=mask_query,
                exclude_domains=current_settings["exclude_domains"],
                recursive=recursive,
                exclude_dirs=current_settings["exclude_dirs"],
                date_grouping=date_grouping,
                ext_grouping=ext_grouping,
                route_old=route_old,
                route_duplicates=route_duplicates,
            )
        st.session_state["preview"] = preview
        st.session_state["params"] = dict(current_settings)
        st.session_state.pop("excluded_srcs", None)
        st.session_state.pop("apply_done", None)
        st.session_state.pop("last_action", None)
        st.session_state.pop("plan_default", None)
        st.session_state.pop("plan_rev", None)
    except Exception as exc:  # noqa: BLE001
        st.error(f"분석 실패 — {friendly_error(exc)}")

preview: Preview | None = st.session_state.get("preview")

if preview is None:
    last = st.session_state.get("last_action")
    if last:
        st.success(last)
        st.caption("폴더 내용이 바뀌었습니다. 최신 상태를 보려면 다시 분석하세요.")
    st.info("왼쪽 사이드바에서 경로를 확인하고 **분석 (미리보기)** 버튼을 눌러 시작하세요.")
    st.stop()

params = st.session_state["params"]

# 설정이 분석 이후 바뀌었으면 안내(재분석 유도)
if current_settings != params:
    st.warning("⚙️ 설정이 변경되었습니다. 결과에 반영하려면 사이드바의 **분석 (미리보기)** 를 다시 누르세요.")

# --------------------------------------------------------------------------- #
# Summary metrics
# --------------------------------------------------------------------------- #
total_size = sum(r.size for r in preview.records)
cols = st.columns(6 if SHOW_BOOKMARK_TAB else 5)
cols[0].metric("총 파일", f"{len(preview.records):,}")
cols[1].metric("총 용량", human_size(total_size))
cols[2].metric("이동 예정", f"{len(preview.plan):,}")
cols[3].metric("중복 그룹", f"{len(preview.duplicates):,}")
cols[4].metric("오래된 파일", f"{len(preview.old_files):,}")
if SHOW_BOOKMARK_TAB:
    cols[5].metric("북마크", f"{len(preview.bookmarks):,}")
st.caption(
    f"스캔 범위: {'하위폴더 포함(재귀)' if preview.recursive else '최상위 파일만'}"
    + ("  ·  정리 분류 폴더는 자동 제외됨" if preview.recursive else "")
)

_tab_labels = ["📊 요약", "📦 이동 미리보기", "♊ 중복", "🕰️ 오래된 파일"]
if SHOW_BOOKMARK_TAB:
    _tab_labels.append("🔖 북마크")
_tab_labels.append("🚀 실행 / 되돌리기")
if SHOW_CLEAN_TAB:
    _tab_labels.append("🗑️ 휴지통 정리")

_tabs = iter(st.tabs(_tab_labels))
tab_summary = next(_tabs)
tab_plan = next(_tabs)
tab_dups = next(_tabs)
tab_old = next(_tabs)
tab_bookmarks = next(_tabs) if SHOW_BOOKMARK_TAB else None
tab_run = next(_tabs)
tab_clean = next(_tabs) if SHOW_CLEAN_TAB else None

# --- 요약 ------------------------------------------------------------------- #
with tab_summary:
    if preview.summary:
        st.subheader("분류별 파일 수")
        sort_col1, sort_col2, sort_col3 = st.columns([2, 2, 2])
        sort_by = sort_col1.selectbox("정렬 기준", ["개수", "분류명"], index=0, key="summary_sort_by")
        sort_order = sort_col2.selectbox("정렬 방향", ["내림차순", "오름차순"], index=0, key="summary_sort_order")
        top_n = sort_col3.selectbox("표시 개수", ["전체", 5, 10, 20], index=0, key="summary_top_n")

        summary_rows = [{"분류": ko_category(category), "개수": count} for category, count in preview.summary.items()]
        sdf = pd.DataFrame(summary_rows)

        ascending = sort_order == "오름차순"
        if sort_by == "개수":
            sdf = sdf.sort_values(by="개수", ascending=ascending)
        else:
            sdf = sdf.sort_values(by="분류", ascending=ascending)

        if top_n != "전체":
            sdf = sdf.head(int(top_n))

        # Vega-Lite 스펙으로 직접 그려 선택한 정렬 순서를 x축에 그대로 반영
        # (st.bar_chart는 x축을 자체 재정렬함. altair 모듈 import도 불필요).
        st.vega_lite_chart(
            sdf,
            {
                "mark": {"type": "bar", "color": "#1f77b4"},
                "encoding": {
                    "x": {"field": "분류", "type": "nominal", "sort": sdf["분류"].tolist(),
                          "axis": {"labelAngle": 0}},
                    "y": {"field": "개수", "type": "quantitative"},
                    "tooltip": [{"field": "분류"}, {"field": "개수"}],
                },
            },
            use_container_width=True,
        )
        st.dataframe(sdf, use_container_width=True, hide_index=True)
    else:
        st.info("스캔된 파일이 없습니다.")

# --- 이동 미리보기 ---------------------------------------------------------- #
with tab_plan:
    st.subheader("이동 예정 목록")
    st.caption("**이동** 칸이 체크된 파일만 이동합니다. 빼려면 체크 해제하세요. "
               "동일 이름은 자동으로 안전한 이름(_1, _2…)이 붙습니다.")
    if not preview.plan:
        st.info("이동할 파일이 없습니다.")
    else:
        bcol1, bcol2, _bsp = st.columns([1, 1, 4])
        if bcol1.button("전체 이동", key="plan_all_on", use_container_width=True):
            st.session_state["plan_default"] = True
            st.session_state["plan_rev"] = st.session_state.get("plan_rev", 0) + 1
        if bcol2.button("전체 제외", key="plan_all_off", use_container_width=True):
            st.session_state["plan_default"] = False
            st.session_state["plan_rev"] = st.session_state.get("plan_rev", 0) + 1
        plan_default = st.session_state.get("plan_default", True)
        plan_rev = st.session_state.get("plan_rev", 0)

        old_paths = {r.path for r in preview.old_files}
        dup_paths = {r.path for group in preview.duplicates for r in group}
        rows = [
            {
                "이동": plan_default,
                "파일": p.src.name,
                "분류": ko_category(p.category),
                "이동 위치": str(p.dst),
                "중복": "✓" if p.src in dup_paths else "",
                "오래됨": "✓" if p.src in old_paths else "",
                "_src": str(p.src),
            }
            for p in preview.plan
        ]
        edited = st.data_editor(
            pd.DataFrame(rows),
            key=f"plan_editor_{preview.plan_token}_{plan_rev}",  # reset on new scan / bulk toggle
            hide_index=True, use_container_width=True, height=420,
            column_config={
                "이동": st.column_config.CheckboxColumn("이동", help="체크된 파일만 이동"),
                "파일": st.column_config.TextColumn("파일", disabled=True),
                "분류": st.column_config.TextColumn("분류", disabled=True),
                "이동 위치": st.column_config.TextColumn("이동 위치", disabled=True, width="large"),
                "중복": st.column_config.TextColumn("중복", disabled=True, width="small"),
                "오래됨": st.column_config.TextColumn("오래됨", disabled=True, width="small"),
                "_src": None,  # 식별용 숨김 컬럼
            },
        )
        excluded = [str(r["_src"]) for _, r in edited.iterrows() if not bool(r.get("이동", False))]
        st.session_state["excluded_srcs"] = excluded
        excluded_set = set(excluded)
        selected_items = [p for p in preview.plan if str(p.src) not in excluded_set]
        subset_token = compute_plan_token(selected_items)
        st.info(f"이동 선택 **{len(selected_items)} / {len(preview.plan)}**건  ·  확인 토큰: `{subset_token}`")
        st.download_button(
            "⬇️ 이동 계획 CSV 다운로드 (전체)",
            pd.DataFrame(rows).drop(columns=["_src"]).to_csv(index=False).encode("utf-8-sig"),
            file_name="move_plan.csv",
            mime="text/csv",
        )

# --- 중복 ------------------------------------------------------------------- #
with tab_dups:
    st.subheader("중복 후보 그룹")
    st.caption("⚠️ 중복 파일은 자동 삭제하지 않습니다. 직접 확인 후 판단하세요.")
    if not preview.duplicates:
        st.success("중복 후보가 없습니다.")
    else:
        st.caption("각 그룹에서 지울 사본의 **삭제** 칸을 체크하세요. 경로로 폴더를 구분할 수 있고, 그룹당 최소 1개는 남겨야 합니다.")
        trash_groups_ui(preview.duplicates, params, key="dup_trash")

# --- 오래된 파일 ------------------------------------------------------------ #
with tab_old:
    st.subheader(f"오래된 파일 후보 ({params['old_days']}일 이상 미수정)")
    if not preview.old_files:
        st.success("오래된 파일이 없습니다.")
    else:
        st.caption("지울 파일의 **삭제** 칸을 체크하세요. 경로로 폴더를 구분할 수 있으며, 휴지통(복구 가능)으로 이동합니다.")
        trash_table_ui(list(preview.old_files), params, key="old_trash")

# 북마크 탭은 현재 UX 요청에 따라 숨김 처리.

# --- 실행 / 되돌리기 -------------------------------------------------------- #
with tab_run:
    st.subheader("보고서 생성")
    st.caption("미리보기 결과를 Markdown / HTML / Excel 보고서로 저장합니다 (파일 이동 없음).")
    if st.button("📝 보고서 생성 (Dry-run)"):
        try:
            result = run_organizer(dry_run=True, confirm_move=False, **run_kwargs(params))
            st.session_state["reports"] = {
                "다운로드 보고서": result.download_reports,
                "북마크 보고서": result.bookmark_reports,
            }
            report_dir = Path(result.download_reports["md"]).parent
            st.success("보고서를 생성했습니다.")
            st.caption(f"저장 위치: `{report_dir}`")
        except Exception as exc:  # noqa: BLE001
            st.error(f"보고서 생성 실패 — {friendly_error(exc)}")

    reports = st.session_state.get("reports")
    if reports:
        mimes = {
            "md": "text/markdown",
            "html": "text/html",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        for label, paths in reports.items():
            if not paths:
                continue
            st.markdown(f"**{label}**")
            cols = st.columns(3)
            for col, key in zip(cols, ("md", "html", "xlsx")):
                path = Path(paths[key])
                if path.exists():
                    col.download_button(
                        f"⬇️ {key.upper()}",
                        path.read_bytes(),
                        file_name=path.name,
                        mime=mimes[key],
                        use_container_width=True,
                        key=f"dl_{label}_{key}",
                    )

    st.divider()

    # --- Actual move (guarded, 2-step, selective) -------------------------- #
    st.subheader("실제 파일 이동")
    st.warning("이 작업은 실제로 파일을 이동합니다. 이동 이력은 저장되며 되돌리기가 가능합니다.")
    excluded_set = set(st.session_state.get("excluded_srcs", []))
    selected_items = [p for p in preview.plan if str(p.src) not in excluded_set]
    subset_token = compute_plan_token(selected_items)
    st.caption(f"선택됨 **{len(selected_items)} / {len(preview.plan)}** 건 (제외는 '이동 미리보기' 탭에서 선택). "
               "아래 토큰을 복사해 입력해야 실행됩니다.")
    st.code(subset_token, language=None)  # 복사 아이콘 제공
    ack = st.checkbox(f"위 {len(selected_items)}건의 이동을 확인했습니다.")
    typed = st.text_input("확인 토큰 입력", placeholder=subset_token)
    can_apply = ack and typed.strip() == subset_token and len(selected_items) > 0
    if st.button("🚚 실제 이동 실행", type="primary", disabled=not can_apply):
        try:
            bar, cb = make_progress("이동")
            result = run_organizer(
                dry_run=False,
                confirm_move=True,
                confirm_code=typed.strip(),
                select=lambda i: str(i.src) not in excluded_set,
                progress=cb,
                **run_kwargs(params),
            )
            bar.empty()
            msg = f"🚚 이동 완료: {result.moved_count}건"
            if result.failure_count:
                msg += f" / 실패 {result.failure_count}건 (이력 파일 확인)"
            if result.empty_dirs_removed:
                msg += f" · 빈 폴더 {result.empty_dirs_removed}개 휴지통 정리"
            msg += f"\n\n이력 파일: {result.history_file}"
            st.session_state["last_action"] = msg
            st.session_state.pop("preview", None)  # plan is now stale
            st.rerun()
        except ConfirmationError as exc:
            st.error(f"확인 차단: {exc}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"이동 실패 — {friendly_error(exc)}")

    st.divider()

    # --- Undo --------------------------------------------------------------- #
    st.subheader("되돌리기")
    files = history_files(Path(params["output_root"]))
    options = [str(p) for p in files]
    selected = (
        st.selectbox("이력 파일 선택", options=options, format_func=lambda s: history_label(Path(s)))
        if options else None
    )
    manual = st.text_input("또는 이력 파일 경로 직접 입력", value=selected or "")
    col_prev, col_run = st.columns(2)
    if col_prev.button("🔍 되돌리기 미리보기", disabled=not manual.strip(), use_container_width=True):
        try:
            prev = preview_undo(Path(manual.strip()))
            st.info(f"복원 예정 **{len(prev.restorable)}건** / 건너뜀 **{len(prev.skipped)}건**")
            if prev.restorable:
                st.markdown("**복원 예정**")
                st.dataframe(undo_rows_ko(prev.restorable), use_container_width=True, hide_index=True)
            if prev.skipped:
                st.markdown("**건너뜀 (원위치 점유/대상 없음)**")
                st.dataframe(undo_rows_ko(prev.skipped), use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"미리보기 실패: {exc}")
    if col_run.button("↩️ 되돌리기 실행", disabled=not manual.strip(), type="primary", use_container_width=True):
        try:
            outcome = undo_move(Path(manual.strip()))
            st.success(f"복원 완료: {outcome.restored}건")
            if outcome.skipped:
                st.warning(f"건너뜀: {len(outcome.skipped)}건 (원위치 점유/대상 없음)")
                st.dataframe(undo_rows_ko(outcome.skipped), use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"되돌리기 실패: {exc}")

# --- 휴지통 정리 (기본 숨김, SHOW_CLEAN_TAB 로 토글) ------------------------- #
REASON_KO = {"duplicate": "중복 사본", "old": "오래된 파일", "selected": "선택 분류"}

if SHOW_CLEAN_TAB and tab_clean is not None:
  with tab_clean:
    st.subheader("휴지통 정리")
    st.warning("선택한 파일을 **휴지통(복구 가능)** 으로 보냅니다. 영구 삭제가 아니며, 잘못 보내도 휴지통에서 복원할 수 있습니다.")
    st.caption("대상은 스캔 폴더 내부로 제한되며, 중복은 그룹당 1개를 반드시 보존합니다.")

    cc1, cc2 = st.columns(2)
    trash_dups = cc1.checkbox("중복 사본 (그룹당 1개 보존)", value=False)
    trash_old = cc2.checkbox("오래된 파일", value=False)
    trash_cats = st.multiselect("이 분류의 파일을 휴지통으로",
                                options=sorted(preview.summary.keys()),
                                format_func=ko_category)

    if st.button("🔍 휴지통 정리 미리보기"):
        cats = set(trash_cats)
        try:
            res = run_clean(
                dry_run=True, trash_old=trash_old, trash_duplicates=trash_dups,
                select=(lambda r: r.category in cats) if cats else None,
                **clean_kwargs(params),
            )
            st.session_state["clean"] = {
                "token": res.plan_token,
                "by_reason": res.by_reason,
                "rows": [{"파일": Path(i.path).name, "사유": REASON_KO.get(i.reason, i.reason),
                          "크기": human_size(i.size), "경로": str(i.path)} for i in res.items],
                "targets": {"trash_old": trash_old, "trash_dups": trash_dups, "cats": list(cats)},
            }
        except Exception as exc:  # noqa: BLE001
            st.error(f"미리보기 실패: {exc}")

    clean = st.session_state.get("clean")
    if clean is not None:
        if not clean["rows"]:
            st.info("휴지통으로 보낼 대상이 없습니다. 위에서 대상을 선택하세요.")
        else:
            summary = " · ".join(f"{REASON_KO.get(k, k)} {v}건" for k, v in clean["by_reason"].items())
            st.info(f"대상 **{len(clean['rows'])}건** ({summary})  ·  확인 토큰: `{clean['token']}`")
            paginated_dataframe(pd.DataFrame(clean["rows"]), key="clean")

            ack = st.checkbox("위 파일들을 휴지통으로 보내는 것을 확인했습니다.")
            typed = st.text_input("확인 토큰 입력", placeholder=clean["token"], key="clean_token_in")
            can = ack and typed.strip() == clean["token"]
            if st.button("🗑️ 휴지통으로 보내기", type="primary", disabled=not can):
                t = clean["targets"]
                cats = set(t["cats"])
                try:
                    res = run_clean(
                        dry_run=False, confirm_code=typed.strip(),
                        trash_old=t["trash_old"], trash_duplicates=t["trash_dups"],
                        select=(lambda r: r.category in cats) if cats else None,
                        **clean_kwargs(params),
                    )
                    msg = f"휴지통으로 이동: {res.trashed_count}건 (복구는 휴지통에서)"
                    if res.failure_count:
                        st.warning(f"{msg} / 실패 {res.failure_count}건")
                    else:
                        st.success(msg)
                    st.info(f"이력 파일: {res.history_file}")
                    st.session_state.pop("clean", None)
                    st.session_state.pop("preview", None)  # scan now stale
                except ConfirmationError as exc:
                    st.error(f"확인 차단: {exc}")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"정리 실패: {exc}")
