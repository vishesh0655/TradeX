import os
import logging
import hmac
from datetime import datetime
import firebase_admin
from firebase_admin import auth as firebase_auth
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi import Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app import models, schemas
from app.security import hash_password, verify_password, create_access_token, get_current_user
from app.services.order_service import (
    execute_market_order,
    order_service,
    OrderServiceError,
)
from app.services.accounting_service import accounting_service
from app.services.portfolio_valuation import portfolio_valuation_service
from app.services.trading_queries import trading_query_service, TradingQueryError
from app.services.fee_engine import fee_engine
from app.services.market_data import market_price_provider
from app.services.paper_price_update import (
    PaperPriceUpdateError,
    paper_price_update_service,
)
from fastapi import FastAPI
from sqlalchemy import text

from app.database import engine

app = FastAPI(
    title="TradeX Paper Trading API",
    description=(
        "TradeX is an educational paper-trading platform. Orders, cash, fills, "
        "and portfolio values are simulated; this API does not connect to a "
        "broker, exchange, bank, or real-money payment service."
    ),
    version="1.0.0",
)
logger = logging.getLogger(__name__)
PAPER_AUTH_RESPONSES = {
    401: {"description": "Authentication is required"},
    403: {"description": "The authenticated user does not own this resource"},
    404: {"description": "The requested resource was not found"},
    409: {"description": "The paper order conflicts with its current state"},
}


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    """Return a stable client error body without leaking implementation details."""
    logger.exception("Unhandled API error for %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


if not firebase_admin._apps:
    firebase_admin.initialize_app()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Limit", "X-Offset"],
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


def _set_page_headers(response: Response, *, total: int, limit: int, offset: int) -> None:
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)


