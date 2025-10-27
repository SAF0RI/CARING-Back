import os

# 업로드 기본 베이스 프리픽스 (환경변수 S3_PREFIX로 오버라이드 가능)
VOICE_BASE_PREFIX = os.getenv("S3_PREFIX", "voices")

# 기본 폴더명 (요청에 folder 미지정 시 사용)
DEFAULT_UPLOAD_FOLDER = "voiceFile"

# # 필요 시 허용 폴더 집합 정의 (예: 검증용)
# ALLOWED_FOLDERS = {"raw", "processed", "public"}

