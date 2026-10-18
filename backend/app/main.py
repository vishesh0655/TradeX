import os
import firebase_admin
from firebase_admin import auth as firebase_auth
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.security import hash_password, verify_password, create_access_token, get_current_user
from app.services.order_service import (
    execute_market_order,
    create_limit_order,
    OrderServiceError,
)
from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

app = FastAPI(title="TradeX API")
if not firebase_admin._apps:
    firebase_admin.initialize_app()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/stocks/{symbol}/quote")
def get_stock_quote(symbol: str, db: Session = Depends(get_db)):
    stock = (
        db.query(models.Stock)
        .filter(models.Stock.symbol == symbol.strip().upper(), models.Stock.is_active.is_(True))
        .first()
    )
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    return {
        "symbol": stock.symbol,
        "company_name": stock.company_name,
        "price": stock.current_price,
        "updated_at": stock.updated_at,
        "data_mode": "SIMULATED",
    }


@app.get("/wallet", response_model=schemas.WalletOut)
def get_wallet(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    wallet = db.query(models.Wallet).filter(models.Wallet.user_id == current_user.id).first()
    if wallet is None:
        raise HTTPException(status_code=404, detail="Virtual wallet not found")
    return schemas.WalletOut(balance=wallet.balance, currency=wallet.currency)


@app.get("/wallet/transactions", response_model=list[schemas.WalletTransactionOut])
def get_wallet_transactions(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    wallet = db.query(models.Wallet).filter(models.Wallet.user_id == current_user.id).first()
    if wallet is None:
        raise HTTPException(status_code=404, detail="Virtual wallet not found")
    return (
        db.query(models.WalletTransaction)
        .filter(models.WalletTransaction.wallet_id == wallet.id)
        .order_by(models.WalletTransaction.created_at.desc(), models.WalletTransaction.id.desc())
        .all()
    )


@app.get("/watchlist", response_model=list[schemas.WatchlistOut])
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.WatchlistItem, models.Stock)
        .join(models.Stock, models.Stock.id == models.WatchlistItem.stock_id)
        .filter(models.WatchlistItem.user_id == current_user.id)
        .order_by(models.WatchlistItem.created_at.desc())
        .all()
    )
    return [
        schemas.WatchlistOut(
            symbol=stock.symbol,
            company_name=stock.company_name,
            current_price=stock.current_price,
            created_at=item.created_at,
        )
        for item, stock in rows
    ]