def _raise_query_error(exc: TradingQueryError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get(
    "/stocks",
    tags=["Paper market"],
    summary="List active simulated instruments",
    description="Returns current stored paper-market prices; this endpoint does not generate or fetch market prices.",
    responses={400: {"description": "Invalid page parameters"}},
)
def list_stocks(
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    search: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    try:
        stocks, total = trading_query_service.list_stocks(
            db, limit=limit, offset=offset, search=search
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    _set_page_headers(response, total=total, limit=limit, offset=offset)
    return {"stocks": [
        {
            "symbol": stock.symbol,
            "company_name": stock.company_name,
            "current_price": float(market_price_provider.get_quote(stock).price),
        }
        for stock in stocks
    ]}


@app.get(
    "/stocks/{symbol}/quote",
    tags=["Paper market"],
    summary="Get a stored paper-market quote",
    description="Returns the configured TradeX paper-market price; this endpoint does not fetch external market data.",
    responses={404: {"description": "Instrument not found"}},
)
def get_stock_quote(symbol: str, db: Session = Depends(get_db)):
    try:
        stock = trading_query_service.get_quote(db, symbol=symbol)
    except TradingQueryError as exc:
        _raise_query_error(exc)
    quote = market_price_provider.get_quote(stock)
    return {
        "symbol": stock.symbol,
        "company_name": stock.company_name,
        "price": quote.price,
        "updated_at": quote.observed_at,
        "data_mode": "SIMULATED",
    }


def require_paper_price_update_token(
    token: str | None = Header(default=None, alias="X-TradeX-Price-Token"),
) -> None:
    configured_token = os.getenv("TRADEX_PAPER_PRICE_UPDATE_TOKEN", "").strip()
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Trusted paper price updates are not configured",
        )
    supplied_token = token or ""
    if not hmac.compare_digest(
        supplied_token.encode("utf-8"), configured_token.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid paper price update token",
        )


@app.post(
    "/internal/paper-prices/{symbol}",
    response_model=schemas.PaperPriceUpdateOut,
    tags=["Internal paper market"],
    summary="Update a stored paper quote and evaluate open orders",
    description=(
        "Accepts an explicitly supplied paper price from a trusted internal "
        "source, stores it, and evaluates open paper orders transactionally. "
        "This endpoint does not generate prices or access external market data."
    ),
    responses={
        401: {"description": "The internal price update token is invalid"},
        404: {"description": "Instrument not found"},
        409: {"description": "Instrument is not tradable"},
        422: {"description": "Invalid price"},
        503: {"description": "Trusted price updates are not configured"},
    },
)
def update_paper_price(
    symbol: str,
    payload: schemas.PaperPriceUpdateRequest,
    db: Session = Depends(get_db),
    _authorized: None = Depends(require_paper_price_update_token),
):
    try:
        return paper_price_update_service.update_price(
            db, symbol=symbol, price=payload.price
        )
    except PaperPriceUpdateError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@app.get("/wallet", response_model=schemas.WalletOut, tags=["Paper account"], description="Read the authenticated user's virtual wallet. No real-money balance is supported.", responses=PAPER_AUTH_RESPONSES)
def get_wallet(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        summary = trading_query_service.get_wallet_summary(
            db, user_id=current_user.id
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    return schemas.WalletOut(**summary)


@app.get("/wallet/transactions", response_model=list[schemas.WalletTransactionOut], tags=["Paper account"], description="Read this user's simulated wallet ledger. Results are paginated.", responses=PAPER_AUTH_RESPONSES)
def get_wallet_transactions(
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    transaction_type: str | None = Query(default=None, max_length=30),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        rows, total = trading_query_service.list_wallet_transactions(
            db, user_id=current_user.id, limit=limit, offset=offset,
            transaction_type=transaction_type, created_from=created_from,
            created_to=created_to,
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    _set_page_headers(response, total=total, limit=limit, offset=offset)
    return rows


@app.post(
    "/fees/estimate",
    response_model=schemas.FeeEstimateOut,
    tags=["Paper orders"],
    summary="Estimate simulated paper-trading fees",
    description="Estimates the configured virtual trading charges for an order notional. This does not submit an order.",
    responses={401: {"description": "Authentication is required"}, 422: {"description": "Invalid estimate request"}},
)
def estimate_order_fees(
    payload: schemas.FeeEstimateRequest,
    current_user: models.User = Depends(get_current_user),
):
    del current_user  # Authentication scopes access to account trading tools.
    estimate = fee_engine.estimate_order(
        side=payload.side.value,
        gross_notional=payload.gross_notional,
    )
    return schemas.FeeEstimateOut(**estimate)


@app.get("/watchlist", response_model=list[schemas.WatchlistOut], tags=["Paper account"], description="Lists only this authenticated user's saved paper-market instruments.", responses=PAPER_AUTH_RESPONSES)
def get_watchlist(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = trading_query_service.list_watchlist(db, user_id=current_user.id)
    return [
        schemas.WatchlistOut(
            symbol=stock.symbol,
            company_name=stock.company_name,
            current_price=market_price_provider.get_quote(stock).price,
            created_at=item.created_at,
        )
        for item, stock in rows
    ]


@app.post("/watchlist", response_model=schemas.WatchlistOut, status_code=status.HTTP_201_CREATED, tags=["Paper account"], description="Adds a simulated-market instrument to the authenticated user's watchlist.", responses=PAPER_AUTH_RESPONSES)
def add_watchlist_item(
    payload: schemas.WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        item, stock = trading_query_service.add_watchlist_item(
            db, user_id=current_user.id, symbol=payload.symbol
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    return schemas.WatchlistOut(
        symbol=stock.symbol,
        company_name=stock.company_name,
        current_price=market_price_provider.get_quote(stock).price,
        created_at=item.created_at,
    )


@app.delete("/watchlist/{symbol}", status_code=status.HTTP_204_NO_CONTENT, tags=["Paper account"], description="Removes an instrument from the authenticated user's watchlist.", responses=PAPER_AUTH_RESPONSES)
def delete_watchlist_item(
    symbol: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        trading_query_service.remove_watchlist_item(
            db, user_id=current_user.id, symbol=symbol
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
@app.post("/register", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def register_user(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    try:
        normalized_email = str(payload.email).strip().lower()
        existing_user = db.query(models.User).filter(models.User.email == normalized_email).first()
        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        new_user = models.User(
            name=payload.name.strip(),
            email=normalized_email,
            password_hash=hash_password(payload.password),
        )
        db.add(new_user)
        db.flush()
        wallet = accounting_service.initialize_wallet(db, user_id=new_user.id)
        db.commit()
        db.refresh(new_user)
        return schemas.UserOut(
            id=new_user.id,
            name=new_user.name,
            email=new_user.email,
            wallet_balance=float(wallet.available_cash),
        )
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Registration transaction failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed",
        ) from exc
@app.post("/login", response_model=schemas.Token)
def login_user(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == str(payload.email).strip().lower()).first()

    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

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

            accounting_service.initialize_wallet(db, user_id=user.id)

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

        accounting_service.initialize_wallet(db, user_id=user.id)

        identity = models.UserIdentity(
            user_id=user.id,
            provider="email",
            provider_subject=firebase_uid,
        )

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

            accounting_service.initialize_wallet(db, user_id=user.id)

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
    return schemas.UserOut(**trading_query_service.get_user_summary(current_user))
@app.post(
    "/orders",
    response_model=schemas.OrderOut,
    status_code=status.HTTP_201_CREATED,
    tags=["Paper orders"],
    summary="Create a paper order",
    description="Accepts and settles only simulated orders using virtual funds; no broker or exchange is contacted.",
    responses=PAPER_AUTH_RESPONSES,
)
def place_order(
    payload: schemas.OrderCreate,
    response: Response,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        order = order_service.place_order(
            db,
            user_id=current_user.id,
            stock_symbol=payload.stock_symbol,
            side=payload.side,
            order_type=payload.order_type,
            quantity=payload.quantity,
            limit_price=payload.limit_price,
            stop_price=payload.stop_price,
            client_order_id=payload.client_order_id,
        )
        if getattr(order, "idempotency_replay", False):
            response.status_code = status.HTTP_200_OK

    except OrderServiceError as exc:

        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        )

    except HTTPException:
        raise

    return schemas.OrderOut(
        id=order.id,
        stock_symbol=order.stock.symbol,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        remaining_quantity=order.remaining_quantity,
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
        stop_triggered=order.stop_triggered,
        triggered_at=order.triggered_at,
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
            detail="Internal server error",
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
        remaining_quantity=order.remaining_quantity,
        average_fill_price=price,
        price_per_share=price,
        total_amount=total,
        status=order.status,
        client_order_id=order.client_order_id,
        limit_price=order.limit_price,
        stop_price=order.stop_price,
        stop_triggered=order.stop_triggered,
        triggered_at=order.triggered_at,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@app.get("/holdings", response_model=list[schemas.HoldingOut], tags=["Paper account"], description="Returns the authenticated user's simulated positions and valuation.", responses=PAPER_AUTH_RESPONSES)
def get_holdings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        holdings = trading_query_service.get_holdings(db, user_id=current_user.id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return [schemas.HoldingOut(**holding) for holding in holdings]


@app.get("/portfolio", response_model=schemas.PortfolioOut, tags=["Paper account"], description="Returns simulated portfolio valuation for the authenticated user.", responses=PAPER_AUTH_RESPONSES)
def get_portfolio(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        return portfolio_valuation_service.get_portfolio(
            db, user_id=current_user.id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/orders", response_model=list[schemas.OrderOut], tags=["Paper orders"], description="Lists only the authenticated user's paper orders. Results are paginated and filterable.", responses=PAPER_AUTH_RESPONSES)
def get_order_history(
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status"),
    symbol: str | None = Query(default=None, max_length=20),
    side: str | None = Query(default=None),
    order_type: str | None = Query(default=None),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        orders, total = trading_query_service.list_orders(
            db, user_id=current_user.id, limit=limit, offset=offset,
            status=status_filter, symbol=symbol, side=side, order_type=order_type,
            created_from=created_from, created_to=created_to,
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    _set_page_headers(response, total=total, limit=limit, offset=offset)
    return [_order_to_schema(order) for order in orders]


@app.get("/orders/{order_id}", response_model=schemas.OrderOut, tags=["Paper orders"], description="Returns one of the authenticated user's paper orders.", responses=PAPER_AUTH_RESPONSES)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        order = trading_query_service.get_order(
            db, user_id=current_user.id, order_id=order_id
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    return _order_to_schema(order)


@app.post("/orders/{order_id}/cancel", response_model=schemas.OrderOut, tags=["Paper orders"], description="Cancels an eligible paper order and releases its remaining virtual reservation.", responses=PAPER_AUTH_RESPONSES)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        order = order_service.cancel_order(db, user_id=current_user.id, order_id=order_id)
    except OrderServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _order_to_schema(order)


@app.patch("/orders/{order_id}", response_model=schemas.OrderOut, tags=["Paper orders"], description="Modifies eligible paper-order terms and recalculates virtual reservations.", responses=PAPER_AUTH_RESPONSES)
def modify_order(
    order_id: int,
    payload: schemas.OrderModify,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        order = order_service.modify_order(
            db,
            user_id=current_user.id,
            order_id=order_id,
            changes=payload.model_dump(exclude_unset=True),
        )
    except OrderServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _order_to_schema(order)


@app.get("/orders/{order_id}/executions", response_model=list[schemas.ExecutionOut], tags=["Paper orders"], description="Lists simulated executions for an order owned by the authenticated user. Results are paginated.", responses=PAPER_AUTH_RESPONSES)
def get_order_executions(
    order_id: int,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    executed_from: datetime | None = None,
    executed_to: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        rows, total = trading_query_service.list_executions(
            db, user_id=current_user.id, order_id=order_id, limit=limit,
            offset=offset, executed_from=executed_from, executed_to=executed_to,
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    _set_page_headers(response, total=total, limit=limit, offset=offset)
    return rows


@app.get("/orders/{order_id}/events", response_model=list[schemas.OrderEventOut], tags=["Paper orders"], description="Lists immutable audit events for an order owned by the authenticated user. Results are paginated.", responses=PAPER_AUTH_RESPONSES)
def get_order_events(
    order_id: int,
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = Query(default=None, max_length=40),
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        rows, total = trading_query_service.list_order_events(
            db, user_id=current_user.id, order_id=order_id, limit=limit,
            offset=offset, event_type=event_type, created_from=created_from,
            created_to=created_to,
        )
    except TradingQueryError as exc:
        _raise_query_error(exc)
    _set_page_headers(response, total=total, limit=limit, offset=offset)
    return rows

