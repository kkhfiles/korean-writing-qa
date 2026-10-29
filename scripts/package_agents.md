# 한글 교정기 설치 안내

**사용자가 「설치해 줘」라고 할 때 코딩 에이전트가 따르는 설치 차례** — 이 폴더의 다른 문서(README 등)는 설치에 불필요

## 설치 차례

1. **Python 3.11 이상 확인** — 버전 숫자가 실제로 출력되어야 설치된 것입니다.
   - Windows: `py -3 --version` 을 먼저, 안 되면 `python --version`
   - **⚠️ 아무 출력이 없거나 Microsoft Store 가 열리면 미설치** — Windows 의 `python` 은 이름만 있는 Store 안내 프로그램일 수 있습니다(종료 코드 9009).
   - macOS, Linux: `python3 --version`
2. **없거나 3.11 미만이면 사용자에게 설치 동의를 받음** — 동의하면 아래 명령으로 설치합니다.
   - Windows: `winget install -e --id Python.Python.3.12 --scope user`
   - **⚠️ 설치 직후 다음 단계는 전체 경로로 실행** — 지금 셸에는 경로가 아직 반영되지 않습니다. `"$LOCALAPPDATA/Programs/Python/Python312/python.exe"`(PowerShell 은 `"$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"`)를 씁니다.
   - macOS: `brew install python@3.12`, Homebrew 가 없으면 python.org 설치 파일 안내
3. **이 폴더에서 `bootstrap.py` 를 한 번 실행** — 1~2단계에서 확인한 Python 으로 실행합니다(예: `py -3 bootstrap.py`, `python3 bootstrap.py`).
   - **다른 설치 명령은 따로 실행하지 않음** — 형태소 판정 모듈 설치, 스킬과 훅 설치, 시료 검사, 설치 확인이 모두 이 안에 있습니다.
4. **출력 끝의 「── 요약 ──」을 사용자에게 전달**
   - **❌ 줄이 있으면 그 줄을 보여 주고 멈춤** — 고치려고 다른 명령을 시도하지 않습니다.
   - **새 세션 안내** — Claude Code 는 새 세션을 열어야 스킬과 자동 검사가 적용된다는 점도 함께 알립니다.

## 설치 뒤

- **쓰는 법** — 문서를 쓰면 자동으로 검사합니다. 직접 부르려면 「이 문서 한글 검사해 줘」라고 말합니다.
- **지우는 법** — 이 폴더에서 `python install.py --uninstall` 을 실행합니다(Codex 도 썼으면 `--codex` 를 더함). 이 설치기가 넣은 파일과 훅 줄만 지웁니다.
- **폴더 위치 유지** — 스킬이 이 폴더의 도구를 부릅니다. 폴더를 옮겼다면 새 위치에서 `bootstrap.py` 를 다시 실행합니다.
