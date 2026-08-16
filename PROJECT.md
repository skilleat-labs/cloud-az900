# AZ-900 모의고사 웹 앱 — 프로젝트 현황

> 마지막 업데이트: 2026-08-16

---

## 개요

AZ-900 시험 준비를 위한 온라인 모의고사 플랫폼.
학생들이 이름을 입력하고 문제를 풀면 채점 후 오답 해설을 보여주고, 리더보드에 결과가 등록된다.
강사는 관리자 페이지에서 오답률 높은 문제를 확인하고 오답풀이 수업에 활용할 수 있다.

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| 백엔드 | Python 3.11 + FastAPI + uvicorn |
| DB | SQLite (aiosqlite) |
| 프론트엔드 | Vanilla HTML / CSS / JavaScript |
| 문제 파싱 | python-docx |
| 해설 생성 | Anthropic Claude API (claude-haiku-4-5-20251001) |

---

## 디렉토리 구조

```
az900-quiz/
├── backend/
│   ├── main.py                  # FastAPI 앱 + API 라우터
│   ├── parser.py                # DOCX → 문제 JSON 파서
│   ├── database.py              # SQLite CRUD
│   ├── explanation.py           # DB에서 해설 읽기 (읽기 전용)
│   └── generate_explanations.py # 해설 사전 생성 스크립트 (1회 실행)
├── frontend/
│   ├── index.html               # 홈 (이름 입력 + 시험지 선택)
│   ├── quiz.html                # 시험 화면
│   ├── result.html              # 결과 + 오답 해설
│   ├── leaderboard.html         # 리더보드
│   └── admin.html               # 관리자 — 오답 분석
├── quiz.db                      # SQLite DB (해설 포함)
├── .env                         # 환경변수 (API 키)
├── requirements.txt
└── start.sh                     # 서버 시작 스크립트
```

---

## 문제 파일 현황

문제 원본 위치: `/Users/nurikim/Documents/스킬잇/01. 강의 교안 자료 /AZ900/분류별_문제집/`

| 파일 | 문제 수 |
|------|---------|
| 1-1_클라우드컴퓨팅_2부 | 32문제 |
| 1-2_클라우드서비스이점_2부 | 13문제 |
| 1-3_클라우드서비스유형_2부 | 10문제 |
| 2-1_Azure핵심아키텍처_2부 | 37문제 |
| 2-2_컴퓨팅및네트워크_2부 | 21문제 |
| 2-3_스토리지서비스_2부 | 11문제 |
| 2-4_ID접근보안_2부 | 16문제 |
| 3-1_비용관리_2부 | 7문제 |
| 3-2_거버넌스및규정준수_2부 | 5문제 |
| 3-3_리소스관리및배포_2부 | 10문제 |
| 3-4_모니터링_2부 | 5문제 |
| **합계** | **167문제** |

- `backend/main.py`의 `ALLOWED_FILES` 셋으로 노출할 파일을 제어
- 새 파일 추가 시 `ALLOWED_FILES`에 파일명 추가 후 서버 재시작

---

## 문제 유형

| 유형 | 설명 | 답 형식 |
|------|------|---------|
| `yes_no` | 단일 문장에 대해 예/아니오 판단 | `'예'` or `'아니오'` (문자열) |
| `multiple_choice` | 보기 4개 중 하나 선택 | 0-indexed 정수 |

> **중요**: 원본 DOCX의 "예 아니오 문제"는 3개 문장이 묶여 있었으나,
> 각 문장을 독립된 1개 문제로 분리해 파싱한다.

---

## 텍스트 교정 규칙

`backend/parser.py`의 `_TYPO_FIXES` 리스트에서 관리.
파싱 시 자동 적용되므로 원본 DOCX는 수정하지 않아도 됨.

| 원문 | 교정 |
|------|------|
| 더블릭 | 퍼블릭 |
| 리스스 | 리소스 |
| 응용 프로그램 | 애플리케이션 |
| 클라우드에 서 | 클라우드에서 |
| 마침표/물음표 앞 공백 | 제거 |
| 과도한 공백 | 단일 공백으로 정규화 |

---

## API 엔드포인트

| Method | URL | 설명 |
|--------|-----|------|
| GET | `/api/exams` | 시험지 목록 |
| GET | `/api/exams/{exam_id}/questions` | 문제 목록 (정답 제외, 랜덤 셔플) |
| POST | `/api/sessions` | 세션 시작 |
| POST | `/api/sessions/{id}/submit` | 답안 제출 + 채점 |
| GET | `/api/sessions/{id}/result` | 결과 조회 |
| GET | `/api/leaderboard?exam_id=` | 리더보드 (점수 내림차순, 시간 오름차순) |
| GET | `/api/admin/wrong-stats?exam_id=` | 문제별 오답 통계 (관리자용) |

---

## 해설 운영 방식

```
[1회 사전 생성]
.venv/bin/python3 -m backend.generate_explanations
→ 167개 해설 생성 후 quiz.db에 저장

[이후 운영]
학생이 틀린 문제 → DB에서 해설 즉시 조회 → 결과 페이지에 표시
(API 호출 없음, 지연 없음)
```

- 재실행 시 이미 생성된 해설은 건너뜀 (중단 후 이어서 실행 가능)
- quiz.db를 서버에 함께 배포하면 서버에서 재생성 불필요

---

## 화면 구성

| 페이지 | URL | 대상 |
|--------|-----|------|
| 홈 | `/` | 학생 |
| 시험 | `/quiz.html` | 학생 |
| 결과 | `/result.html` | 학생 |
| 리더보드 | `/leaderboard.html` | 학생 |
| 오답 분석 | `/admin.html` | 강사 |

### 관리자 페이지 기능
- 오답률 높은 순으로 전체 문제 목록
- 시험지별 필터
- **목록 보기**: 펼치면 정답 + 해설 확인
- **오답풀이 모드**: 슬라이드 형태로 1문제씩 — 수업 중 빔프로젝터 활용

---

## 로컬 실행 방법

```bash
cd /Users/nurikim/Documents/az900-quiz

# 1. .env에 API 키 설정 (해설 생성 시에만 필요)
# ANTHROPIC_API_KEY=sk-ant-...

# 2. 해설 사전 생성 (최초 1회)
.venv/bin/python3 -m backend.generate_explanations

# 3. 서버 시작
./start.sh
# → http://localhost:8000
```

---

## 향후 계획

| 항목 | 상태 |
|------|------|
| Azure 서버 배포 | 예정 |
| 인프런용 실행파일 (PyInstaller) | 예정 — 단독 실행, 리더보드 없는 단순화 버전 |

---

## DB 스키마

```sql
exams        -- 시험지 목록 (id, filename, title, question_count)
sessions     -- 응시 세션 (user_name, exam_id, score, time_seconds)
answers      -- 문항별 답변 (session_id, question_id, user_answer, is_correct)
explanations -- 사전 생성된 해설 (exam_id, question_id, content)
```
