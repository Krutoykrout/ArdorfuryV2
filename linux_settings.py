"""GNOME mouse preferences for the current user; independent of USB profiles.

Uses the installed GSettings schema and executable. No root, shell invocation,
input injection or device reconfiguration is needed.
"""

import math
import os
import shutil
import subprocess

SCHEMA = "org.gnome.desktop.peripherals.mouse"
KEYS = ("speed", "accel-profile", "double-click")
ACCELERATION = {
    "default": "Как в системе",
    "flat": "Без ускорения",
    "adaptive": "Адаптивное",
}


class SettingsError(RuntimeError):
    pass


class GnomeMouseSettings:
    def __init__(self, runner=None, desktop=None, executable=None):
        self.runner = runner or subprocess.run
        self.desktop = (
            os.environ.get("XDG_CURRENT_DESKTOP", "") if desktop is None else desktop
        )
        self.executable = (
            shutil.which("gsettings") if executable is None else executable
        )

    def _check_environment(self):
        if "gnome" not in self.desktop.lower().split(":"):
            raise SettingsError(
                "Эти настройки пока доступны только в GNOME / Ubuntu GNOME."
            )
        if not self.executable:
            raise SettingsError("Не найдена системная программа gsettings.")

    def _run(self, *args):
        self._check_environment()
        try:
            result = self.runner(
                [self.executable, *args],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise SettingsError(
                "Не удалось обратиться к настройкам Linux: " + str(error)
            ) from error
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[:350]
            raise SettingsError("Настройки Linux недоступны: " + detail)
        return result.stdout.strip()

    def read(self):
        try:
            speed = float(self._run("get", SCHEMA, "speed"))
            acceleration = self._run("get", SCHEMA, "accel-profile").strip("'")
            interval = int(self._run("get", SCHEMA, "double-click"))
        except ValueError as error:
            raise SettingsError(
                "Linux вернул неизвестный формат настроек мыши."
            ) from error
        values = {
            "speed": speed,
            "accel-profile": acceleration,
            "double-click": interval,
        }
        self._validate(values)
        return values

    def writable(self):
        return {key for key in KEYS if self._run("writable", SCHEMA, key) == "true"}

    @staticmethod
    def _validate(changes):
        if not isinstance(changes, dict) or set(changes) - set(KEYS):
            raise SettingsError("Неизвестная настройка Linux.")
        for key, value in changes.items():
            valid = False
            if key == "speed":
                valid = (
                    type(value) in (int, float)
                    and math.isfinite(value)
                    and -1 <= value <= 1
                )
            elif key == "accel-profile":
                valid = isinstance(value, str) and value in ACCELERATION
            elif key == "double-click":
                valid = type(value) is int and 0 <= value <= 2147483647
            if not valid:
                raise SettingsError("Недопустимое значение: " + key)

    def _set(self, key, value):
        wire = repr(value) if isinstance(value, str) else str(value)
        self._run("set", SCHEMA, key, wire)

    def apply(self, changes):
        """Write only edited fields, verify, and attempt rollback on any failure."""
        self._validate(changes)
        before = self.read()
        changes = {key: value for key, value in changes.items() if value != before[key]}
        if not changes:
            return before
        writable = self.writable()
        if set(changes) - writable:
            raise SettingsError(
                "Часть настроек заблокирована администратором; ничего не изменено."
            )
        attempted = []
        try:
            for key, value in changes.items():
                attempted.append(key)  # A timed-out write may have reached the service.
                self._set(key, value)
            after = self.read()
            if any(after[key] != value for key, value in changes.items()):
                raise SettingsError("Linux не подтвердил новые значения.")
            return after
        except SettingsError as error:
            rollback_errors = []
            for key in reversed(attempted):
                try:
                    self._set(key, before[key])
                except SettingsError:
                    rollback_errors.append(key)
            try:
                restored = self.read()
                if any(restored[key] != before[key] for key in attempted):
                    rollback_errors.append("verification")
            except SettingsError:
                rollback_errors.append("read")
            tail = (
                " Не удалось полностью восстановить значения; нажми «Прочитать из Linux»."
                if rollback_errors
                else " Прежние значения восстановлены."
            )
            raise SettingsError(str(error) + tail) from error
