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
        order = SimpleNamespace(id=11, status="OPEN", updated_at=None)

        transition_order(db, order, "FILLED", metadata={"filled_quantity": 3})

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].event_type, "ORDER_FILLED")
        self.assertEqual(db.added[0].metadata_json["from"], "OPEN")
        self.assertEqual(db.added[0].metadata_json["filled_quantity"], 3)

    def test_terminal_order_cannot_reopen(self):
        db = RecordingSession()
        order = SimpleNamespace(id=12, status="FILLED", updated_at=None)

        with self.assertRaises(InvalidOrderTransition):
            transition_order(db, order, "OPEN")

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(db.added, [])

    def test_partial_fill_can_complete(self):
        db = RecordingSession()
        order = SimpleNamespace(id=13, status="PARTIALLY_FILLED", updated_at=None)

        transition_order(db, order, "FILLED")

        self.assertEqual(order.status, "FILLED")
        self.assertEqual(db.added[0].metadata_json["to"], "FILLED")


if __name__ == "__main__":
    unittest.main()
