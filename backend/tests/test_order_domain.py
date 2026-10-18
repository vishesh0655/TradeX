import unittest
from decimal import Decimal

from pydantic import ValidationError

from app.domain.orders import OrderValidationError, validate_fill_quantities, validate_order_terms
from app import models
from app.schemas import OrderCreate


class OrderDomainTests(unittest.TestCase):
    def test_order_audit_events_are_immutable_in_orm(self):
        event = models.OrderEvent(order_id=1, event_type="ORDER_CREATED")
        with self.assertRaisesRegex(ValueError, "immutable"):
            models._reject_order_event_mutation(None, None, event)

    def test_each_supported_order_type_accepts_valid_terms(self):
        valid_orders = [
            ("MARKET", None, None),
            ("LIMIT", Decimal("100.00"), None),
            ("STOP", None, Decimal("100.00")),
            ("STOP_LIMIT", Decimal("98.00"), Decimal("100.00")),
        ]
        for order_type, limit_price, stop_price in valid_orders:
            with self.subTest(order_type=order_type):
                side, normalized_type, limit, stop = validate_order_terms(
                    side="BUY",
                    order_type=order_type,
                    quantity=2,
                    limit_price=limit_price,
                    stop_price=stop_price,
                )
                self.assertEqual(side, "BUY")
                self.assertEqual(normalized_type, order_type)
                self.assertEqual(limit, limit_price)
                self.assertEqual(stop, stop_price)

    def test_market_rejects_prices(self):
        for kwargs in (
            {"limit_price": Decimal("10")},
            {"stop_price": Decimal("10")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(OrderValidationError):
                validate_order_terms(side="BUY", order_type="MARKET", quantity=1, **kwargs)

    def test_limit_requires_only_a_positive_limit_price(self):
        cases = [
            {"limit_price": None},
            {"limit_price": Decimal("0")},
            {"limit_price": Decimal("10"), "stop_price": Decimal("9")},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(OrderValidationError):
                validate_order_terms(side="BUY", order_type="LIMIT", quantity=1, **kwargs)

    def test_stop_requires_only_a_positive_stop_price(self):
        cases = [
            {"stop_price": None},
            {"stop_price": Decimal("-1")},
            {"stop_price": Decimal("10"), "limit_price": Decimal("9")},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(OrderValidationError):
                validate_order_terms(side="BUY", order_type="STOP", quantity=1, **kwargs)

    def test_stop_limit_requires_two_positive_prices(self):
        cases = [
            {"limit_price": Decimal("10"), "stop_price": None},
            {"limit_price": None, "stop_price": Decimal("10")},
            {"limit_price": Decimal("0"), "stop_price": Decimal("10")},
            {"limit_price": Decimal("10"), "stop_price": Decimal("-1")},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(OrderValidationError):
                validate_order_terms(side="BUY", order_type="STOP_LIMIT", quantity=1, **kwargs)

    def test_invalid_order_type_side_and_quantity_are_rejected(self):
        with self.assertRaises(OrderValidationError):
            validate_order_terms(side="BUY", order_type="TRAILING", quantity=1)
        with self.assertRaises(OrderValidationError):
            validate_order_terms(side="HOLD", order_type="MARKET", quantity=1)
        for quantity in (0, -1, 1.5, True):
            with self.subTest(quantity=quantity), self.assertRaises(OrderValidationError):
                validate_order_terms(side="BUY", order_type="MARKET", quantity=quantity)

    def test_schema_uses_the_same_order_contract(self):
        order = OrderCreate(
            stock_symbol=" tcs ",
            side="BUY",
            order_type="STOP_LIMIT",
            quantity=2,
            limit_price="98.00",
            stop_price="100.00",
        )
        self.assertEqual(order.order_type, "STOP_LIMIT")
        with self.assertRaises(ValidationError):
            OrderCreate(stock_symbol="TCS", side="BUY", order_type="MARKET", quantity=1, limit_price=10)
        with self.assertRaises(ValidationError):
            OrderCreate(stock_symbol="TCS", side="BUY", order_type="LIMIT", quantity=1)
        with self.assertRaises(ValidationError):
            OrderCreate(stock_symbol="TCS", side="BUY", order_type="MARKET", quantity=0)

    def test_fill_quantity_must_be_within_order_quantity(self):
        validate_fill_quantities(5, 0)
        validate_fill_quantities(5, 5)
        for filled_quantity in (-1, 6, 1.5, True):
            with self.subTest(filled_quantity=filled_quantity), self.assertRaises(OrderValidationError):
                validate_fill_quantities(5, filled_quantity)

    def test_quantity_and_price_fit_database_precision(self):
        for quantity in (2_147_483_648,):
            with self.subTest(quantity=quantity), self.assertRaises(OrderValidationError):
                validate_order_terms(side="BUY", order_type="MARKET", quantity=quantity)
        for price in (Decimal("0.001"), Decimal("1000000000000.00")):
            with self.subTest(price=price), self.assertRaises(OrderValidationError):
                validate_order_terms(
                    side="BUY", order_type="LIMIT", quantity=1, limit_price=price
                )
        # Redundant trailing zeroes do not lose precision when stored as NUMERIC(14, 2).
        validate_order_terms(
            side="BUY", order_type="LIMIT", quantity=1, limit_price=Decimal("1.230")
        )
