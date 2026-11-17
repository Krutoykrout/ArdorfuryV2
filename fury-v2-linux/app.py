#!/usr/bin/env python3
"""Fury V2 Linux — native Qt UI using the installed vendor's local artwork."""

import argparse, copy, json, os, subprocess, sys, time, uuid
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QEvent, QSize, QLockFile
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QSlider,
    QSpinBox,
    QRadioButton,
    QButtonGroup,
    QFrame,
    QStackedWidget,
    QColorDialog,
    QMenu,
    QMessageBox,
    QFileDialog,
    QInputDialog,
    QDialog,
    QVBoxLayout,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QListWidget,
    QCheckBox,
    QAbstractItemView,
)
from core import (
    ROOT,
    Store,
    default_profile,
    validate,
    atomic_json,
    ACTIONS,
    LIGHTS,
    build_packets,
    action_label,
)
from usb_device import discover, Device
from macros import (
    KEYS,
    NAMES,
    MODES,
    MAX_EVENTS,
    canonical_key,
    macro_body,
    EVDEV_TO_HID,
)

LOCAL_SKIN = ROOT / "assets/skins"
USER_SKIN = (
    Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    / "fury-v2-linux/skins"
)
SKIN = LOCAL_SKIN if (LOCAL_SKIN / "bk/bk.jpg").exists() else USER_SKIN


def mouse_pixmap(filename="mouse.png"):
    pix = QPixmap(str(SKIN / "mouse" / filename))
    return pix if not pix.isNull() else QPixmap(str(ROOT / "assets/mouse.svg"))


STYLE = """
QWidget { color: #eeeeee; font-family: Arial, "Liberation Sans"; font-size: 15px; }
QDialog, QMessageBox, QInputDialog { background: #111111; }
QLabel { background: transparent; border: none; }
QPushButton { background: #080808; border: 1px solid #5f5f5f; padding: 3px; }
QPushButton:hover, QPushButton:checked { color: #ed1c24; border-color: #ed1c24; }
QPushButton:pressed { background: #231012; }
QPushButton:disabled, QRadioButton:disabled, QCheckBox:disabled { color: #646464; }
QLineEdit,QSpinBox,QComboBox { background: #000; border: 1px solid #5f5f5f; padding: 5px; selection-background-color: #ed1c24; }
QLineEdit:focus,QSpinBox:focus,QComboBox:focus { border-color: #ed1c24; }
QComboBox QAbstractItemView { background: #090909; selection-background-color: #a0151a; }
QComboBox::drop-down { border-left: 1px solid #5f5f5f; width: 25px; }
QSlider::groove:horizontal { background: #585858; height: 5px; }
QSlider::sub-page:horizontal { background: #ed1c24; }
QSlider::handle:horizontal { background: #ed1c24; width: 13px; margin: -6px 0; }
QSlider:disabled::handle:horizontal { background: #555; }
QRadioButton { spacing: 7px; background: transparent; }
QRadioButton::indicator { width: 11px; height: 11px; border: 1px solid #888; border-radius: 6px; background: #000; }
QRadioButton::indicator:checked { background: #ed1c24; border-color: #ed1c24; }
QRadioButton:checked { color: #ed1c24; }
QMenu { background: #101010; border: 1px solid #5f5f5f; }
QMenu::item { padding: 8px 20px; }
QMenu::item:selected { background: #9e151c; }
QListWidget,QTableWidget { background: #050505; border: 1px solid #5f5f5f; gridline-color: #353535; selection-background-color: #881017; }
QHeaderView { background: #111111; }
QTableCornerButton::section { background: #353535; border: 1px solid #5f5f5f; }
QHeaderView::section { background: #353535; color: white; padding: 8px; border: 1px solid #5f5f5f; }
QToolTip { background: #222; color: #eee; border: 1px solid #ed1c24; padding: 5px; }
QScrollBar:vertical { background: #111; width: 8px; }
QScrollBar::handle:vertical { background: #555; min-height: 25px; }
"""


STYLE += (
    'QComboBox::down-arrow {image:url("'
    + str(ROOT / "assets/down.svg")
    + '");width:12px;height:10px;}'
    "QSpinBox::up-button {subcontrol-origin:border;subcontrol-position:top right;width:18px;border-left:1px solid #555;}"
    "QSpinBox::down-button {subcontrol-origin:border;subcontrol-position:bottom right;width:18px;border-left:1px solid #555;}"
    'QSpinBox::up-arrow {image:url("'
    + str(ROOT / "assets/up.svg")
    + '");width:12px;height:10px;}'
    'QSpinBox::down-arrow {image:url("'
    + str(ROOT / "assets/down.svg")
    + '");width:12px;height:10px;}'
)


def place(widget, x, y, w, h):
    widget.setGeometry(x, y, w, h)
    return widget


def label(parent, text, x, y, w, h=28, style=None):
    l = place(QLabel(text, parent), x, y, w, h)
    if style:
        l.setStyleSheet(style)
    return l


def button(parent, text, x, y, w, h, callback=None):
    b = place(QPushButton(text, parent), x, y, w, h)
    if callback:
        b.clicked.connect(callback)
    return b


def panel(parent, x, y, w, h, title=None):
    p = place(QFrame(parent), x, y, w, h)
    p.setObjectName("panel")
    p.setStyleSheet("QFrame#panel {background: #000; border: 1px solid #5f5f5f;}")
    if title:
        label(p, title, 1, 1, w - 2, 39, "background: #5f5f5f; padding-left: 20px;")
    return p


