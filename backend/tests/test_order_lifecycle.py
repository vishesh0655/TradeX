import unittest
from types import SimpleNamespace

from app.services.order_lifecycle import (
    InvalidOrderTransition,
    transition_order,
)


class RecordingSession:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


class OrderLifecycleTests(unittest.TestCase):
    def test_open_order_can_fill_and_records_event(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=11,
            status="OPEN",
            quantity=3,
            filled_quantity=3,
            updated_at=None,
        )

        transition_order(db, order, "FILLED", metadata={"filled_quantity": 3})

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].event_type, "ORDER_FILLED")
        self.assertEqual(db.added[0].metadata_json["from"], "OPEN")
        self.assertEqual(db.added[0].metadata_json["filled_quantity"], 3)

    def test_terminal_order_cannot_reopen(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=12,
            status="FILLED",
            quantity=3,
            filled_quantity=3,
            updated_at=None,
        )

        with self.assertRaises(InvalidOrderTransition):
            transition_order(db, order, "OPEN")

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(db.added, [])

    def test_partial_fill_can_complete(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=13,
            status="PARTIALLY_FILLED",
            quantity=3,
            filled_quantity=3,
            updated_at=None,
        )

        transition_order(db, order, "FILLED")

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(db.added[0].metadata_json["to"], "FILLED")

    def test_partial_status_requires_a_partial_fill(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=14,
            status="OPEN",
            quantity=3,
            filled_quantity=0,
            updated_at=None,
        )

        with self.assertRaises(InvalidOrderTransition):
            transition_order(db, order, "PARTIALLY_FILLED")

        self.assertEqual(order.status, "OPEN")
        self.assertEqual(db.added, [])

    def test_transition_rejects_filled_quantity_above_order_quantity(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=15,
            status="OPEN",
            quantity=3,
            filled_quantity=4,
            updated_at=None,
        )

        with self.assertRaises(InvalidOrderTransition):
            transition_order(db, order, "FILLED")

        self.assertEqual(order.status, "OPEN")
        self.assertEqual(db.added, [])

    def test_rejected_order_cannot_be_reopened(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=16,
            status="REJECTED",
            quantity=1,
            filled_quantity=0,
            updated_at=None,
        )

        with self.assertRaises(InvalidOrderTransition):
            transition_order(db, order, "OPEN")

    def test_cancel_pending_can_only_become_cancelled(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=17,
            status="CANCEL_PENDING",
            quantity=3,
            filled_quantity=1,
            updated_at=None,
        )

        transition_order(db, order, "CANCELLED")

        self.assertEqual(order.status, "CANCELLED")
        self.assertEqual(db.added[0].metadata_json["from"], "CANCEL_PENDING")

    def test_transition_metadata_cannot_override_state_change(self):
        db = RecordingSession()
        order = SimpleNamespace(
            id=18,
            status="NEW",
            quantity=1,
            filled_quantity=0,
            updated_at=None,
        )

        transition_order(db, order, "OPEN", metadata={"from": "FILLED", "to": "FILLED"})

        self.assertEqual(db.added[0].metadata_json["from"], "NEW")
        self.assertEqual(db.added[0].metadata_json["to"], "OPEN")


if __name__ == "__main__":
    unittest.main()
