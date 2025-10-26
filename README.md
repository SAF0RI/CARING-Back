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

개발 서버(Uvicorn) 실행:

```bash
uvicorn app.main:app --reload --port 8000
```

API 문서: `http://127.0.0.1:8000/docs`

## 환경 변수 설정

프로젝트 루트에 `.env` 파일을 생성하고 다음 값을 채우세요.

### AWS S3 설정
```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=your-bucket
S3_PREFIX=voices
```

### Google Cloud Speech-to-Text 설정
```
# 서비스 계정 키 파일 경로 설정
GOOGLE_APPLICATION_CREDENTIALS=/path/to/your/service-account-key.json
```

`.env`는 `app/__init__.py`에서 자동 로드됩니다.

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