class RedSlider(QSlider):
    def paintEvent(self, event):
        p = QPainter(self)
        enabled = self.isEnabled()
        y = self.height() // 2
        fraction = (self.value() - self.minimum()) / max(
            1, self.maximum() - self.minimum()
        )
        x = 7 + int(fraction * (self.width() - 14))
        p.fillRect(0, y - 2, self.width(), 5, QColor("#454545"))
        p.fillRect(0, y - 2, x, 5, QColor("#ed1c24" if enabled else "#555555"))
        p.fillRect(x - 6, y - 8, 13, 16, QColor("#ed1c24" if enabled else "#777777"))


class SkinButton(QPushButton):
    def __init__(self, parent, text, x, y, w, h, skin, callback=None):
        super().__init__(text, parent)
        place(self, x, y, w, h)
        self.skin = skin
        self.hover = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            self.clicked.connect(callback)

    def enterEvent(self, event):
        self.hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        state = 3 if self.isDown() or self.isChecked() else 2 if self.hover else 1
        pix = QPixmap(str(SKIN / f"{self.skin}_{state}.png"))
        if pix.isNull():
            pix = QPixmap(str(SKIN / f"{self.skin}_1.png"))
        if not pix.isNull():
            p.drawPixmap(self.rect(), pix)
        else:
            p.fillRect(self.rect(), QColor("#15191e"))
            p.setPen(QColor("#ed1c24" if self.hover else "#5f5f5f"))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
            if not self.text():
                p.setPen(QColor("#eeeeee"))
                p.drawText(
                    self.rect(),
                    Qt.AlignmentFlag.AlignCenter,
                    {
                        "min": "−",
                        "close": "×",
                        "add": "+",
                        "delete": "−",
                        "menu": "…",
                    }.get(self.skin, ""),
                )
        p.setPen(QColor("#ed1c24" if self.hover or self.isChecked() else "#eeeeee"))
        p.setFont(self.font())
        p.drawText(
            self.rect().adjusted(5, 0, -5, 0),
            Qt.AlignmentFlag.AlignCenter,
            self.fontMetrics().elidedText(
                self.text(), Qt.TextElideMode.ElideRight, self.width() - 10
            ),
        )


class Sender(QThread):
    result = pyqtSignal(bool, str)

    def __init__(self, packets):
        super().__init__()
        self.packets = packets

    def run(self):
        try:
            with Device() as d:
                d.send(self.packets)
            self.result.emit(
                True,
                "Команды переданы мыши. Обратное чтение настроек пока не поддерживается.",
            )
        except Exception as e:
            self.result.emit(
                False,
                "Передача не завершена: "
                + str(e)
                + "\nЧасть команд могла быть отправлена. Можно повторить применение.",
            )


class Recorder(QDialog):
    def __init__(self, parent, delay):
        super().__init__(parent)
        self.setWindowTitle("Запись макроса")
        self.resize(540, 280)
        self.events = []
        self.down = set()
        self.last = None
        self.delay = delay
        self.limit_reached = False
        box = QVBoxLayout(self)
        hint = QLabel(
            "Нажимай клавиши или кнопки мыши в этом окне.\nEsc — закончить. Запись вне окна не ведётся.\nНа X11 записываются физические клавиши независимо от раскладки."
        )
        hint.setWordWrap(True)
        box.addWidget(hint)
        self.count = QLabel("Событий: 0 / 40")
        box.addWidget(self.count)
        self.error = QLabel("")
        self.error.setWordWrap(True)
        box.addWidget(self.error)
        done = QPushButton("Готово")
        done.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        done.clicked.connect(self.accept)
        box.addWidget(done)

    def append(self, name, kind):
        if kind == "down":
            if name in self.down:
                return
            if len(self.events) + len(self.down) + 2 > MAX_EVENTS:
                self.limit_reached = True
                self.accept()
                return
            self.down.add(name)
        else:
            if name not in self.down:
                return
            self.down.remove(name)
        now = time.monotonic()
        # Recorded inter-event time is attached to the preceding event.
        if self.delay < 0 and self.events and self.last is not None:
            self.events[-1]["delay"] = min(65535, round((now - self.last) * 1000))
        self.events.append(
            dict(key=name, kind=kind, delay=10 if self.delay < 0 else self.delay)
        )
        self.last = now
        self.count.setText(f"Событий: {len(self.events)} / 40")

    def event(self, e):
        if e.type() == QEvent.Type.ShortcutOverride:
            e.accept()
            return True
        if e.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            if e.isAutoRepeat():
                return True
            if e.key() == Qt.Key.Key_Escape:
                if e.type() == QEvent.Type.KeyPress:
                    self.accept()
                return True
            name = None
            if QApplication.platformName() == "xcb" and e.nativeScanCode():
                name = NAMES.get(EVDEV_TO_HID.get(e.nativeScanCode() - 8))
            if name is None:
                modifiers = {
                    Qt.Key.Key_Control: "LCtrl",
                    Qt.Key.Key_Shift: "LShift",
                    Qt.Key.Key_Alt: "LAlt",
                    Qt.Key.Key_Meta: "LWin",
                    Qt.Key.Key_AltGr: "RAlt",
                }
                text = modifiers.get(
                    e.key(),
                    QKeySequence(e.key()).toString(
                        QKeySequence.SequenceFormat.PortableText
                    ),
                )
                try:
                    name = canonical_key(text)
                except ValueError:
                    self.error.setText("Эта клавиша не поддерживается: " + text)
                    return True
            self.append(name, "down" if e.type() == QEvent.Type.KeyPress else "up")
            return True
        if e.type() == QEvent.Type.WindowDeactivate and self.isVisible():
            self.accept()
        return super().event(e)

    def mousePressEvent(self, e):
        self.mouse_event(e, "down")

    def mouseReleaseEvent(self, e):
        self.mouse_event(e, "up")

    def mouse_event(self, e, kind):
        name = {
            Qt.MouseButton.LeftButton: "MouseLeft",
            Qt.MouseButton.RightButton: "MouseRight",
            Qt.MouseButton.MiddleButton: "MouseMiddle",
            Qt.MouseButton.BackButton: "MouseBack",
            Qt.MouseButton.ForwardButton: "MouseForward",
        }.get(e.button())
        if name:
            self.append(name, kind)

    def accept(self):
        for key in sorted(self.down):
            self.events.append(dict(key=key, kind="up", delay=10))
        self.down.clear()
        super().accept()


class MacroBindingDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Назначить макрос")
        self.resize(450, 210)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Кнопка мыши"))
        self.button = QComboBox()
        self.button.addItems(
            [
                f"{i+1}. {action_label(a,parent.p)}"
                for i, a in enumerate(parent.p["buttons"])
            ]
        )
        self.button.setCurrentIndex(4)
        layout.addWidget(self.button)
        layout.addWidget(QLabel("Режим воспроизведения"))
        self.mode = QComboBox()
        for key, (title, _) in MODES.items():
            self.mode.addItem(title, key)
        layout.addWidget(self.mode)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class EventDialog(QDialog):
    def __init__(self, parent, delay):
        super().__init__(parent)
        self.setWindowTitle("Добавить событие")
        self.resize(420, 230)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Клавиша / кнопка мыши"))
        self.key = QComboBox()
        self.key.addItems(KEYS)
        layout.addWidget(self.key)
        self.kind = QComboBox()
        self.kind.addItems(["Нажать и отпустить", "Только нажать", "Только отпустить"])
        layout.addWidget(self.kind)
        self.delay = QSpinBox()
        self.delay.setRange(0, 65535)
        self.delay.setSuffix(" мс")
        self.delay.setValue(delay)
        layout.addWidget(self.delay)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class Window(QWidget):
    def __init__(self, data_path):
        super().__init__()
        self.loading = True
        self.worker = None
        self.drag = None
        self.setWindowTitle("Fury V2 Linux")
        self.setWindowIcon(QIcon(str(ROOT / "assets/icon.svg")))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(1280, 750)
        self.background = QPixmap(str(SKIN / "bk/bk.jpg"))
        self.store = Store(data_path)
        self.changed_groups = set()
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save)
        self.nav = []
        for i, (name, x) in enumerate(
            [
                ("Основные", 90),
                ("Расширенные", 290),
                ("Подсветка", 770),
                ("Макросы", 950),
            ]
        ):
            b = button(self, name, x, 15, 150, 64, lambda _, n=i: self.tab(n))
            b.setCheckable(True)
            glow = SKIN / "guangyun.png"
            glow_style = (
                (
                    'background-image:url("'
                    + str(glow)
                    + '");background-position:center;background-repeat:no-repeat;'
                )
                if glow.is_file()
                else ""
            )
            b.setStyleSheet(
                "QPushButton{border:none;background:transparent;font-size:17px;} QPushButton:checked,QPushButton:hover{color:#ed1c24;"
                + glow_style
                + "}"
            )
            self.nav.append(b)
        SkinButton(self, "", 1165, 18, 22, 22, "min", self.showMinimized).setToolTip(
            "Свернуть"
        )
        SkinButton(self, "", 1192, 18, 22, 22, "close", self.close).setToolTip(
            "Закрыть"
        )
        self.sidebar = panel(self, 51, 99, 320, 546)
        label(self.sidebar, "Выберите профиль", 10, 10, 298, 34)
        self.combo = place(QComboBox(self.sidebar), 10, 49, 298, 34)
        self.combo.currentIndexChanged.connect(self.choose_profile)
        for n, x, tip, fn in [
            ("add", 10, "Новый профиль", self.add_profile),
            ("delete", 112, "Удалить профиль", self.delete_profile),
            ("menu", 214, "Импорт и экспорт", self.profile_menu),
        ]:
            SkinButton(self.sidebar, "", x, 93, 94, 34, n, fn).setToolTip(tip)
        label(self.sidebar, "Переименовать профиль", 10, 137, 298, 34)
        self.name_edit = place(QLineEdit(self.sidebar), 10, 176, 298, 34)
        self.name_edit.setMaxLength(30)
        self.name_edit.editingFinished.connect(self.rename_profile)
        SkinButton(
            self.sidebar, "Сбросить", 10, 240, 298, 34, "reset", self.reset_profile
        )
        self.apply_btn = SkinButton(
            self.sidebar, "Применить", 10, 404, 298, 34, "reset", self.apply
        )
        self.profile_hint = label(
            self.sidebar,
            "Локальный профиль\nНастройки мыши ещё не прочитаны",
            11,
            455,
            296,
            60,
            "color:#999;font-size:12px;",
        )
        self.profile_hint.setWordWrap(True)
        self.pages = place(QStackedWidget(self), 386, 99, 839, 546)
        self.build_keys()
        self.build_performance()
        self.build_light()
        self.macro_page = place(QWidget(self), 51, 99, 1174, 546)
        self.build_macros()
        self.message = label(
            self,
            "Профиль сохраняется на компьютере. «Применить» отправляет настройки открытой вкладки.",
            51,
            659,
            1174,
            30,
            "color:#a0a0a0;font-size:13px;",
        )
        self.device_label = label(
            self, "", 51, 701, 800, 24, "color:#999;font-size:13px;"
        )
        self.access_btn = button(
            self, "Настроить доступ", 1035, 696, 190, 32, self.setup_access
        )
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.detect)
        self.timer.start(3000)
        self.load()
        self.tab(0)
        self.detect()
        self.loading = False

    @property
    def p(self):
        return self.store.current

    def paintEvent(self, e):
        p = QPainter(self)
        if not self.background.isNull():
            p.drawPixmap(0, 0, self.background)
        else:
            p.fillRect(self.rect(), QColor("#0d1014"))
            p.fillRect(0, 0, self.width(), 80, QColor("#171c22"))
            p.setPen(QColor("#ed1c24"))
            p.setFont(QFont("Sans", 17, QFont.Weight.Bold))
            p.drawText(520, 35, "FURY V2")
            p.setPen(QColor("#a5adb8"))
            p.setFont(QFont("Sans", 10))
            p.drawText(538, 58, "L I N U X")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < 80:
            self.drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, e):
        self.drag = None

    def note(self, text, error=False):
        self.message.setText(text.replace("\n", " "))
        self.message.setStyleSheet(
            "color:" + ("#ed6c70" if error else "#aaaaaa") + ";font-size:13px;"
        )

    def save(self):
        try:
            self.store.save()
        except (OSError, ValueError) as e:
            self.note("Не удалось сохранить профиль: " + str(e), True)

    def change(self, key, value, group=None):
        if self.loading:
            return
        self.p[key] = value
        if group:
            self.changed_groups.add(group)
        self.save_timer.start(250)
        self.note("Изменения в локальном профиле; для мыши нажми «Применить».")

    def load(self):
        self.loading = True
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItems([p["name"] for p in self.store.profiles])
        self.combo.setCurrentIndex(self.store.active)
        self.combo.blockSignals(False)
        self.name_edit.setText(self.p["name"])
        for i, b in enumerate(self.key_buttons):
            b.setText(f'{i+1}.  {action_label(self.p["buttons"][i],self.p)}')
        self.dpi_count.setValue(self.p["dpi_count"])
        for i in range(6):
            self.dpi_sliders[i].setValue(self.p["dpi"][i] // 100)
            self.dpi_values[i].setValue(self.p["dpi"][i])
            self.dpi_radios[i].setChecked(i == self.p["selected_dpi"])
            self.dpi_radios[i].setEnabled(i < self.p["dpi_count"])
            self.dpi_sliders[i].setEnabled(i < self.p["dpi_count"])
            self.color_style(self.dpi_colors[i], self.p["dpi_colors"][i])
        self.rates[self.p["rate"]].setChecked(True)
        for key, control in self.sliders.items():
            control.setValue(self.p[key])
        self.light_modes[self.p["light_mode"]].setChecked(True)
        self.color_modes[self.p["color_mode"]].setChecked(True)
        self.color_style(self.fixed_color, self.p["color"])
        for i, b in enumerate(self.palette):
            self.color_style(b, self.p["palette"][i])
        self.refresh_macros()
        self.loading = False

    def tab(self, n):
        for i, b in enumerate(self.nav):
            b.setChecked(i == n)
        self.sidebar.setVisible(n != 3)
        self.pages.setVisible(n != 3)
        self.macro_page.setVisible(n == 3)
        if n != 3:
            self.pages.setCurrentIndex(n)
        self.current_tab = n
        if hasattr(self, "message"):
            if n == 3:
                self.note(
                    "Создай макрос, назначь кнопку, затем нажми «Записать в мышь»."
                )
            else:
                self.note(
                    "«Применить» отправляет только настройки этой вкладки. Профиль сохранён на компьютере."
                )

    def choose_profile(self, index):
        if self.loading or index < 0:
            return
        self.save_timer.stop()
        self.store.active = index
        self.changed_groups.clear()
        self.load()
        self.save()
        self.note("Выбран локальный профиль. Настройки мыши не изменены.")

    def add_profile(self):
        if len(self.store.profiles) >= 100:
            return
        self.store.profiles.append(
            default_profile(f"Профиль {len(self.store.profiles)+1}")
        )
        self.store.active = len(self.store.profiles) - 1
        self.load()
        self.save()

    def delete_profile(self):
        if len(self.store.profiles) == 1:
            self.note("Нужно оставить хотя бы один профиль.", True)
            return
        if (
            QMessageBox.question(
                self, "Удалить профиль", f'Удалить «{self.p["name"]}» с компьютера?'
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.profiles.pop(self.store.active)
        self.store.active = max(0, self.store.active - 1)
        self.load()
        self.save()

    def rename_profile(self):
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setText(self.p["name"])
            return
        self.p["name"] = name
        self.combo.setItemText(self.store.active, name)
        self.save()

    def reset_profile(self):
        if (
            QMessageBox.question(
                self,
                "Сбросить профиль",
                "Вернуть локальный профиль к заводским значениям программы? Мышь изменится после «Применить».",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.store.profiles[self.store.active] = default_profile(self.p["name"])
        self.load()
        self.save()
        self.note(
            "Локальный профиль сброшен. Для передачи выбери вкладку и нажми «Применить»."
        )

    def profile_menu(self):
        m = QMenu(self)
        m.addAction("Импорт JSON…", self.import_profile)
        m.addAction("Экспорт JSON…", self.export_profile)
        m.exec(self.sidebar.mapToGlobal(self.sidebar.rect().center()))

    def import_profile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт профиля", str(ROOT), "Профили (*.json)"
        )
        if not path:
            return
        try:
            if len(self.store.profiles) >= 100:
                raise ValueError("Не более 100 профилей.")
            if Path(path).stat().st_size > 2_000_000:
                raise ValueError("Файл слишком большой.")
            p = validate(json.loads(Path(path).read_text()))
            self.store.profiles.append(p)
            self.store.active = len(self.store.profiles) - 1
            self.load()
            self.save()
        except (ValueError, TypeError, OSError) as e:
            QMessageBox.warning(self, "Импорт", str(e))

    def export_profile(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт профиля", str(ROOT / "profile.json"), "Профили (*.json)"
        )
        if path:
            try:
                atomic_json(path, validate(self.p))
                self.note("Профиль экспортирован: " + path)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Экспорт", str(e))

    def build_keys(self):
        page = QWidget()
        self.pages.addWidget(page)
        self.mouse = place(QLabel(page), 98, 10, 296, 528)
        self.mouse.setPixmap(mouse_pixmap())
        self.key_buttons = []
        for i in range(7):
            b = SkinButton(
                page,
                "",
                516,
                10 + i * 76,
                225,
                41,
                "button",
                lambda _, n=i: self.key_menu(n),
            )
            b.installEventFilter(self)
            b.setProperty("mouseKey", i + 1)
            self.key_buttons.append(b)

    def eventFilter(self, obj, event):
        key = obj.property("mouseKey")
        if key and event.type() in (QEvent.Type.Enter, QEvent.Type.Leave):
            file = (
                f"mouse_{key}.png" if event.type() == QEvent.Type.Enter else "mouse.png"
            )
            self.mouse.setPixmap(mouse_pixmap(file))
        return super().eventFilter(obj, event)

    def key_menu(self, index):
        menu = QMenu(self)
        for key, (title, _) in ACTIONS.items():
            menu.addAction(title, lambda k=key: self.set_button(index, k))
        menu.addSeparator()
        sub = menu.addMenu("Назначить макрос")
        sub.setEnabled(bool(self.p["macros"]))
        for m in self.p["macros"]:
            modes = sub.addMenu(m["name"])
            for mode, (title, _) in MODES.items():
                modes.addAction(
                    title,
                    lambda mid=m["id"], mode=mode: self.bind_macro(index, mid, mode),
                )
        menu.exec(
            self.key_buttons[index].mapToGlobal(
                self.key_buttons[index].rect().bottomLeft()
            )
        )

    def set_button(self, index, key):
        p = copy.deepcopy(self.p)
        p["buttons"][index] = key
        try:
            validate(p)
        except ValueError as e:
            self.note(str(e), True)
            return False
        self.change("buttons", p["buttons"], "buttons")
        self.key_buttons[index].setText(f"{index+1}.  {action_label(key,self.p)}")
        self.update_macro_status()
        return True

    def bind_macro(self, index, macro_id, mode):
        return self.set_button(index, dict(macro=macro_id, mode=mode))

    def assign_macro(self):
        m = self.macro()
        if m is None:
            self.note("Сначала создай или выбери макрос.", True)
            return
        dialog = MacroBindingDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self.bind_macro(
                dialog.button.currentIndex(), m["id"], dialog.mode.currentData()
            ):
                self.note(
                    "Назначение сохранено. Нажми «Записать в мышь» для применения."
                )

    def slider(self, parent, key, title, x, y, w, lo, hi, group=None, enabled=True):
        label(parent, title, x, y, w, 24, None if enabled else "color:#777;")
        s = place(RedSlider(Qt.Orientation.Horizontal, parent), x, y + 29, w - 55, 22)
        s.setRange(lo, hi)
        s.setEnabled(enabled)
        val = label(
            parent,
            "",
            x + w - 48,
            y + 26,
            48,
            28,
            "font-size:12px;color:" + ("#eee;" if enabled else "#777;"),
        )
        s.valueChanged.connect(lambda v, k=key: self.change(k, v, group))
        s.valueChanged.connect(lambda v: val.setText(str(v)))
        self.sliders[key] = s
        label(parent, str(lo), x, y + 53, 45, 18, "font-size:11px;color:#999;")
        label(parent, str(hi), x + w - 85, y + 53, 55, 18, "font-size:11px;color:#999;")
        return s

    def build_performance(self):
        page = QWidget()
        self.pages.addWidget(page)
        self.sliders = {}
        left = panel(page, 0, 0, 400, 546, "Настройки DPI")
        self.dpi_count = place(QSpinBox(left), 290, 5, 85, 30)
        self.dpi_count.setRange(1, 6)
        self.dpi_count.valueChanged.connect(self.set_dpi_count)
        self.dpi_sliders = []
        self.dpi_values = []
        self.dpi_radios = []
        self.dpi_colors = []
        group = QButtonGroup(left)
        for i in range(6):
            y = 52 + i * 74
            r = place(QRadioButton(f"DPI {i+1}", left), 12, y, 130, 24)
            group.addButton(r, i)
            r.clicked.connect(
                lambda _, n=i: self.change("selected_dpi", n, "performance")
            )
            self.dpi_radios.append(r)
            c = button(
                left,
                "",
                248,
                y,
                22,
                22,
                lambda _, n=i: self.choose_color("dpi_colors", n),
            )
            self.dpi_colors.append(c)
            val = place(QSpinBox(left), 285, y - 2, 99, 28)
            val.setRange(200, 12400)
            val.setSingleStep(100)
            val.valueChanged.connect(lambda v, n=i: self.dpi_spin(n, v))
            self.dpi_values.append(val)
            s = place(RedSlider(Qt.Orientation.Horizontal, left), 12, y + 28, 370, 20)
            s.setRange(2, 124)
            s.valueChanged.connect(lambda v, n=i: self.dpi_slide(n, v))
            self.dpi_sliders.append(s)
            label(left, "200", 12, y + 49, 60, 16, "font-size:11px;")
            label(left, "12400", 336, y + 49, 50, 16, "font-size:11px;")
        label(
            left,
            "Выше 6200 прошивка округляет DPI с шагом 200.",
            12,
            508,
            375,
            28,
            "font-size:12px;color:#999;",
        )
        right = panel(page, 415, 0, 424, 546, "Частота опроса")
        self.rates = {}
        rate_group = QButtonGroup(right)
        for i, hz in enumerate([125, 250, 500, 1000]):
            r = place(QRadioButton(f"{hz} Гц", right), 14 + i * 100, 53, 100, 25)
            rate_group.addButton(r)
            r.clicked.connect(lambda _, v=hz: self.change("rate", v, "performance"))
            self.rates[hz] = r
        for key, title, y, lo, hi in [
            ("cursor_speed", "Скорость мыши", 105, 1, 11),
            ("scroll_speed", "Скорость прокрутки", 205, 1, 11),
            ("double_click", "Скорость двойного щелчка", 305, 0, 10),
            ("response", "Время отклика кнопки, мс", 405, 1, 100),
        ]:
            s = self.slider(right, key, title, 15, y, 390, lo, hi, enabled=False)
            s.setToolTip("Параметр ещё не перенесён в Linux; мыши не отправляется.")
        label(
            right,
            "Серые настройки пока недоступны в Linux-версии.",
            15,
            510,
            395,
            24,
            "font-size:12px;color:#999;",
        )

    def dpi_slide(self, index, v):
        self.dpi_values[index].blockSignals(True)
        self.dpi_values[index].setValue(v * 100)
        self.dpi_values[index].blockSignals(False)
        if not self.loading:
            values = self.p["dpi"].copy()
            values[index] = v * 100
            self.change("dpi", values, "performance")

    def dpi_spin(self, index, v):
        v = max(200, min(12400, round(v / 100) * 100))
        self.dpi_sliders[index].setValue(v // 100)
        if self.dpi_values[index].value() != v:
            self.dpi_values[index].setValue(v)

    def set_dpi_count(self, n):
        if self.loading:
            return
        self.p["selected_dpi"] = min(self.p["selected_dpi"], n - 1)
        self.change("dpi_count", n, "performance")
        self.load()

    def build_light(self):
        page = QWidget()
        self.pages.addWidget(page)
        left = panel(page, 0, 0, 400, 546, "Эффект подсветки")
        right = panel(page, 415, 0, 424, 546, "Настройка параметров")
        self.light_modes = []
        group = QButtonGroup(left)
        for i, title in enumerate(LIGHTS):
            r = place(QRadioButton(title, left), 18, 52 + i * 38, 375, 28)
            group.addButton(r)
            r.clicked.connect(lambda _, n=i: self.change("light_mode", n, "light"))
            self.light_modes.append(r)
        for key, title, y, hi in [
            ("brightness", "Яркость", 55, 255),
            ("frequency", "Скорость", 140, 4),
            ("length", "Длина", 225, 4),
        ]:
            self.slider(right, key, title, 20, y, 380, 0, hi, "light")
        label(
            right,
            "Настройка цвета",
            1,
            315,
            422,
            38,
            "background:#5f5f5f;padding-left:20px;",
        )
        self.color_modes = []
        cg = QButtonGroup(right)
        for i, title in enumerate(["Фиксированный", "Циклический"]):
            r = place(QRadioButton(title, right), 20 + i * 195, 366, 190, 28)
            cg.addButton(r)
            r.clicked.connect(lambda _, n=i: self.change("color_mode", n, "light"))
            self.color_modes.append(r)
        label(right, "Текущий цвет", 20, 408, 165, 28)
        self.fixed_color = button(
            right, "", 196, 406, 62, 30, lambda: self.choose_color("color")
        )
        self.palette = []
        for i in range(8):
            self.palette.append(
                button(
                    right,
                    "",
                    20 + i * 48,
                    458,
                    34,
                    34,
                    lambda _, n=i: self.choose_color("palette", n),
                )
            )
        label(
            right,
            "Доступные параметры зависят от выбранного эффекта.",
            20,
            510,
            390,
            24,
            "color:#999;font-size:12px;",
        )

    def color_style(self, b, color):
        b.setStyleSheet(
            f"QPushButton{{background:{color};border:1px solid #888;}} QPushButton:hover{{border:2px solid white;}}"
        )

    def choose_color(self, key, index=None):
        old = self.p[key] if index is None else self.p[key][index]
        c = QColorDialog.getColor(QColor(old), self, "Выбрать цвет")
        if not c.isValid():
            return
        if index is None:
            value = c.name()
        else:
            value = self.p[key].copy()
            value[index] = c.name()
        self.change(key, value, "performance" if key == "dpi_colors" else "light")
        self.load()

    def build_macros(self):
        left = panel(self.macro_page, 0, 0, 320, 546)
        right = panel(self.macro_page, 335, 0, 839, 546)
        label(left, "Список макросов", 10, 10, 298, 30)
        self.macro_list = place(QListWidget(left), 10, 49, 298, 265)
        self.macro_list.currentRowChanged.connect(self.show_macro)
        SkinButton(left, "", 10, 328, 94, 34, "add", self.add_macro).setToolTip(
            "Новый макрос"
        )
        SkinButton(left, "", 112, 328, 94, 34, "delete", self.delete_macro).setToolTip(
            "Удалить макрос"
        )
        SkinButton(left, "", 214, 328, 94, 34, "menu", self.rename_macro).setToolTip(
            "Переименовать макрос"
        )
        label(left, "Задержка между событиями", 10, 380, 298, 25)
        self.delay = place(QSpinBox(left), 10, 412, 125, 32)
        self.delay.setRange(0, 65535)
        self.delay.setValue(10)
        self.delay.setSuffix(" мс")
        self.real_delay = place(QCheckBox("Реальная", left), 155, 414, 150, 28)
        SkinButton(left, "Начать запись", 10, 475, 298, 34, "reset", self.record_macro)
        self.table = place(QTableWidget(0, 3, right), 0, 0, 839, 400)
        self.table.setHorizontalHeaderLabels(["Клавиша", "Действие", "Задержка, мс"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellChanged.connect(self.edit_event)
        label(right, "Повторений", 15, 418, 135, 32)
        self.repeat = place(QSpinBox(right), 155, 418, 95, 32)
        self.repeat.setRange(1, 999)
        self.repeat.valueChanged.connect(self.repeat_macro)
        for title, x, fn in [
            ("↑", 290, lambda: self.move_event(-1)),
            ("↓", 340, lambda: self.move_event(1)),
            ("Удалить", 395, self.delete_event),
            ("Добавить", 510, self.add_event),
        ]:
            button(right, title, x, 418, 45 if len(title) == 1 else 105, 32, fn)
        self.macro_status = label(
            right, "", 15, 457, 809, 38, "color:#aaa;font-size:12px;"
        )
        self.macro_status.setWordWrap(True)
        button(right, "Назначить кнопке", 15, 503, 195, 32, self.assign_macro)
        self.macro_apply = button(
            right, "Записать в мышь", 225, 503, 195, 32, self.apply
        )
        button(right, "Импорт / экспорт", 435, 503, 195, 32, self.macro_menu)

    def refresh_macros(self):
        idx = self.macro_list.currentRow()
        self.macro_list.blockSignals(True)
        self.macro_list.clear()
        self.macro_list.addItems([m["name"] for m in self.p["macros"]])
        self.macro_list.setCurrentRow(min(max(0, idx), len(self.p["macros"]) - 1))
        self.macro_list.blockSignals(False)
        self.show_macro()

    def macro(self):
        i = self.macro_list.currentRow()
        return self.p["macros"][i] if 0 <= i < len(self.p["macros"]) else None

    def show_macro(self, *args):
        m = self.macro()
        self.table.blockSignals(True)
        self.table.setRowCount(len(m["events"]) if m else 0)
        if m:
            for row, e in enumerate(m["events"]):
                for col, text in enumerate(
                    [
                        e["key"],
                        "Нажать" if e["kind"] == "down" else "Отпустить",
                        str(e["delay"]),
                    ]
                ):
                    self.table.setItem(row, col, QTableWidgetItem(text))
            self.repeat.blockSignals(True)
            self.repeat.setValue(m["repeat"])
            self.repeat.blockSignals(False)
        self.table.blockSignals(False)
        self.update_macro_status()

    def update_macro_status(self):
        m = self.macro()
        if m is None:
            self.macro_status.setText("Выбери макрос или создай новый кнопкой +.")
            return
        targets = [
            str(i + 1)
            for i, a in enumerate(self.p["buttons"])
            if isinstance(a, dict) and a["macro"] == m["id"]
        ]
        try:
            size = len(macro_body(m))
            text = f'{len(m["events"])} / 40 событий · {size} / 128 байт · Кнопки: ' + (
                ", ".join(targets) if targets else "не назначен"
            )
        except ValueError as e:
            text = "Не готов к записи: " + str(e)
        self.macro_status.setText(text)

    def macros_changed(self):
        self.change("macros", self.p["macros"])
        self.update_macro_status()
        for i, b in enumerate(self.key_buttons):
            b.setText(f'{i+1}.  {action_label(self.p["buttons"][i],self.p)}')
        self.note("Макрос изменён в профиле. Для применения нажми «Записать в мышь».")

    def add_macro(self):
        if len(self.p["macros"]) >= 100:
            self.note("В профиле может быть не более 100 макросов.", True)
            return
        name, ok = QInputDialog.getText(self, "Новый макрос", "Название:")
        if ok and name.strip():
            self.p["macros"].append(
                dict(id=uuid.uuid4().hex, name=name.strip()[:60], events=[], repeat=1)
            )
            self.refresh_macros()
            self.macro_list.setCurrentRow(len(self.p["macros"]) - 1)
            self.macros_changed()

    def delete_macro(self):
        if self.macro() is not None:
            mid = self.macro()["id"]
            if any(
                isinstance(a, dict) and a["macro"] == mid for a in self.p["buttons"]
            ):
                self.note(
                    "Сначала замени назначения этого макроса во вкладке «Основные».",
                    True,
                )
                return
            self.p["macros"].pop(self.macro_list.currentRow())
            self.refresh_macros()
            self.macros_changed()

    def rename_macro(self):
        m = self.macro()
        if m is None:
            return
        name, ok = QInputDialog.getText(
            self, "Имя макроса", "Название:", text=m["name"]
        )
        if ok and name.strip():
            m["name"] = name.strip()[:60]
            self.refresh_macros()
            self.macros_changed()

    def record_macro(self):
        if self.macro() is None:
            self.add_macro()
        m = self.macro()
        if m is None:
            return
        dialog = Recorder(
            self, -1 if self.real_delay.isChecked() else self.delay.value()
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if len(m["events"]) + len(dialog.events) > 1000:
            self.note("В локальном макросе не может быть больше 1000 событий.", True)
            return
        m["events"].extend(dialog.events)
        self.show_macro()
        self.macros_changed()
        if dialog.limit_reached:
            self.note(
                "Запись остановлена на лимите 40 событий. Нажатые клавиши отпущены."
            )

    def repeat_macro(self, n):
        if not self.loading and self.macro() is not None:
            self.macro()["repeat"] = n
            self.macros_changed()

    def edit_event(self, row, col):
        m = self.macro()
        if m is None:
            return
        try:
            e = dict(
                key=self.table.item(row, 0).text(),
                kind={"Нажать": "down", "Отпустить": "up"}[
                    self.table.item(row, 1).text()
                ],
                delay=int(self.table.item(row, 2).text()),
            )
            p = copy.deepcopy(self.p)
            p["macros"][self.macro_list.currentRow()]["events"][row] = e
            validate(p)
            m["events"][row] = e
            self.macros_changed()
        except (ValueError, KeyError):
            self.note(
                "Проверь клавишу, действие («Нажать» / «Отпустить») и задержку 0–65535.",
                True,
            )
            self.show_macro()

    def move_event(self, d):
        m = self.macro()
        i = self.table.currentRow()
        if m and 0 <= i < len(m["events"]) and 0 <= i + d < len(m["events"]):
            m["events"][i], m["events"][i + d] = m["events"][i + d], m["events"][i]
            self.show_macro()
            self.table.selectRow(i + d)
            self.macros_changed()

    def delete_event(self):
        m = self.macro()
        i = self.table.currentRow()
        if m and 0 <= i < len(m["events"]):
            m["events"].pop(i)
            self.show_macro()
            self.macros_changed()

    def add_event(self):
        m = self.macro()
        if m is None:
            return
        dialog = EventDialog(self, self.delay.value())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kinds = [["down", "up"], ["down"], ["up"]][dialog.kind.currentIndex()]
        if len(m["events"]) + len(kinds) > 1000:
            self.note("Не более 1000 локальных событий.", True)
            return
        m["events"].extend(
            dict(key=dialog.key.currentText(), kind=kind, delay=dialog.delay.value())
            for kind in kinds
        )
        self.show_macro()
        self.macros_changed()

    def macro_menu(self):
        menu = QMenu(self)
        menu.addAction("Импорт макроса JSON…", self.import_macro)
        menu.addAction("Экспорт выбранного макроса…", self.export_macro)
        menu.exec(self.macro_apply.mapToGlobal(self.macro_apply.rect().bottomLeft()))

    def import_macro(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт макроса", str(ROOT), "Макросы (*.json)"
        )
        if not path:
            return
        try:
            if Path(path).stat().st_size > 200_000:
                raise ValueError("Файл слишком большой.")
            m = json.loads(Path(path).read_text())
            m["id"] = uuid.uuid4().hex
            candidate = copy.deepcopy(self.p)
            candidate["macros"].append(m)
            validated = validate(candidate)
            self.p["macros"] = validated["macros"]
            self.refresh_macros()
            self.macro_list.setCurrentRow(len(self.p["macros"]) - 1)
            self.macros_changed()
        except (ValueError, TypeError, OSError) as e:
            QMessageBox.warning(self, "Импорт", str(e))

    def export_macro(self):
        m = self.macro()
        if m is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт макроса", str(ROOT / "macro.json"), "Макросы (*.json)"
        )
        if path:
            try:
                atomic_json(path, m)
            except OSError as e:
                QMessageBox.warning(self, "Экспорт", str(e))

    def detect(self):
        dev = discover()
        if not dev:
            text = "●  Fury V2 не подключена"
        elif len(dev) > 1:
            text = "●  Подключено несколько Fury V2 — оставь одну для настройки"
        elif dev[0]["accessible"]:
            text = "●  Fury V2 подключена  ·  USB доступен  ·  Linux 0.2"
        else:
            text = "●  Fury V2 подключена  ·  Для настройки нужен доступ к USB"
        self.device_label.setText(text)
        self.access_btn.setVisible(bool(dev) and not all(d["accessible"] for d in dev))

    def setup_access(self):
        self.access_process = subprocess.Popen(
            [str(ROOT / "setup-access.sh")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.note(
            "Системный запрос предоставит активному пользователю доступ только к Fury V2."
        )
        self.access_btn.setEnabled(False)
        self.access_poll = QTimer(self)
        self.access_poll.timeout.connect(self.access_finished)
        self.access_poll.start(500)

    def access_finished(self):
        code = self.access_process.poll()
        if code is None:
            return
        self.access_poll.stop()
        self.access_btn.setEnabled(True)
        self.detect()
        self.note(
            (
                "Правило доступа установлено. Если доступ не появился, переподключи мышь."
                if code == 0
                else "Настройка доступа отменена или не выполнена."
            ),
            code != 0,
        )

    def apply(self):
        if self.worker and self.worker.isRunning():
            return
        group = ["buttons", "performance", "light", "buttons"][self.current_tab]
        if self.current_tab == 3 and not any(
            isinstance(a, dict) for a in self.p["buttons"]
        ):
            self.note("Сначала назначь макрос хотя бы одной кнопке.", True)
            return
        try:
            packets = build_packets(self.p, (group,))
            self.store.save()
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Настройки", str(e))
            return
        self.apply_btn.setEnabled(False)
        self.macro_apply.setEnabled(False)
        self.note("Передаю настройки мыши…")
        self.worker = Sender(packets)
        self.worker.result.connect(self.sent)
        self.worker.start()

    def sent(self, ok, message):
        self.apply_btn.setEnabled(True)
        self.macro_apply.setEnabled(True)
        self.note(message, not ok)
        if not ok:
            QMessageBox.warning(self, "Fury V2", message)

    def closeEvent(self, e):
        if self.worker and self.worker.isRunning():
            self.note("Подожди завершения передачи настроек.")
            e.ignore()
            return
        self.save_timer.stop()
        self.save()
        e.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "fury-v2-linux/profiles.json",
    )
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Fury V2 Linux")
    app.setDesktopFileName("fury-v2-linux")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    args.data = args.data.expanduser().resolve()
    args.data.parent.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(args.data) + ".lock")
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(
            None,
            "Fury V2 Linux",
            "Приложение уже запущено для этого файла профилей. Открой существующее окно.",
        )
        return 0
    try:
        w = Window(args.data)
    except (OSError, ValueError, KeyError, TypeError) as e:
        QMessageBox.critical(
            None,
            "Fury V2 Linux",
            "Не удалось прочитать профили. Файл не перезаписан.\n" + str(e),
        )
        return 1
    w.show()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
        for i, name in enumerate(["buttons", "performance", "lighting", "macros"]):
            w.tab(i)
            app.processEvents()
            w.grab().save(str(args.screenshots / (name + ".png")))
        w.close()
        return 0
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
