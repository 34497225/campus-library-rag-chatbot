from fastapi import FastAPI


app = FastAPI(
    title="Campus Library Chatbot API",
    description="Backend API for authentication and conversation management.",
    version="0.1.0",
)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}