@app.post("/watchlist", response_model=schemas.WatchlistOut, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(
    payload: schemas.WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    symbol = payload.symbol.strip().upper()
    stock = db.query(models.Stock).filter(models.Stock.symbol == symbol, models.Stock.is_active.is_(True)).first()
    if stock is None:
        raise HTTPException(status_code=404, detail="Stock not found")
    item = (
        db.query(models.WatchlistItem)
        .filter(models.WatchlistItem.user_id == current_user.id, models.WatchlistItem.stock_id == stock.id)
        .first()
    )
    if item is None:
        item = models.WatchlistItem(user_id=current_user.id, stock_id=stock.id)
        db.add(item)
        db.commit()
        db.refresh(item)
    return schemas.WatchlistOut(
        symbol=stock.symbol,
        company_name=stock.company_name,
        current_price=stock.current_price,
        created_at=item.created_at,
    )


@app.delete("/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def delete_watchlist_item(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = (
        db.query(models.WatchlistItem)
        .join(models.Stock, models.Stock.id == models.WatchlistItem.stock_id)
        .filter(models.WatchlistItem.user_id == current_user.id, models.Stock.symbol == symbol.strip().upper())
        .first()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    db.delete(item)
    db.commit()
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
@app.post("/auth/phone", response_model=schemas.Token)
def phone_login(
    payload: schemas.SocialAuthRequest,
    db: Session = Depends(get_db),
):
    # 1. Verify Firebase ID token
    try:
        decoded_token = firebase_auth.verify_id_token(
            payload.credential
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase credential",
        )

    # 2. Confirm this was a phone authentication
    firebase_claims = decoded_token.get("firebase", {})
    sign_in_provider = firebase_claims.get("sign_in_provider")

    phone_number = decoded_token.get("phone_number")
    firebase_uid = decoded_token.get("uid")

    if (
        sign_in_provider != "phone"
        or not phone_number
        or not firebase_uid
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified phone authentication is required",
        )

    # 3. Find an existing TradeX phone identity
    identity = (
        db.query(models.UserIdentity)
        .filter(
            models.UserIdentity.provider == "phone",
            models.UserIdentity.provider_subject == firebase_uid,
        )
        .first()
    )

    if identity:
        user = identity.user

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        access_token = create_access_token(user_id=user.id)

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    # 4. Create a new user for a first-time phone login
    try:
        phone_digits = "".join(
            char for char in phone_number if char.isdigit()
        )

        # User.email is currently required and unique in your database.
        # Use a deterministic internal email for phone-only accounts.
        internal_email = f"phone_{phone_digits}@phone.tradex.local"

        user = (
            db.query(models.User)
            .filter(models.User.email == internal_email)
            .first()
        )

        if user:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive",
                )
        else:
            user = models.User(
                name="TradeX User",
                email=internal_email,
                password_hash=None,
            )

            db.add(user)
            db.flush()

            wallet = models.Wallet(
                user_id=user.id,
            )

            db.add(wallet)

        # 5. Save the Firebase identity
        identity = models.UserIdentity(
            user_id=user.id,
            provider="phone",
            provider_subject=firebase_uid,
        )

        db.add(identity)
        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Phone login failed",
        )

    # 6. Return the normal TradeX JWT
    access_token = create_access_token(user_id=user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
@app.post("/auth/email", response_model=schemas.Token)
def email_auth(
    payload: schemas.SocialAuthRequest,
    db: Session = Depends(get_db),
):
    # 1. Verify Firebase ID token
    try:
        decoded_token = firebase_auth.verify_id_token(
            payload.credential
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase credential",
        )

    # 2. Confirm password-based Firebase authentication
    firebase_claims = decoded_token.get("firebase", {})
    sign_in_provider = firebase_claims.get("sign_in_provider")

    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")
    email_verified = decoded_token.get("email_verified", False)
    name = decoded_token.get("name") or "TradeX User"

    if (
        sign_in_provider != "password"
        or not firebase_uid
        or not email
        or email_verified is not True
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Verified email authentication is required",
        )

    email = email.strip().lower()

    # 3. Check whether this Firebase identity already exists
    identity = (
        db.query(models.UserIdentity)
        .filter(
            models.UserIdentity.provider == "email",
            models.UserIdentity.provider_subject == firebase_uid,
        )
        .first()
    )

    if identity:
        user = identity.user

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        access_token = create_access_token(user_id=user.id)

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    # 4. Prevent silently linking an existing account
    existing_user = (
        db.query(models.User)
        .filter(models.User.email == email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This email is already associated with a TradeX "
                "account. Please sign in using your existing method."
            ),
        )

    # 5. Create the TradeX user, wallet, and Firebase identity
    try:
        user = models.User(
            name=name,
            email=email,
            password_hash=None,
        )

        db.add(user)
        db.flush()

        wallet = models.Wallet(
            user_id=user.id,
        )

        identity = models.UserIdentity(
            user_id=user.id,
            provider="email",
            provider_subject=firebase_uid,
        )

        db.add(wallet)
        db.add(identity)

        db.commit()
        db.refresh(user)

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Email authentication failed",
        )

    # 6. Return the normal TradeX JWT
    access_token = create_access_token(user_id=user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
@app.post("/auth/google", response_model=schemas.Token)
def google_login(
    payload: schemas.SocialAuthRequest,
    db: Session = Depends(get_db),
):
    try:
        google_user = id_token.verify_oauth2_token(
            payload.credential,
            requests.Request(),
            os.environ["GOOGLE_CLIENT_ID"],
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google credential",
        )

    if google_user.get("iss") not in (
        "accounts.google.com",
        "https://accounts.google.com",
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google issuer",
        )

    google_sub = google_user.get("sub")
    email = google_user.get("email")
    name = google_user.get("name") or "TradeX User"
    email_verified = google_user.get("email_verified", False)

    if not google_sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account information is incomplete",
        )

    if not email_verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google email is not verified",
        )

    identity = (
        db.query(models.UserIdentity)
        .filter(
            models.UserIdentity.provider == "google",
            models.UserIdentity.provider_subject == google_sub,
        )
        .first()
    )

    if identity:
        user = identity.user

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        access_token = create_access_token(user_id=user.id)

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    user = (
        db.query(models.User)
        .filter(models.User.email == email)
        .first()
    )

    try:
        if not user:
            user = models.User(
                name=name,
                email=email,
                password_hash=None,
            )

            db.add(user)
            db.flush()

            wallet = models.Wallet(
                user_id=user.id,
            )

            db.add(wallet)

        else:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is inactive",
                )

        identity = models.UserIdentity(
            user_id=user.id,
            provider="google",
            provider_subject=google_sub,
        )

        db.add(identity)
        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google login failed",
        )

    access_token = create_access_token(user_id=user.id)

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }
@app.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return schemas.UserOut(
        id=current_user.id,
        name=current_user.name,
        email=current_user.email,
        wallet_balance=float(current_user.wallet.balance),
    )
