# 제주특별법 공개 입법동향 모니터링 (무료 시범 버전)

GitHub Pages에서 누구나 볼 수 있는 **비공식 공개 웹사이트**를 운영하는 배포 준비 파일입니다.

- 주소 예시: `https://내깃허브아이디.github.io/jeju-law-watch/`
- 공개 페이지: `site/index.html`
- 자동 수집: `scripts/collect.py`
- 30분 간격 예약 실행: `.github/workflows/publish.yml`
- 공식 API와 연결되지 않았거나 수집 오류가 나면 **오류/연결 대기를 명시**하며 기록을 지어내지 않습니다.
- 실제 배포와 외부 API 조회는 아직 진행되지 않았습니다. **로그인, API 인증키 발급, GitHub 등록이 필요합니다.**

## 최초 설치 순서 (비개발자용)

### 1. GitHub 계정 및 저장소 생성

1. [github.com](https://github.com/)에서 로그인/회원가입.
2. 오른쪽 위 `+` → `New repository` 클릭.
3. `Repository name`: `jeju-law-watch` 입력.
4. **Public(공개)** 선택. 공개 사이트에 사용할 코드와 자동 수집 데이터도 공개됩니다.
5. `Create repository` 클릭.

### 2. 파일 올리기

1. 이 ZIP 파일을 내 컴퓨터에서 압축 해제.
2. GitHub 저장소 화면에서 `uploading an existing file` 또는 `Add file → Upload files`를 누릅니다.
3. **`site` 폴더와 `scripts` 폴더, `README.md`, `.github/workflows/publish.yml`을 모두 경로 그대로 업로드해야 합니다.** 웹 UI에서 `.github` 같은 숨김 폴더 업로드가 어려운 경우 GitHub Desktop으로 전체 폴더를 업로드하는 편이 쉽습니다.
4. 깃허브의 `Code` 탭에서 `.github/workflows/publish.yml` 파일이 보이는지 확인합니다.

> 유의: GitHub 웹사이트에서 폴더째 업로드가 제대로 안 될 경우에는 GitHub Desktop ([desktop.github.com](https://desktop.github.com/))을 사용해 폴더 구조를 그대로 올리세요.

### 3. Pages 공개 설정

1. 저장소 `Settings` → 왼쪽 `Pages`.
2. `Build and deployment` 항목에서 `Source`를 **GitHub Actions**로 선택.
3. `Actions` 탭에서 `제주특별법 공개 모니터링 자동 갱신` 항목을 열어 `Run workflow`를 수동 실행.
4. 완료 후 `Settings → Pages`에 표시되는 공개 주소를 누릅니다.
5. 정상 동작이라면 API가 아직 없을 경우 `인증키 미설정` 및 `공식 API 연결... 미완료` 상태가 표시됩니다. 이는 오류가 아니라 초기 상태입니다.

### 4. 공식 API 인증키 발급

- 국회: [열린국회정보](https://open.assembly.go.kr/) → OPEN API 인증키 발급. API 코드 `nzmimeepazxkubdpn` (국회의원 발의법률안). **22대 의원발의 개정안만** 수집합니다.
- 법령: [국가법령정보 공동활용](https://open.law.go.kr/) → 법령 목록 조회 Open API 사용 신청, `OC` 인증값 발급.
- 기관 신청 과정에서 홈페이지 주소가 필요하면 위에서 생성한 GitHub Pages 주소를 입력합니다.

**절대 인증키를 공개 저장소에 직접 올리지 마세요.**

### 5. 두 개의 인증값 등록

1. GitHub 저장소 `Settings` → `Secrets and variables` → `Actions`.
2. `New repository secret` 선택, 두 건을 등록합니다.

| Name | Secret (Value) |
|---|---|
| `ASSEMBLY_API_KEY` | 국회 API 인증키 |
| `LAW_OC` | 법제처 API 인증값(OC) |

GitHub Actions 자동 실행 시 두 값이 안전하게 수집 프로그램에 전달됩니다. 외부 공개 화면에는 노출하지 않습니다.

### 6. 정상 동작 점검

1. GitHub `Actions` 탭 → 해당 워크플로 → `Run workflow`.
2. `공식 데이터 갱신`의 실행 로그에서 `국회:정상`, `법제처:정상`인지 확인합니다.
3. 홈페이지 새로고침 후 상단 `공식 데이터 수집 정상`과 `마지막 실행`이 표시되는지 확인합니다.
4. 둘 중 하나라도 `조회 오류`가 뜨면 API 신청 및 사용 승인, 인증값, API 제공 형식을 확인합니다.
5. 초기 정상 수집은 기준 정보로 저장되며 **신규 변경 기록을 생성하지 않습니다**. 이후부터 처리상태 변화가 발생하면 변경 이력이 추가됩니다.

## 무료로 운영 가능한가요?

- **GitHub Pages는 GitHub Free 계정의 공개 저장소에서 무료 사용이 가능합니다.** 공개 저장소 GitHub Actions 실행시간은 무료입니다. 다만 Pages/Actions 서비스는 이용약관, 동시 실행·사용 제한, 정책 변경 영향을 받습니다.
- 주소는 `.github.io`를 쓰면 **도메인 구매비가 0원**입니다. `jeju-law.kr`처럼 별도 도메인을 사려면 도메인 비용이 듭니다.
- GitHub Actions의 예약 실행은 약속된 시각에 반드시 즉시 실행되지는 않습니다. 공식 기관 데이터 등록 자체도 지연될 수 있으므로 법적 기한 관리 및 긴급 보고의 단독 경로로 사용하지 마세요.

## 현재 지원 범위와 한계

| 기능 | 상태 |
|---|---|
| 공개 웹사이트, 모바일 반응형 화면, 검색 | 포함 |
| 22대 국회의원 발의 제주특별법 개정안 목록 | API 연계 코드 포함, 실제 인증 후 점검 필요 |
| 의원발의 법안의 공표된 처리상태 변경 비교 | 포함 (최초 수집 이후) |
| 법제처 제주특별법 공포번호·공포일·시행일 정보 비교 | API 연계 코드 포함, 실제 인증 후 점검 필요 |
| 정부제출 법률안, 위원회 대안 | **미포함** |
| 소위 세부 심사일정, 회의록, 수정안의 본문 비교 | **미포함** |
| 휴대전화 푸시 알림 | **미포함** (홈페이지에서 직접 확인) |
| ChatGPT 자동 분석 | **미포함** (차후 확장) |

법제처 기본정보 변경은 **조문 내용이 실제로 달라졌다는 사실과 동의어가 아닙니다**. 신구조문 비교 없이 법적 효과를 단정하지 마세요.

## 개인정보 및 보안

이 홈페이지는 **누구나 열람할 수 있으며** 공개 저장소의 `site/data/monitor.json`도 공개됩니다. 공개된 의안정보 및 법령 기본정보만 저장해야 합니다. 비공개 부처협의 내용, 내부 검토 의견, 담당자 연락처, 비밀키, 내부 파일을 추가하지 마세요. 실제 도 공무용으로 운영할 경우 기관의 외부서비스 사용·대외공개 심사 및 보안규정을 확인하세요.

제주도·정부 공식 시스템으로 오인되지 않도록 사이트 모든 화면 하단에 `비공식 공개 정보 서비스` 표시가 있습니다.

## 관련 공식 정보

- https://open.assembly.go.kr/
- https://open.law.go.kr/
- https://docs.github.com/en/pages/getting-started-with-github-pages
- https://docs.github.com/en/actions

## 로컬 테스트

```bash
python -m unittest discover -s tests -v
python scripts/collect.py
python -m http.server 8000 -d site
```

테스트 화면: http://localhost:8000
