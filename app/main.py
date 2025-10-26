from fastapi import FastAPI

app = FastAPI(title="Caring API")

@app.get("/health")
def health():
    return {"status": "ok"}
