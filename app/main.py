from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from typing import List

app = FastAPI(title="Caring API")

@app.get("/health")
def health():
    return {"status": "ok"}


# POST : upload voice
@app.post("/voices/upload")
async def upload_voice(file: UploadFile = File(...)):
    # 내부 로직은 생략, 업로드된 파일 메타만 반환
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "detail": "uploaded (stub)"
    }


# GET : query my voice histories
@app.get("/voices")
async def list_voices(skip: int = 0, limit: int = 20):
    # 내부 로직은 생략, 더미 목록 반환
    items = [
        {"voice_id": f"v_{i}", "filename": f"sample_{i}.wav", "status": "processed"}
        for i in range(skip, min(skip + limit, skip + 20))
    ]
    return {"items": items, "count": len(items), "next": skip + len(items)}


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
