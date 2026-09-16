from fastapi import FastAPI
import uvicorn

app = FastAPI(title="Handoff API placeholder")


@app.get("/")
def root():
    return {
        "message": "The real operator API is started inside a running discovery session so it can share the exact Playwright Page object."
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
