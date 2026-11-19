"""Run with: QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v"""

import copy, json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from core import ROOT, Store, default_profile, validate, build_packets, encode, feature
from usb_device import Device, USBError


class ProtocolTests(unittest.TestCase):
    def test_vendor_vectors(self):
        vectors = json.loads((ROOT / "tests/vendor-vectors.json").read_text())
        for v in vectors:
            with self.subTest(mode=v["profile"]["light_mode"]):
                self.assertEqual(
                    [[t, p.hex()] for t, p in build_packets(v["profile"])], v["packets"]
                )

    def test_cycle_actions_use_vendor_named_actions(self):
        # Independent semantic fixture: original action IDs 6 (dpi_cycle_text)
        # and 50 (light_mode_switch_text), not IDs inferred from our wire map.
        p = default_profile()
        p["macros"] = [
            dict(
                id="1" * 32,
                name="Copy",
                repeat=1,
                events=[
                    dict(key="C", kind="down", delay=50),
                    dict(key="C", kind="up", delay=50),
                ],
            )
        ]
        p["buttons"][3] = dict(macro="1" * 32, mode="count")
        packets = build_packets(p, ("buttons",))
        self.assertEqual(packets[1][1][20:28], bytes.fromhex("070003000b000000"))
        self.assertEqual(packets[1][1][12:16], bytes.fromhex("09000100"))
        expected = json.loads((ROOT / "tests/cycle-actions-vector.json").read_text())
        self.assertEqual([[k, b.hex()] for k, b in packets], expected)

    def test_scoped_apply(self):
        for group, allowed in [
            ("performance", {1, 11, 16, 17, 8}),
            ("light", {12, 13, 16, 8}),
            ("buttons", {18, 8}),
        ]:
            packets = build_packets(default_profile(), (group,))
            self.assertEqual(packets[-1], ("feature", feature(8, 170, 204, 238)))
            self.assertTrue(all(b[0] in allowed for t, b in packets if t == "feature"))

    def test_validation_prevents_invalid_usb(self):
        for key, value in [
            ("dpi", [0] * 6),
            ("dpi_count", 0),
            ("selected_dpi", 6),
            ("rate", 8000),
            ("buttons", ["off"] * 7),
            ("color", "#garbage"),
            ("macros", [{}]),
        ]:
            p = default_profile()
            p[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_packets(p)

    def test_no_device(self):
        with patch("usb_device.discover", return_value=[]), self.assertRaises(USBError):
            with Device():
                pass

    def test_access_error(self):
        with patch(
            "usb_device.discover", return_value=[{"accessible": False}]
        ), self.assertRaises(USBError):
            with Device():
                pass

    def test_transport_preflights_all_packets(self):
        d = Device()
        d.lib = MagicMock()
        for bad in [("out", b"bad"), ("feature", bytes(8)), ("unknown", bytes(32))]:
            with self.assertRaises(USBError):
                d.send([("feature", feature(1, 1)), bad])
            d.lib.libusb_control_transfer.assert_not_called()

    def test_short_usb_transfer_is_reported(self):
        d = Device()
        d.lib = MagicMock()
        d.lib.libusb_control_transfer.return_value = 7
        with self.assertRaisesRegex(USBError, "Неполная"):
            d.send([("feature", feature(1, 1))])

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profiles.json"
            s = Store(path)
            s.current["dpi"][0] = 1600
            s.save()
            self.assertEqual(Store(path).current["dpi"][0], 1600)
            path.write_text("{corrupted")
            with self.assertRaises(ValueError):
                Store(path)
            self.assertEqual(path.read_text(), "{corrupted")


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        from app import STYLE

        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def test_edit_reload_and_no_implicit_usb(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp, patch("app.Device") as usb:
            w = Window(Path(tmp) / "profiles.json")
            w.show()
            self.app.processEvents()
            w.tab(1)
            w.dpi_sliders[0].setValue(16)
            self.assertEqual(w.p["dpi"][0], 1600)
            self.assertEqual(w.dpi_values[0].value(), 1600)
            w.dpi_count.setValue(1)
            self.assertEqual(w.p["selected_dpi"], 0)
            w.tab(2)
            w.light_modes[8].click()
            w.sliders["brightness"].setValue(200)
            self.assertEqual(w.p["light_mode"], 8)
            w.set_button(5, "dpi_down")
            self.assertEqual(w.p["buttons"][5], "dpi_down")
            w.add_profile()
            w.choose_profile(0)
            self.assertEqual(w.p["dpi"][0], 1600)
            self.assertEqual(w.p["brightness"], 200)
            w.p["macros"].append(
                dict(
                    id="a" * 32,
                    name="Тест",
                    repeat=1,
                    events=[
                        dict(key="A", kind="down", delay=10),
                        dict(key="A", kind="up", delay=10),
                    ],
                )
            )
            w.refresh_macros()
            w.tab(3)
            self.assertEqual(w.table.rowCount(), 2)
            w.save()
            w.close()
            usb.assert_not_called()
            saved = Store(Path(tmp) / "profiles.json")
            self.assertEqual(saved.current["macros"][0]["name"], "Тест")

    def test_recorder_releases_keys(self):
        from app import Recorder
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest

        r = Recorder(None, 10)
        r.show()
        QTest.keyPress(r, Qt.Key.Key_A)
        r.accept()
        self.assertEqual(
            [(e["key"], e["kind"]) for e in r.events], [("A", "down"), ("A", "up")]
        )


if __name__ == "__main__":
    unittest.main()
