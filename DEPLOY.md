# 배포 가이드

## 0. 먼저 이해할 점 (중요)

이 도구는 **로컬 파일을 스캔·이동·휴지통 정리**하는 데스크톱형 앱입니다.

- **GitHub Pages** = 프로젝트 **소개용 정적 사이트**(앱 실행 X). → 이건 이 저장소에 포함됨.
- **Streamlit Community Cloud / Render / Railway** = 앱을 웹에서 띄울 수 있지만,
  그 경우 **"서버"의 파일**을 다루므로 방문자 PC의 다운로드 폴더는 정리할 수 없습니다.
  → 온라인은 **데모**로만 의미가 있고, **실제 사용은 각자 PC에서 로컬 실행**이 정석입니다.

---

## 1. 변경사항 푸시 (먼저)

> GitHub는 비밀번호 git 인증을 폐지했습니다. **Personal Access Token(PAT)** 또는 SSH가 필요합니다.
> 대화 등에 비밀번호가 노출됐다면 **즉시 변경**하세요.

```bash
git add -A
git commit -m "Add landing page (GitHub Pages) and deploy configs"
git push origin main
# 인증 창이 뜨면: Username=gemini2k, Password=<Personal Access Token>
# PAT 발급: GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
#           scope: repo 체크 → 생성된 토큰을 비밀번호 칸에 붙여넣기
```

---

## 2. GitHub Pages (정적 소개 페이지)

**방법 A — GitHub Actions (권장, 이미 워크플로 포함)**
1. 저장소 **Settings → Pages**
2. **Build and deployment → Source** 를 **GitHub Actions** 로 선택
3. `main`에 푸시하면 `.github/workflows/pages.yml`이 `docs/`를 자동 배포
4. 완료 후 주소: **https://gemini2k.github.io/DownloadOrganizer/**

**방법 B — Actions 없이 (브랜치 폴더)**
1. Settings → Pages → Source: **Deploy from a branch**
2. Branch: **main** / 폴더: **/docs** → Save
3. 같은 주소로 게시됨

---

## 3. Streamlit Community Cloud (온라인 데모, 무료)

1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인
2. **New app** → Repository: `gemini2k/DownloadOrganizer`, Branch: `main`,
   Main file path: `streamlit_app.py`
3. Deploy → 몇 분 뒤 `https://<앱이름>.streamlit.app` 주소 생성
4. 생성된 주소를 `docs/index.html`의 "온라인 데모" 버튼 링크에 넣고 다시 푸시하면 소개 페이지에서 연결됩니다.

> 의존성은 루트 `requirements.txt`로 자동 설치됩니다.
> 데모는 서버 파일 기준이므로, 실제 정리에는 사용하지 마세요.

---

## 4. Render / Railway (선택)

- **Render**: New → Blueprint → 이 저장소 선택(`render.yaml` 자동 인식). 또는 Web Service로
  Build `pip install -r requirements.txt`, Start `streamlit run streamlit_app.py --server.port $PORT --server.address 0.0.0.0`.
- **Railway**: New Project → Deploy from repo. `Procfile`의 start 명령을 사용.

---

## 5. 로컬 실행 (실제 사용 — 권장)

```bash
pip install -e .
streamlit run streamlit_app.py
```
