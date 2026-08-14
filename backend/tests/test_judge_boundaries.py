from __future__ import annotations

import unittest

from app.judge import in_spec


class JudgeBoundaryTests(unittest.TestCase):
    def test_equal_to_minimum_fails(self) -> None:
        self.assertFalse(in_spec(10.0, 10.0, 20.0))

    def test_equal_to_maximum_fails(self) -> None:
        self.assertFalse(in_spec(20.0, 10.0, 20.0))

    def test_value_strictly_between_limits_passes(self) -> None:
        self.assertTrue(in_spec(15.0, 10.0, 20.0))

    def test_single_sided_limits_are_also_strict(self) -> None:
        self.assertFalse(in_spec(10.0, 10.0, None))
        self.assertFalse(in_spec(20.0, None, 20.0))
        self.assertTrue(in_spec(10.1, 10.0, None))
        self.assertTrue(in_spec(19.9, None, 20.0))

    def test_missing_measurement_remains_unknown(self) -> None:
        self.assertIsNone(in_spec(None, 10.0, 20.0))


if __name__ == '__main__':
    unittest.main()
