# Testing

Tests are in backend/tests/ and use unittest.

| Test file | Intent |
|---|---|
| test_api_end_to_end.py, test_api_contracts.py | API journeys/contracts |
| test_order_domain.py | order validation |
| test_order_service.py, test_order_modify_cancel.py | creation/change/cancel |
| test_order_lifecycle.py, test_order_evaluation.py | transitions/events/evaluation |
| test_execution_engine.py, test_accounting.py | fills, cash, positions, P&L |
| test_risk_engine.py | cash/share risks |
| test_paper_price_update.py, test_market_data.py | stored paper prices |
| test_trading_queries.py | user-scoped query behavior |

Run from backend/:

~~~text
python -m unittest discover -s tests
~~~

No coverage-report configuration was found, so no coverage percentage is claimed.
