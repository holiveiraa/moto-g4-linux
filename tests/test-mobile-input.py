#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Regression checks for contact lifetime and input-event loss (no hardware writes)."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('inputd', Path(__file__).parents[1] / 'native/moto-inputd.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TouchTests(unittest.TestCase):
    def setUp(self):
        self.touch = module.Contacts()

    def frame(self, *events):
        out = []
        for code, value in events:
            out.extend(self.touch.feed(3, code, value))
        return out + self.touch.feed(0, 0, 0)

    def test_tap_drag_release(self):
        down = self.frame((57, 10), (53, 120), (54, 840))
        self.assertEqual(down, [(1, 330, 1), (3, 0, 120), (3, 1, 840), (0, 0, 0)])
        drag = self.frame((53, 124))
        self.assertNotIn((1, 330, 1), drag)
        self.assertIn((3, 1, 840), drag)
        self.assertEqual(self.frame((57, -1)), [(1, 330, 0), (0, 0, 0)])

    def test_second_finger_cannot_click_other_key(self):
        self.frame((57, 10), (53, 10), (54, 20))
        second = self.frame((47, 1), (57, 11), (53, 900), (54, 1500))
        self.assertIn((3, 0, 10), second)
        self.assertNotIn((3, 0, 900), second)
        self.assertEqual(self.frame((47, 0), (57, -1)), [(1, 330, 0), (0, 0, 0)])
        self.assertEqual(self.frame((47, 1), (53, 950)), [])
        self.frame((57, -1))
        self.assertIn((1, 330, 1), self.frame((57, 12), (53, 30), (54, 50)))

    def test_lost_events_release_pointer(self):
        self.frame((57, 10), (53, 120), (54, 840))
        self.assertEqual(self.touch.feed(0, 3, 0), [(1, 330, 0), (0, 0, 0)])
        self.assertEqual(self.frame((53, 600)), [])
        self.assertFalse(self.touch.down)
        self.assertIn((1, 330, 1), self.frame((57, 11), (53, 50), (54, 60)))


class GestureTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.g = module.Gestures(self.actions.append)
        self.g.set_state({'top': 160, 'bottom': 1124, 'menu': False})

    def down(self, x=200, y=500):
        return [(1, 330, 1), (3, 0, x), (3, 1, y), (0, 0, 0)]

    def test_keyboard_never_delayed(self):
        event = self.down(y=1400)
        self.assertEqual(self.g.feed(event, 1), event)

    def test_terminal_tap_replayed_once(self):
        down = self.down()
        up = [(1, 330, 0), (0, 0, 0)]
        self.assertEqual(self.g.feed(down, 1), [])
        self.assertEqual(self.g.feed(up, 1.1), down + up)
        self.assertEqual(self.actions, [])

    def test_drag_scroll_does_not_click_or_type(self):
        self.g.feed(self.down(), 1)
        self.assertEqual(self.g.feed([(3, 1, 580), (0, 0, 0)], 1.1), [])
        self.assertEqual(self.actions, ['scroll-up', 'scroll-up'])
        self.assertEqual(self.g.feed([(1, 330, 0), (0, 0, 0)], 1.2), [])

    def test_hold_selects_and_menu_uses_normal_pointer(self):
        event = self.down()
        self.g.feed(event, 1)
        self.assertEqual(self.g.held(1.5), event)
        up = [(1, 330, 0), (0, 0, 0)]
        self.assertEqual(self.g.feed(up, 1.6), up)
        self.g.set_state({'top': 160, 'bottom': 1124, 'menu': True})
        self.assertEqual(self.g.feed(event, 2), event)


if __name__ == '__main__':
    unittest.main()
