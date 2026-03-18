# 📋 Notion Routine Sync

노션 페이지에 작성한 **하루 루틴 표**와 **하루 회고**를 자동으로 파싱해서  
노션 데이터베이스에 동기화하는 자동화 도구입니다.  
GitHub Actions로 매일 자동 실행됩니다.

---

## ⚙️ 동작 방식

1. 노션 페이지에서 루틴 표 / 회고 블록을 읽어옵니다
2. 제목 패턴으로 담당자 · 날짜를 파싱합니다
3. 루틴 DB / 회고 DB에 행을 생성하거나 업데이트합니다
4. 매일 UTC 19:00 (KST 04:00) 에 자동 실행됩니다

---

## 📁 파일 구조
```
├── sync.py                  # 메인 실행 파일
├── notion_routine_client.py # 루틴 DB CRUD
├── review_client.py         # 회고 DB CRUD
├── .env                     # 환경변수 (gitignore 처리)
└── .github/
    └── workflows/
        └── sync.yml         # GitHub Actions 워크플로우
```

---

## 📝 노션 페이지 작성 규칙

### 루틴 표
제목을 아래 형식으로 작성하고, 바로 아래에 표를 붙여주세요.
```
하루 루틴 표 - 홍길동 (3/18)
```

표 컬럼 예시:

| 시간대 | 내용 | 특이사항 | 달성도 |
|--------|------|----------|--------|
| 기상 | 오전 7시 기상 및 스트레칭 진행. | 오전 8시에 일어남. | 70% 미만 |
| 취침 | 오후 11시 이전 취침 | 10시 반 취침. | 100% |

---

### 하루 회고
제목을 아래 형식으로 작성하고, 바로 아래에 내용을 작성해주세요.
```
하루 회고 - 홍길동 (3/18)
```

회고 작성 형식:
```
⭐⭐⭐⭐ (만족도, 별 개수로 입력)
잘한 점: 오늘 루틴 100% 달성
아쉬운 점: 취침이 늦었음
내일 개선할 점: 23시 전 취침
한 줄 정리: 그래도 잘 버텼다
```

---

## 🗄️ 노션 DB 구조

### 루틴 DB

| 속성 | 타입 |
|------|------|
| 번호 | title |
| 일자 | date |
| 담당자 | select |
| 시간대 | text |
| 내용 | text |
| 특이사항 | text |
| 달성도 | text |

### 회고 DB

| 속성 | 타입 |
|------|------|
| 번호 | title |
| 일자 | date |
| 담당자 | select |
| 만족도 | number |
| 잘한 점 | text |
| 아쉬운 점 | text |
| 내일 개선할 점 | text |
| 한 줄 정리 | text |

---

## 🔐 환경변수 설정

`.env` 파일 (로컬 실행 시):
```env
NOTION_TOKEN=secret_xxxx
ROUTINE_DB_ID=xxxx
REVIEW_DB_ID=xxxx
ROUTINE_PAGE_ID=xxxx
```

GitHub Actions 사용 시 → 레포 **Settings → Secrets and variables → Actions** 에서 동일한 키로 등록해주세요.

---

## 🚀 실행 방법

### 로컬 실행
```bash
pip install notion-client==2.2.1 python-dotenv
python sync.py
```

### 자동 실행

GitHub Actions가 매일 **KST 04:00** 에 자동으로 실행합니다.  
수동으로 실행하려면 Actions 탭 → `Notion Routine Sync` → **Run workflow**

---

## 🔄 중복 처리

- **날짜 + 담당자 + 시간대** 조합이 이미 존재하면 → UPDATE
- 없으면 → CREATE (번호 자동 채번)
- 회고는 **날짜 + 담당자** 조합 기준으로 중복 판단
