import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from typing import List
from .s3_service import upload_fileobj, list_bucket_objects
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .emotion_service import analyze_voice_emotion

app = FastAPI(title="Caring API")

@app.get("/health")
def health():
    return {"status": "ok"}


# POST : upload voice
@app.post("/voices/upload")
async def upload_voice(
    file: UploadFile = File(...),
    folder: Optional[str] = Form(default=None),  # 예: "raw" 또는 "user123/session1"
):
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")

    # 키: optional prefix/YYYYMMDD_originalname
    base_prefix = VOICE_BASE_PREFIX.rstrip("/")
    effective_prefix = f"{base_prefix}/{folder or DEFAULT_UPLOAD_FOLDER}".rstrip("/")
    key = f"{effective_prefix}/{file.filename}"

    # 파일을 S3에 업로드
    upload_fileobj(bucket=bucket, key=key, fileobj=file.file)

    # 감정 분석 수행
    emotion_result = analyze_voice_emotion(file)

    # DB가 없으므로, 버킷의 파일 목록을 반환
    names = list_bucket_objects(bucket=bucket, prefix=effective_prefix)
    return {
        "uploaded": key, 
        "files": names,
        "emotion_analysis": emotion_result
    }


# GET : query my voice histories
@app.get("/voices")
async def list_voices(skip: int = 0, limit: int = 50, folder: Optional[str] = None):
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")
    base_prefix = VOICE_BASE_PREFIX.rstrip("/")
    effective_prefix = f"{base_prefix}/{folder or DEFAULT_UPLOAD_FOLDER}".rstrip("/")

    keys = list_bucket_objects(bucket=bucket, prefix=effective_prefix)
    # 페이징 비슷하게 slice만 적용
    sliced = keys[skip: skip + limit]
    return {"items": sliced, "count": len(sliced), "next": skip + len(sliced)}


# GET : query specific voice & show result
@app.get("/voices/{voice_id}")
async def get_voice(voice_id: str):
    # 내부 로직은 생략, 더미 상세 반환
    result = {
        "voice_id": voice_id,
        "filename": f"{voice_id}.wav",
        "status": "processed",
        "duration_sec": 12.34,
        "analysis": {"pitch_mean": 220.5, "energy": 0.82}
    }
    return JSONResponse(content=result)


# POST : analyze emotion from uploaded voice file
@app.post("/voices/analyze-emotion")
async def analyze_emotion(file: UploadFile = File(...)):
    """음성 파일의 감정을 분석합니다."""
    emotion_result = analyze_voice_emotion(file)
    return emotion_result
