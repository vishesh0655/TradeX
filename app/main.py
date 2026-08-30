from fastapi import FastAPI

app = FastAPI(title="TradeX API")


@app.get("/")
def home():
    return {"message": "TradeX backend is running"}