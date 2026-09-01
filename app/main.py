from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import hash_password, verify_password, create_access_token, get_current_user
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
@app.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    new_user = models.User(
        name=payload.name,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    new_wallet = models.Wallet(user_id=new_user.id)
    db.add(new_wallet)
    db.commit()

    return new_user
@app.post("/login", response_model=schemas.Token)
def login_user(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    access_token = create_access_token(user_id=user.id)
    return {"access_token": access_token, "token_type": "bearer"}
@app.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user