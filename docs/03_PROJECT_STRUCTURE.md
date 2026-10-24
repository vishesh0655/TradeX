# Project structure

~~~text
TradeX/
├─ backend/
│  ├─ app/
│  │  ├─ main.py       FastAPI routes and HTTP error mapping
│  │  ├─ database.py   engine, SessionLocal, Base, get_db()
│  │  ├─ models.py     ORM tables and constraints
│  │  ├─ schemas.py    Pydantic request/response contracts
│  │  ├─ security.py   passwords, JWT, current-user dependency
│  │  ├─ domain/       order types and validation
│  │  └─ services/     trading business logic
│  ├─ alembic/         migrations
│  ├─ tests/           unittest test suite
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ App.jsx       application state and page switching
│  │  ├─ api/          HTTP wrappers
│  │  ├─ pages/        screen components
│  │  └─ components/   layout, reusable UI, trading ticket
│  └─ package.json
└─ docs/
~~~

database.py reads database environment variables, creates a psycopg SQLAlchemy URL and engine, creates SessionLocal/Base, and yields/then closes sessions through get_db(). main.py and protected routes depend on it.
