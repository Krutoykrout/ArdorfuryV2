import copy, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from core import ROOT, Store, default_profile, validate, build_packets
from macros import *


def macro(events=None):
    return dict(
        id="1" * 32,
        name="Test",
        repeat=1,
        events=(
            events
            if events is not None
            else [
                dict(key="A", kind="down", delay=100),
                dict(key="A", kind="up", delay=100),
            ]
        ),
    )


def assigned():
    p = default_profile()
    m = macro()
    p["macros"] = [m]
    p["buttons"][4] = {"macro": m["id"], "mode": "count"}
    return p


class MacroTests(unittest.TestCase):
    def test_vendor_vectors(self):
        for v in json.loads((ROOT / "tests/macro-vectors.json").read_text()):
            self.assertEqual(
                [[t, p.hex()] for t, p in build_packets(v["profile"], ("buttons",))],
                v["packets"],
            )

    def test_exact_known_block(self):
        self.assertEqual(
            compile_macro(macro()), bytes.fromhex("00010b048b04").ljust(128, b"\0")
        )

    def test_long_delay_boundary(self):
        m = macro()
        m["events"][0]["delay"] = 1271
        self.assertEqual(macro_body(m).hex(), "000101040001003f8b04")

    def test_empty_unbalanced_and_unknown(self):
        for events in [
            [],
            [dict(key="A", kind="up", delay=0)],
            [dict(key="A", kind="down", delay=0)],
            [dict(key="NotAKey", kind="down", delay=0)],
            macro()["events"][:1] * 2,
        ]:
            with self.subTest(events=events), self.assertRaises(ValueError):
                compile_macro(macro(events))

    def test_byte_capacity_no_truncation(self):
        events = macro()["events"] * 20
        for i in range(11):
            events[i] = dict(events[i], delay=65535)
        self.assertEqual(len(macro_body(macro(events))), 126)
        events[11] = dict(events[11], delay=65535)
        with self.assertRaisesRegex(ValueError, "130/128"):
            compile_macro(macro(events))

    def test_event_limit(self):
        self.assertEqual(len(macro_body(macro(macro()["events"] * 20))), 82)
        with self.assertRaises(ValueError):
            compile_macro(macro(macro()["events"] * 21))

    def test_chord_and_modifiers(self):
        events = [
            dict(key=k, kind=t, delay=10)
            for k, t in [("Ctrl", "down"), ("C", "down"), ("C", "up"), ("Ctrl", "up")]
        ]
        self.assertEqual(macro_body(macro(events)).hex(), "000101e00106810681e0")

    def test_migration_and_references(self):
        p = default_profile()
        m = macro()
        m.pop("id")
        p["macros"] = [m]
        a = validate(p)
        b = validate(p)
        self.assertEqual(a["macros"][0]["id"], b["macros"][0]["id"])
        a["buttons"][4] = {"macro": a["macros"][0]["id"], "mode": "hold"}
        a["macros"][0]["name"] = "Renamed"
        validate(a)
        a["macros"].clear()
        with self.assertRaises(ValueError):
            validate(a)

    def test_same_macro_two_slots_and_remove(self):
        p = assigned()
        p["buttons"][3] = dict(p["buttons"][4], mode="toggle")
        packets = build_packets(p, ("buttons",))
        headers = [b for t, b in packets if t == "feature" and b[0] == 19]
        self.assertEqual([h[1] for h in headers], [1, 2])
        table = packets[1][1]
        self.assertEqual(table[12:20], bytes.fromhex("0901010009000200"))
        p["buttons"][3] = "back"
        p["buttons"][4] = "forward"
        self.assertFalse(
            any(
                t == "feature" and b[0] == 19 for t, b in build_packets(p, ("buttons",))
            )
        )

    def test_draft_does_not_block_unrelated_settings(self):
        p = assigned()
        p["macros"][0]["events"] = []
        build_packets(p, ("light",))
        build_packets(p, ("performance",))
        with self.assertRaises(ValueError):
            build_packets(p, ("buttons",))

    def test_invalid_modes_and_macro_ids(self):
        for action in [
            dict(macro="bad", mode="count"),
            dict(macro="1" * 32, mode="unknown"),
        ]:
            p = assigned()
            p["buttons"][4] = action
            with self.assertRaises(ValueError):
                build_packets(p, ("buttons",))


class MacroUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_binding_preserves_ids_and_blocks_delete(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp, patch("app.Device") as usb:
            w = Window(Path(tmp) / "profiles.json")
            w.p["macros"] = [macro()]
            w.refresh_macros()
            w.tab(3)
            w.bind_macro(4, "1" * 32, "hold")
            self.assertIn("Макрос", w.key_buttons[4].text())
            self.assertIn("Кнопки: 5", w.macro_status.text())
            w.delete_macro()
            self.assertEqual(len(w.p["macros"]), 1)
            w.set_button(4, "forward")
            w.delete_macro()
            self.assertEqual(w.p["macros"], [])
            w.close()
            usb.assert_not_called()

    def test_bad_macro_never_starts_usb_worker(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp, patch("app.Sender") as sender, patch(
            "app.QMessageBox.warning"
        ):
            w = Window(Path(tmp) / "profiles.json")
            w.store.profiles[0] = assigned()
            w.p["macros"][0]["events"] = []
            w.load()
            w.tab(3)
            w.apply()
            sender.assert_not_called()
            w.close()

    def test_recorder_capacity_and_modifiers(self):
        from app import Recorder

        r = Recorder(None, 10)
        for _ in range(20):
            r.append("A", "down")
            r.append("A", "up")
        r.append("B", "down")
        self.assertTrue(r.limit_reached)
        self.assertEqual(len(r.events), 40)
        compile_macro(macro(r.events))

    def test_refused_binding_and_renamed_label(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp:
            w = Window(Path(tmp) / "profiles.json")
            w.p["macros"] = [macro()]
            w.refresh_macros()
            self.assertFalse(w.bind_macro(0, "1" * 32, "count"))
            self.assertEqual(w.p["buttons"][0], "left")
            self.assertIn("левым кликом", w.message.text())
            self.assertTrue(w.bind_macro(4, "1" * 32, "count"))
            w.p["macros"][0]["name"] = "Новое имя"
            w.macros_changed()
            self.assertIn("Новое имя", w.key_buttons[4].text())
            w.close()

    def test_old_profile_migrates_without_losing_settings(self):
        from core import atomic_json

        with tempfile.TemporaryDirectory() as tmp:
            p = assigned()
            p["buttons"][4] = "forward"
            p["macros"][0].pop("id")
            p["dpi"][0] = 1800
            path = Path(tmp) / "profiles.json"
            atomic_json(path, dict(version=1, active=0, profiles=[p]))
            store = Store(path)
            mid = store.current["macros"][0]["id"]
            store.save()
            again = Store(path)
            self.assertEqual(again.current["dpi"][0], 1800)
            self.assertEqual(again.current["macros"][0]["id"], mid)

    def test_mouse_macro_usage_names(self):
        # Original key-name routine 0x402380 labels f3 Backward_Button, f4 Forward_Button.
        self.assertEqual(key_code("MouseBack"), 0xF3)
        self.assertEqual(key_code("MouseForward"), 0xF4)

    def test_key_dialog_has_supported_keys(self):
        from app import EventDialog

        d = EventDialog(None, 10)
        self.assertEqual(d.key.count(), len(KEYS))
        d.close()


if __name__ == "__main__":
    unittest.main()
