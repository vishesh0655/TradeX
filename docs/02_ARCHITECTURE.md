# Architecture

~~~mermaid
flowchart LR
  UI[React UI] --> Client[api/client.js]
  Client --> API[FastAPI main.py]
  API --> Auth[JWT and provider verification]
  API --> Services[Order/accounting/query services]
  Services --> ORM[SQLAlchemy ORM]
  ORM --> DB[(PostgreSQL)]
~~~

## Layers

1. React components display state and send requests.
2. api/client.js handles URL prefix, JSON, JWT, and 401 behavior.
3. main.py maps HTTP routes to schemas and services.
4. domain/orders.py and services/ contain order/business logic.
5. SQLAlchemy models and a session persist state in PostgreSQL.

Order-related work uses the SQLAlchemy session as a unit of work. Service errors roll back; constraints and immutable event/ledger design add integrity protections.
