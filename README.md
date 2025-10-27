# Caring Voice

음성 관련 애플리케이션 프로젝트입니다.

## 요구사항

- Python 3.11+

## 설치

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

## 실행

### 로컬 개발 환경

개발 서버(Uvicorn) 실행:

```bash
uvicorn app.main:app --reload --port 8000
```

API 문서: `http://127.0.0.1:8000/docs`

### Docker를 사용한 실행

#### 1. 환경 변수 설정
`.env` 파일에 AWS RDS 및 필요한 설정을 추가하세요:

```env
# 데이터베이스 (AWS RDS)
DB_HOST=your-rds-endpoint.region.rds.amazonaws.com
DB_PORT=3306
DB_USER=admin
DB_PASSWORD=your_password
DB_NAME=caring_voice

# AWS 설정
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=your-bucket-name

# Google Cloud 설정
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/google-credentials.json
```

#### 2. Docker Compose로 서버 실행

```bash
# 빌드 및 실행
docker-compose up -d

# 로그 확인
docker-compose logs -f

# 중지
docker-compose down
```

#### 3. API 접근
- 로컬: `http://localhost:8000`
- API 문서: `http://localhost:8000/docs`

## 데이터베이스 마이그레이션

### 자동 마이그레이션
서버 시작 시 자동으로 마이그레이션이 실행됩니다.

### 수동 마이그레이션
```bash
# 마이그레이션 파일 생성
alembic revision --autogenerate -m "커밋 메시지"

# 마이그레이션 실행
alembic upgrade head

# 마이그레이션 롤백
alembic downgrade -1
```

## 질문 데이터 초기화

질문 템플릿을 데이터베이스에 저장합니다:

```bash
python init_questions.py
```

이 명령어는 다음 카테고리의 질문들을 자동으로 추가합니다:
- emotion (14개)
- stress (10개)
- physical (10개)
- social (10개)
- self_reflection (15개)

총 59개의 질문이 데이터베이스에 저장됩니다.

## 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 값을 채우세요. 예시는 `.env.example` 참고.

```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=your-bucket
S3_PREFIX=voices
```

### Google Cloud 설정
```
# 서비스 계정 키 파일 경로 설정 (Speech-to-Text, Natural Language API 공통)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
```

### 데이터베이스 설정
```
# MySQL 데이터베이스 연결 정보
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=table_name
```

`.env`는 `app/database.py`에서 자동 로드됩니다.

> 💡 **배포 환경**: 운영 환경에서는 환경변수를 시스템에 직접 설정하거나, `.env` 파일을 사용하지 않고 컨테이너/Docker의 환경변수 설정을 사용하세요.

## API 엔드포인트

### 음성 관련 API
- `POST /voices/upload`: 음성 파일 업로드 + STT 변환
- `POST /voices/transcribe`: STT 변환만
- `POST /voices/{voice_key}/analyze-emotion`: S3 파일 감정 분석
- `GET /voices`: 파일 목록 조회

### 텍스트 분석 API (Google Natural Language)
- `POST /nlp/sentiment`: 텍스트 감정 분석
- `POST /nlp/entities`: 엔티티 추출
- `POST /nlp/syntax`: 구문 분석
- `POST /nlp/analyze`: 종합 텍스트 분석

## 프로젝트 구조

```
caring-voice/
├── app/
│   ├── __init__.py
│   └── main.py          # FastAPI 엔트리 포인트 및 엔드포인트
├── .gitignore
├── README.md
├── requirements.txt
└── LICENSE
```

## 개발

프로젝트 개발에 참여하시려면:

1. 이 저장소를 포크하세요
2. 새로운 브랜치를 생성하세요 (`git checkout -b feature/새기능`)
3. 변경사항을 커밋하세요 (`git commit -am '새기능 추가'`)
4. 브랜치에 푸시하세요 (`git push origin feature/새기능`)
5. Pull Request를 생성하세요

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
