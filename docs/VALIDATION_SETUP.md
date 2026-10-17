# 검증 전용 실행환경

현재 검증 도구는 전체 앱이 아니다. Python3.12 가상환경에서 requirements-validation.txt를 설치하고 실행한다. venv·패키지·임시 로그는 work/ 또는 .venv에 두며 Git 제외다. 일반 python이 WindowsApps 별칭이면 설치된 실제 Python 실행파일의 명시 경로를 사용한다. 패키지 설치 실패 시 기본 TEMP 대신 작업 폴더 안의 별도 TEMP/TMP를 사용한 결과를 기록한다. 관리자 권한/전역 설치는 필요조건이 아니다.

프로젝트 루트 기준 검증 명령:

```powershell
# 검증된 Python 3.12 실행파일로 venv 생성 후 해당 환경의 python 사용
python -m pip install -r requirements-validation.txt
python scripts/validation/probe_hwpx.py
python scripts/validation/workflow_contract.py
python -m unittest discover -s tests -v
```

generate_hwpx_fixture.py는 기존 fixture 덮어쓰기를 거부한다. 이번 생성은 이미 완료했으므로 분석/재검증 시 probe_hwpx.py만 실행한다. 새 생성 시험은 별도 버전/파일명으로 수행한다. .env.example은 빈 설정 계약이며 현재 도구는 외부 모델을 호출하지 않는다.

이 Windows sandbox에서는 Git이 새 저장소를 Administrators 소유로 판단해 일반 git status를 dubious ownership으로 거부했다. 본 작업은 **검증한 현재 루트만** `git -c safe.directory="현재 루트 절대경로" <명령>`으로 지정해 검사했다. 전역 safe.directory나 소유권을 바꾸지 않았다. 일반 사용자 환경에서 같은 오류가 없다면 추가 옵션은 필요 없다. `safe.directory=*`는 사용하지 않는다.

루트 AGENTS/Skill은 자동 탐색에 맞는 위치다. 형식/경로 검사, 로컬 app-server skills/list, 현재/다음 세션 실제 주입을 구별한다. app-server는 기본 상태DB 쓰기 권한이 없을 수 있어 프로세스 단위 sqlite_home/log_dir을 work 아래로 지정해 읽기 전용 discovery만 시도했다. thread/start·turn/start·모델 호출·글로벌 설정 변경은 하지 않는다. 실패하면 원인/해결조건을 보고한다.
