from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

app = FastAPI(title="TradeX API")


@app.get("/")
def home():
    return {"message": "TradeX backend is running"}


@app.get("/database-check")
def database_check():
    with engine.connect() as connection:
        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    return {
        "status": "connected",
        "database": database_name,
    }


@app.get("/stocks")
def list_stocks():
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT symbol, company_name, current_price
                FROM stocks
                WHERE is_active = TRUE
                ORDER BY symbol
                """
            )
        )

        stocks = [
            {
                "symbol": row.symbol,
                "company_name": row.company_name,
                "current_price": float(row.current_price),
            }
            for row in result
        ]

    return {"stocks": stocks}