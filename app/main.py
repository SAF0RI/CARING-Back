import os
from typing import Optional
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from typing import List
from .s3_service import upload_fileobj, list_bucket_objects
from .constants import VOICE_BASE_PREFIX, DEFAULT_UPLOAD_FOLDER
from .emotion_service import analyze_voice_emotion
from .stt_service import transcribe_voice
from .nlp_service import analyze_text_sentiment, analyze_text_entities, analyze_text_syntax

app = FastAPI(title="Caring API")

@app.get("/health")
def health():
    return {"status": "ok"}


# POST : upload voice with STT
@app.post("/voices/upload")
async def upload_voice(
    file: UploadFile = File(...),
    folder: Optional[str] = Form(default=None),
    language_code: str = Form(default="ko-KR")
):
    """음성 파일을 업로드하고 STT를 수행합니다."""
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")

    # 파일 내용을 메모리에 읽기 (두 번 사용하기 위해)
    file_content = await file.read()
    
    # S3 업로드
    base_prefix = VOICE_BASE_PREFIX.rstrip("/")
    effective_prefix = f"{base_prefix}/{folder or DEFAULT_UPLOAD_FOLDER}".rstrip("/")
    key = f"{effective_prefix}/{file.filename}"
    
    from io import BytesIO
    file_obj_for_s3 = BytesIO(file_content)
    upload_fileobj(bucket=bucket, key=key, fileobj=file_obj_for_s3)

    # STT 변환 - 파일 내용을 직접 사용
    from io import BytesIO
    temp_file_obj = BytesIO(file_content)
    
    # UploadFile과 유사한 객체 생성
    class TempUploadFile:
        def __init__(self, content, filename):
            self.file = content
            self.filename = filename
            self.content_type = "audio/wav"
    
    temp_upload_file = TempUploadFile(temp_file_obj, file.filename)
    stt_result = transcribe_voice(temp_upload_file, language_code)

    # 파일 목록 조회
    names = list_bucket_objects(bucket=bucket, prefix=effective_prefix)
    
    return {
        "uploaded": key,
        "files": names,
        "transcription": stt_result
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


# POST : analyze emotion from S3 file
@app.post("/voices/{voice_key}/analyze-emotion")
async def analyze_emotion_from_s3(voice_key: str):
    """S3에 저장된 음성 파일의 감정을 분석합니다."""
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET_NAME not configured")
    
    try:
        # S3에서 파일 다운로드
        from .s3_service import get_s3_client
        s3_client = get_s3_client()
        
        response = s3_client.get_object(Bucket=bucket, Key=voice_key)
        file_content = response['Body'].read()
        
        # BytesIO로 파일 객체 생성
        from io import BytesIO
        file_obj = BytesIO(file_content)
        
        # 파일명 추출 (키에서 마지막 부분)
        filename = voice_key.split('/')[-1]
        
        class FileWrapper:
            def __init__(self, content, filename, content_type):
                self.file = content
                self.filename = filename
                self.content_type = content_type
        
        emotion_file = FileWrapper(file_obj, filename, "audio/wav")
        emotion_result = analyze_voice_emotion(emotion_file)
        
        return {
            "voice_key": voice_key,
            "emotion_analysis": emotion_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"파일을 찾을 수 없거나 분석 중 오류 발생: {str(e)}")


# POST : convert speech to text using Google STT
@app.post("/voices/transcribe")
async def transcribe_speech(
    file: UploadFile = File(...),
    language_code: str = "ko-KR"
):
    """음성 파일을 텍스트로 변환합니다."""
    stt_result = transcribe_voice(file, language_code)
    return stt_result


# POST : analyze text sentiment using Google NLP
@app.post("/nlp/sentiment")
async def analyze_sentiment(
    text: str,
    language_code: str = "ko"
):
    """텍스트의 감정을 분석합니다."""
    sentiment_result = analyze_text_sentiment(text, language_code)
    return sentiment_result


# POST : extract entities from text using Google NLP
@app.post("/nlp/entities")
async def extract_entities(
    text: str,
    language_code: str = "ko"
):
    """텍스트에서 엔티티를 추출합니다."""
    entities_result = analyze_text_entities(text, language_code)
    return entities_result


# POST : analyze text syntax using Google NLP
@app.post("/nlp/syntax")
async def analyze_syntax(
    text: str,
    language_code: str = "ko"
):
    """텍스트의 구문을 분석합니다."""
    syntax_result = analyze_text_syntax(text, language_code)
    return syntax_result


# POST : comprehensive text analysis using Google NLP
@app.post("/nlp/analyze")
async def analyze_text_comprehensive(
    text: str,
    language_code: str = "ko"
):
    """텍스트의 감정, 엔티티, 구문을 종합 분석합니다."""
    sentiment_result = analyze_text_sentiment(text, language_code)
    entities_result = analyze_text_entities(text, language_code)
    syntax_result = analyze_text_syntax(text, language_code)
    
    return {
        "text": text,
        "language_code": language_code,
        "sentiment_analysis": sentiment_result,
        "entity_analysis": entities_result,
        "syntax_analysis": syntax_result
    }
