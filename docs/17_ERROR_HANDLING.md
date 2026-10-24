# Error handling

Expected failures use FastAPI HTTPException or service/domain error conversion. Unexpected exceptions reach the generic handler in main.py, are logged, and return HTTP 500 with Internal server error.

Actual error categories include:

- duplicate registration, invalid local credentials, invalid provider credentials;
- invalid/expired JWT or inactive user;
- absent/inactive stock and watchlist errors;
- invalid order terms, quantity, and type-dependent price fields;
- insufficient paper funds/shares and reservation conflicts;
- order ownership, invalid status transitions, cancel/modify eligibility;
- fee estimate and protected price-update authorization failures.

The frontend turns response details into ApiError, distinguishes network failures, clears auth on 401, and gives retry affordances on data pages.
