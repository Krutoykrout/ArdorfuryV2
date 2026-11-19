import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from linux_settings import GnomeMouseSettings, SettingsError, KEYS


class FakeGSettings:
    def __init__(self):
        self.values = {"speed": 0.1234, "accel-profile": "default", "double-click": 400}
        self.calls = []
        self.locked = set()
        self.fail_key = None
        self.ignore_key = None
        self.time_out_after_write = False

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        op, schema, key = argv[1:4]
        assert schema == "org.gnome.desktop.peripherals.mouse"
        value = ""
        if op == "get":
            value = repr(self.values[key])
        elif op == "writable":
            value = "false" if key in self.locked else "true"
        elif op == "set":
            if key == self.fail_key:
                self.fail_key = None
                return subprocess.CompletedProcess(
                    argv, 1, "", "Simulated commit failure"
                )
            if key != self.ignore_key:
                value = argv[4]
                self.values[key] = (
                    value.strip("'")
                    if key == "accel-profile"
                    else float(value) if key == "speed" else int(value)
                )
            if self.time_out_after_write:
                self.time_out_after_write = False
                raise subprocess.TimeoutExpired(argv, 3)
        return subprocess.CompletedProcess(argv, 0, str(value), "")

    def writes(self):
        return [call for call in self.calls if call[1] == "set"]


def backend(fake):
    return GnomeMouseSettings(
        runner=fake, desktop="ubuntu:GNOME", executable="/usr/bin/gsettings"
    )


class LinuxSettingsTests(unittest.TestCase):
    def test_read_has_no_writes(self):
        fake = FakeGSettings()
        service = backend(fake)
        self.assertEqual(service.read(), fake.values)
        self.assertEqual(service.writable(), set(KEYS))
        self.assertEqual(fake.writes(), [])

    def test_only_changed_fields_written_and_read_back(self):
        fake = FakeGSettings()
        service = backend(fake)
        result = service.apply({"double-click": 550})
        self.assertEqual(
            result, {"speed": 0.1234, "accel-profile": "default", "double-click": 550}
        )
        self.assertEqual([call[3] for call in fake.writes()], ["double-click"])

    def test_failure_rolls_back_prior_write(self):
        fake = FakeGSettings()
        service = backend(fake)
        before = dict(fake.values)
        fake.fail_key = "accel-profile"
        with self.assertRaisesRegex(SettingsError, "Прежние значения восстановлены"):
            service.apply({"speed": 0.7, "accel-profile": "flat"})
        self.assertEqual(fake.values, before)

    def test_timed_out_write_is_also_rolled_back(self):
        fake = FakeGSettings()
        service = backend(fake)
        before = dict(fake.values)
        fake.time_out_after_write = True
        with self.assertRaises(SettingsError):
            service.apply({"speed": -0.8})
        self.assertEqual(fake.values, before)

    def test_zero_exit_without_commit_is_not_success(self):
        fake = FakeGSettings()
        service = backend(fake)
        fake.ignore_key = "speed"
        with self.assertRaisesRegex(SettingsError, "не подтвердил"):
            service.apply({"speed": 0.7})

    def test_locked_field_prevents_all_writes(self):
        fake = FakeGSettings()
        service = backend(fake)
        fake.locked.add("double-click")
        with self.assertRaises(SettingsError):
            service.apply({"speed": 0.8, "double-click": 500})
        self.assertEqual(fake.writes(), [])

    def test_bad_values_and_unsupported_desktop_do_not_write(self):
        fake = FakeGSettings()
        service = backend(fake)
        for changes in [
            {"speed": float("nan")},
            {"speed": True},
            {"speed": 2},
            {"accel-profile": "bad"},
            {"double-click": -1},
            {"other": 1},
        ]:
            with self.assertRaises(SettingsError):
                service.apply(changes)
        self.assertEqual(fake.calls, [])
        other = GnomeMouseSettings(runner=fake, desktop="KDE", executable="gsettings")
        with self.assertRaisesRegex(SettingsError, "GNOME"):
            other.read()
        self.assertEqual(fake.calls, [])


class LinuxSettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def test_system_values_are_independent_of_profile_and_usb(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp, patch("app.Device") as usb:
            fake = FakeGSettings()
            w = Window(Path(tmp) / "profiles.json", linux_settings=backend(fake))
            self.assertEqual(w.linux_double_click.value(), 400)
            w.linux_double_click.setValue(650)
            w.add_profile()
            w.choose_profile(0)
            self.assertEqual(w.linux_double_click.value(), 650)
            self.assertEqual(fake.writes(), [])
            w.apply_linux_settings()
            self.assertTrue(w.linux_worker.wait(5000))
            self.app.processEvents()
            self.assertEqual(fake.values["double-click"], 650)
            self.assertEqual(fake.values["speed"], 0.1234)
            self.assertEqual(w.linux_dirty, set())
            self.assertFalse(w.linux_apply_btn.isEnabled())
            w.close()
            usb.assert_not_called()

    def test_linux_edits_are_not_sent_by_hardware_apply(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp, patch("app.Sender") as sender:
            fake = FakeGSettings()
            w = Window(Path(tmp) / "profiles.json", linux_settings=backend(fake))
            w.tab(1)
            w.linux_speed.setValue(70)
            w.apply()
            self.assertEqual(fake.writes(), [])
            sender.assert_called_once()
            w.worker = None
            w.close()

    def test_reload_discards_draft_and_shows_external_changes(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeGSettings()
            w = Window(Path(tmp) / "profiles.json", linux_settings=backend(fake))
            w.linux_double_click.setValue(700)
            fake.values["double-click"] = 450
            w.read_linux_settings()
            self.assertEqual(w.linux_double_click.value(), 450)
            self.assertFalse(w.linux_dirty)
            self.assertEqual(fake.writes(), [])
            w.close()

    def test_unsupported_desktop_preserves_hardware_ui(self):
        from app import Window

        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeGSettings()
            service = GnomeMouseSettings(
                runner=fake, desktop="KDE", executable="gsettings"
            )
            w = Window(Path(tmp) / "profiles.json", linux_settings=service)
            self.assertFalse(w.linux_speed.isEnabled())
            self.assertTrue(w.apply_btn.isEnabled())
            self.assertTrue(w.dpi_values[0].isEnabled())
            w.close()
            self.assertEqual(fake.calls, [])

    def test_double_click_is_a_button_action_and_keeps_a_left_click(self):
        from app import Window
        from core import ROOT, build_packets

        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeGSettings()
            w = Window(Path(tmp) / "profiles.json", linux_settings=backend(fake))
            self.assertFalse(w.set_button(0, "double_click"))
            self.assertTrue(w.set_button(4, "double_click"))
            self.assertIn("Двойной клик", w.key_buttons[4].text())
            expected = json.loads((ROOT / "tests/double-click-vector.json").read_text())
            self.assertEqual(
                [[k, b.hex()] for k, b in build_packets(w.p, ("buttons",))], expected
            )
            w.close()


if __name__ == "__main__":
    unittest.main()
