from fastapi import FastAPI

app = FastAPI(title="PingMeBot")  # или как ты назвал проект

@app.get("/health")
async def health():
    return {"status": "ok"}
