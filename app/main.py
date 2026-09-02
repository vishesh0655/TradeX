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
@app.post("/orders/buy", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def buy_stock(
    payload: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    stock = db.query(models.Stock).filter(models.Stock.symbol == payload.stock_symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found")

    if payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive")

    total_cost = stock.current_price * payload.quantity

    wallet = db.query(models.Wallet).filter(models.Wallet.user_id == current_user.id).first()
    if wallet.balance < total_cost:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient balance")

    try:
        wallet.balance -= total_cost

        holding = (
            db.query(models.Holding)
            .filter(models.Holding.user_id == current_user.id, models.Holding.stock_id == stock.id)
            .first()
        )

        if holding:
            total_shares = holding.quantity + payload.quantity
            total_invested = (holding.average_buy_price * holding.quantity) + total_cost
            holding.average_buy_price = total_invested / total_shares
            holding.quantity = total_shares
        else:
            holding = models.Holding(
                user_id=current_user.id,
                stock_id=stock.id,
                quantity=payload.quantity,
                average_buy_price=stock.current_price,
            )
            db.add(holding)

        order = models.Order(
            user_id=current_user.id,
            stock_id=stock.id,
            order_type="BUY",
            quantity=payload.quantity,
            price_per_share=stock.current_price,
            status="COMPLETED",
        )
        db.add(order)

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order failed, please try again")

    return order
@app.post("/orders/sell", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def sell_stock(
    payload: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    stock = db.query(models.Stock).filter(models.Stock.symbol == payload.stock_symbol.upper()).first()
    if not stock:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stock not found")

    if payload.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be positive")

    holding = (
        db.query(models.Holding)
        .filter(models.Holding.user_id == current_user.id, models.Holding.stock_id == stock.id)
        .first()
    )

    if not holding or holding.quantity < payload.quantity:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient shares to sell")

    total_proceeds = stock.current_price * payload.quantity

    try:
        wallet = db.query(models.Wallet).filter(models.Wallet.user_id == current_user.id).first()
        wallet.balance += total_proceeds

        if holding.quantity == payload.quantity:
            db.delete(holding)
        else:
            holding.quantity -= payload.quantity

        order = models.Order(
            user_id=current_user.id,
            stock_id=stock.id,
            order_type="SELL",
            quantity=payload.quantity,
            price_per_share=stock.current_price,
            status="COMPLETED",
        )
        db.add(order)

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Order failed, please try again")

    return order
@app.get("/holdings", response_model=list[schemas.HoldingOut])
def get_holdings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    holdings = db.query(models.Holding).filter(models.Holding.user_id == current_user.id).all()

    result = []
    for holding in holdings:
        stock = holding.stock
        invested_value = holding.average_buy_price * holding.quantity
        current_value = stock.current_price * holding.quantity
        profit_loss = current_value - invested_value
        profit_loss_percent = (profit_loss / invested_value) * 100 if invested_value > 0 else 0

        result.append(schemas.HoldingOut(
            stock_symbol=stock.symbol,
            company_name=stock.company_name,
            quantity=holding.quantity,
            average_buy_price=float(holding.average_buy_price),
            current_price=float(stock.current_price),
            current_value=float(current_value),
            invested_value=float(invested_value),
            profit_loss=float(profit_loss),
            profit_loss_percent=round(float(profit_loss_percent), 2),
        ))

    return result