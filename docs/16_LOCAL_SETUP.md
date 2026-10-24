# Local setup

## Backend

~~~text
cd backend
python -m venv .venv
# activate the environment in your shell
python -m pip install -r requirements.txt
# create .env using the required variable names; do not commit it
alembic upgrade head
uvicorn app.main:app --reload
~~~

FastAPI documentation is normally at /docs while it runs.

## Frontend

~~~text
cd frontend
npm install
npm run dev
~~~

Set Vite values needed by firebase.js, Login.jsx, and api/client.js. Never put server database/JWT secrets in frontend environment variables.
