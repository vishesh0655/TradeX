# Configuration

Never commit .env values or credentials.

| Variable name/group | Purpose | Used by |
|---|---|---|
| DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD | PostgreSQL URL | database.py and Alembic env.py |
| JWT secret/algorithm/expiry settings | JWT signing | security.py |
| Google client settings | Google credential verification | auth route and frontend Login.jsx |
| Firebase/project settings | provider verification/client initialization | backend auth and firebase.js |
| VITE_API_URL | frontend API base URL | api/client.js |
| VITE_GOOGLE_CLIENT_ID | Google Identity Services client id | Login.jsx |
| paper-price update token | protects paper price update | main.py |

Only names/purposes are documented. Exact deployed names for JWT/Firebase/backend Google configuration should be checked in local configuration without copying values into version control.