@app.post(
    "/orders",
    response_model=schemas.OrderOut,
    status_code=status.HTTP_201_CREATED,
)
def place_order(
    payload: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:

        # -----------------------------
        # MARKET
        # -----------------------------

        if payload.order_type == "MARKET":

            order = execute_market_order(
                db,
                user_id=current_user.id,
                stock_symbol=payload.stock_symbol,
                side=payload.side,
                quantity=payload.quantity,
                client_order_id=payload.client_order_id,
            )

        # -----------------------------
        # LIMIT
        # -----------------------------

        elif payload.order_type == "LIMIT":

            order = create_limit_order(
                db,
                user_id=current_user.id,
                stock_symbol=payload.stock_symbol,
                side=payload.side,
                quantity=payload.quantity,
                limit_price=payload.limit_price,
                client_order_id=payload.client_order_id,
            )

        # -----------------------------
        # STOP / STOP_LIMIT
        # -----------------------------

        else:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"{payload.order_type} orders are not enabled yet."
                ),
            )

    except OrderServiceError as exc:

        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        )

    except HTTPException:
        raise

    except Exception:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order failed, please try again",
        )

    return schemas.OrderOut(
        id=order.id,
        stock_symbol=order.stock.symbol,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        average_fill_price=(
            float(order.average_fill_price)
            if order.average_fill_price is not None
            else None
        ),
        price_per_share=(
            float(order.average_fill_price)
            if order.average_fill_price is not None
            else None
        ),
        total_amount=(
            float(
                order.average_fill_price
                * order.filled_quantity
            )
            if order.average_fill_price is not None
            else None
        ),
        status=order.status,
        client_order_id=order.client_order_id,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )

# Temporary compatibility routes for the existing frontend/API clients.
# They use the same Order Service and therefore the same execution/accounting path.
@app.post("/orders/buy", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def buy_stock(
    payload: schemas.LegacyOrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _place_legacy_order(payload, "BUY", db, current_user)


@app.post("/orders/sell", response_model=schemas.OrderOut, status_code=status.HTTP_201_CREATED)
def sell_stock(
    payload: schemas.LegacyOrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _place_legacy_order(payload, "SELL", db, current_user)


def _place_legacy_order(
    payload: schemas.LegacyOrderCreate,
    side: str,
    db: Session,
    current_user: models.User,
):
    try:
        order = execute_market_order(
            db,
            user_id=current_user.id,
            stock_symbol=payload.stock_symbol,
            side=side,
            quantity=payload.quantity,
        )
    except OrderServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Order failed, please try again",
        )

    return _order_to_schema(order)


def _order_to_schema(order: models.Order) -> schemas.OrderOut:
    price = (
        float(order.average_fill_price)
        if order.average_fill_price is not None
        else None
    )
    total = (
        float(order.average_fill_price * order.filled_quantity)
        if order.average_fill_price is not None
        else None
    )
    return schemas.OrderOut(
        id=order.id,
        stock_symbol=order.stock.symbol,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        average_fill_price=price,
        price_per_share=price,
        total_amount=total,
        status=order.status,
        client_order_id=order.client_order_id,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@app.get("/holdings", response_model=list[schemas.HoldingOut])
def get_holdings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    holdings = (
        db.query(models.Holding)
        .filter(models.Holding.user_id == current_user.id)
        .all()
    )

    result = []
    for holding in holdings:
        stock = holding.stock
        invested_value = holding.average_buy_price * holding.quantity
        current_value = stock.current_price * holding.quantity
        profit_loss = current_value - invested_value
        profit_loss_percent = (
            (profit_loss / invested_value) * 100
            if invested_value > 0
            else 0
        )

        result.append(
            schemas.HoldingOut(
                stock_symbol=stock.symbol,
                company_name=stock.company_name,
                quantity=holding.quantity,
                average_buy_price=float(holding.average_buy_price),
                current_price=float(stock.current_price),
                current_value=float(current_value),
                invested_value=float(invested_value),
                profit_loss=float(profit_loss),
                profit_loss_percent=round(float(profit_loss_percent), 2),
            )
        )

    return result


@app.get("/orders", response_model=list[schemas.OrderOut])
def get_order_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    orders = (
        db.query(models.Order)
        .filter(models.Order.user_id == current_user.id)
        .order_by(models.Order.created_at.desc())
        .all()
    )

    return [_order_to_schema(order) for order in orders]


@app.get("/orders/{order_id}/executions", response_model=list[schemas.ExecutionOut])
def get_order_executions(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.user_id == current_user.id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return (
        db.query(models.Execution)
        .filter(models.Execution.order_id == order.id)
        .order_by(models.Execution.executed_at.asc(), models.Execution.id.asc())
        .all()
    )


@app.get("/orders/{order_id}/events", response_model=list[schemas.OrderEventOut])
def get_order_events(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id, models.Order.user_id == current_user.id)
        .first()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return (
        db.query(models.OrderEvent)
        .filter(models.OrderEvent.order_id == order.id)
        .order_by(models.OrderEvent.created_at.asc(), models.OrderEvent.id.asc())
        .all()
    )

