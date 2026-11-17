"""Native Fury V2 profile model and protocol; no Windows runtime required."""

from pathlib import Path
import copy, json, os, re, tempfile, uuid
from macros import MODES, compile_macro

ROOT = Path(__file__).resolve().parent
ACTIONS = {
    "left": ("Левая кнопка", "0100f000"),
    "right": ("Правая кнопка", "0100f100"),
    "middle": ("Средняя кнопка", "0100f200"),
    "back": ("Назад", "0100f400"),
    "forward": ("Вперёд", "0100f300"),
    "dpi_cycle": ("Переключение DPI", "07000100"),
    "dpi_down": ("DPI −", "07000200"),
    "light_cycle": ("Смена режимов подсветки", "08000300"),
    "off": ("Отключить клавишу", "00000000"),
}
DEFAULT_BUTTONS = [
    "left",
    "right",
    "middle",
    "back",
    "forward",
    "dpi_cycle",
    "light_cycle",
]
LIGHTS = [
    "Выкл.",
    "Пульсация",
    "Разряд молнии",
    "Неон",
    "Волна",
    "Реакция на нажатие",
    "Хвост",
    "Туда-обратно",
    "Стандартная",
    "Йо-йо",
    "Мрамор",
    "Падающая звезда",
]


def default_profile(name="Профиль 1"):
    return dict(
        name=name,
        dpi=[400, 800, 1200, 2400, 3200, 6200],
        dpi_count=6,
        selected_dpi=2,
        dpi_colors=["#ff0000", "#00ff00", "#0000ff", "#ff00ff", "#00ffff", "#ffffff"],
        rate=500,
        light_mode=3,
        brightness=124,
        frequency=3,
        length=2,
        color_mode=1,
        color="#ff0000",
        palette=[
            "#ff0000",
            "#00ff00",
            "#0000ff",
            "#ffff00",
            "#ff00ff",
            "#00ffff",
            "#ff8000",
            "#ffffff",
        ],
        buttons=DEFAULT_BUTTONS.copy(),
        macros=[],
        cursor_speed=6,
        scroll_speed=3,
        double_click=5,
        precision=False,
        response=20,
    )


def validate(p):
    if not isinstance(p, dict):
        raise ValueError("Профиль должен быть объектом JSON.")
    base = default_profile()
    unknown = set(p) - set(base)
    if unknown:
        raise ValueError("Неизвестные поля: " + ", ".join(sorted(unknown)))
    q = copy.deepcopy(base)
    q.update(copy.deepcopy(p))

    def integer(v, lo, hi):
        return type(v) is int and lo <= v <= hi

    if not isinstance(q["name"], str) or not q["name"].strip() or len(q["name"]) > 30:
        raise ValueError("Имя: от 1 до 30 символов.")
    if (
        not isinstance(q["dpi"], list)
        or len(q["dpi"]) != 6
        or any(not integer(x, 200, 12400) or x % 100 for x in q["dpi"])
    ):
        raise ValueError("DPI: шесть значений от 200 до 12400, шаг 100.")
    for k, lo, hi in [
        ("dpi_count", 1, 6),
        ("selected_dpi", 0, 5),
        ("light_mode", 0, 11),
        ("brightness", 0, 255),
        ("frequency", 0, 4),
        ("length", 0, 4),
        ("color_mode", 0, 1),
        ("cursor_speed", 1, 11),
        ("scroll_speed", 1, 11),
        ("double_click", 0, 10),
        ("response", 1, 100),
    ]:
        if not integer(q[k], lo, hi):
            raise ValueError("Недопустимое значение: " + k)
    if q["selected_dpi"] >= q["dpi_count"]:
        raise ValueError("Выбранный DPI должен быть активен.")
    if type(q["rate"]) is not int or q["rate"] not in (125, 250, 500, 1000):
        raise ValueError("Частота: 125, 250, 500 или 1000 Гц.")

    def color(c):
        return isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c)

    if not color(q["color"]):
        raise ValueError("Неверный цвет.")
    for k, n in [("dpi_colors", 6), ("palette", 8)]:
        if (
            not isinstance(q[k], list)
            or len(q[k]) != n
            or not all(color(c) for c in q[k])
        ):
            raise ValueError("Неверная палитра: " + k)
    if not isinstance(q["buttons"], list) or len(q["buttons"]) != 7:
        raise ValueError("Нужно семь назначений кнопок.")
    if "left" not in q["buttons"]:
        raise ValueError("Оставь хотя бы одну кнопку с левым кликом.")
    if type(q["precision"]) is not bool:
        raise ValueError("Неверное значение ускорения.")
    if not isinstance(q["macros"], list) or len(q["macros"]) > 100:
        raise ValueError("Слишком много макросов.")
    ids = set()
    for i, m in enumerate(q["macros"]):
        if (
            not isinstance(m, dict)
            or not {"name", "events", "repeat"} <= set(m)
            or set(m) - {"id", "name", "events", "repeat"}
        ):
            raise ValueError("Неверный макрос.")
        if "id" not in m:
            m["id"] = uuid.uuid5(uuid.NAMESPACE_URL, f'fury-v2:{i}:{m["name"]}').hex
        if (
            not isinstance(m["id"], str)
            or not re.fullmatch("[0-9a-f]{32}", m["id"])
            or m["id"] in ids
        ):
            raise ValueError("Неверный или повторяющийся ID макроса.")
        ids.add(m["id"])
        if (
            not isinstance(m["name"], str)
            or not 1 <= len(m["name"]) <= 60
            or not integer(m["repeat"], 1, 999)
        ):
            raise ValueError("Неверное имя или повтор макроса.")
        if not isinstance(m["events"], list) or len(m["events"]) > 1000:
            raise ValueError("Не более 1000 событий.")
        for e in m["events"]:
            if (
                not isinstance(e, dict)
                or set(e) != {"key", "kind", "delay"}
                or not isinstance(e["key"], str)
                or not 1 <= len(e["key"]) <= 60
                or e["kind"] not in ("down", "up")
                or not integer(e["delay"], 0, 65535)
            ):
                raise ValueError("Неверное событие макроса.")
    for action in q["buttons"]:
        if isinstance(action, str) and action in ACTIONS:
            continue
        if (
            isinstance(action, dict)
            and set(action) == {"macro", "mode"}
            and isinstance(action["macro"], str)
            and action["macro"] in ids
            and isinstance(action["mode"], str)
            and action["mode"] in MODES
        ):
            continue
        raise ValueError("Неподдерживаемое назначение кнопки или отсутствующий макрос.")
    return q


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = [default_profile()]
        self.active = 0
        if self.path.exists():
            data = json.loads(self.path.read_text())
            rows = data["profiles"]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 100:
                raise ValueError("Неверный список профилей.")
            self.profiles = [validate(p) for p in rows]
            self.active = data["active"]
            if type(self.active) is not int or not 0 <= self.active < len(rows):
                raise ValueError("Неверный активный профиль.")

    @property
    def current(self):
        return self.profiles[self.active]

    def save(self):
        atomic_json(
            self.path,
            dict(
                version=2,
                active=self.active,
                profiles=[validate(p) for p in self.profiles],
            ),
        )


# Wire obfuscation verified against 1,003 vectors from the isolated vendor routine.
def encode(packet):
    if len(packet) != 8:
        raise ValueError("Feature packet must be 8 bytes")
    b = bytearray(packet[i] for i in (5, 4, 7, 6, 1, 0, 3, 2))
    for i, k in enumerate(b"FB1255", 1):
        b[i] ^= k
    n = int.from_bytes(b, "big")
    n = ((n << 3) | (n >> 61)) & ((1 << 64) - 1)
    return bytes(
        (a + b) & 255
        for a, b in zip(n.to_bytes(8, "big"), bytes.fromhex("25 f6 e4 76 47 54 e6 76"))
    )


def feature(command, *args):
    if len(args) > 6:
        raise ValueError("Too many arguments")
    b = bytes([command, *args]).ljust(7, b"\0")
    return b + bytes([(255 - sum(b)) & 255])


def rgb(s):
    return bytes.fromhex(s[1:])


def build_packets(profile, groups=("performance", "light", "buttons")):
    p = validate(profile)
    out = []

    def f(cmd, *args):
        out.append(("feature", feature(cmd, *args)))

    def data(b):
        out.append(("out", b.ljust(32, b"\0")))

    if "performance" in groups:
        f(1, {125: 8, 250: 4, 500: 2, 1000: 1}[p["rate"]])
        f(11, p["selected_dpi"] + 1)
    if "light" in groups:
        f(12, *rgb(p["color"]))
        mode = p["light_mode"]
        bright = p["brightness"]
        speed = 4 - p["frequency"]
        cm = 2 if p["color_mode"] == 1 else 0
        if mode == 0:
            a, b = 0, 0
        elif mode == 1:
            a, b = bright, cm
        elif mode == 2:
            a, b = p["frequency"], cm
        elif mode in (3, 4):
            a, b = p["frequency"], bright
        elif mode == 5:
            a, b = bright, cm
        elif mode in (6, 7):
            a, b = 4 - p["length"], cm
        elif mode == 8:
            a, b = bright, int(bool(cm))
        elif mode == 9:
            a, b = bright, cm | (speed << 4)
        elif mode == 10:
            a, b = bright, speed
        else:
            a, b = bright, cm
        f(13, mode, a, b)
        f(16, 0, 24)
        data(b"".join(map(rgb, p["palette"])))
    if "performance" in groups:
        f(16, 1, 24)
        data(b"".join(map(rgb, p["dpi_colors"] + ["#ff8000", "#ffffff"])))
        f(17, p["dpi_count"], 8)
        units = [d // 100 for d in p["dpi"]] + [70, 80]
        data(bytes(n if n <= 62 else (n // 2) | 64 for n in units))
    if "buttons" in groups:
        # Office layer only. Hidden slots match the vendor default profile + Data.ini.
        table = bytearray()
        blocks = []
        macros = {m["id"]: m for m in p["macros"]}
        for action in p["buttons"]:
            if isinstance(action, str):
                table.extend(bytes.fromhex(ACTIONS[action][1]))
            else:
                macro = macros[action["macro"]]
                try:
                    block = compile_macro(macro)
                except ValueError as e:
                    raise ValueError(f'Макрос «{macro["name"]}»: {e}') from e
                blocks.append(block)
                table.extend([9, MODES[action["mode"]][1], len(blocks), 0])
        table += bytes(28) + bytes.fromhex("0400010004000200")
        assert len(table) == 64
        f(18, 1, 64)
        data(bytes(table[:32]))
        data(bytes(table[32:]))
        for slot, block in enumerate(blocks, 1):
            f(19, slot, 128)
            for offset in range(0, 128, 32):
                data(block[offset : offset + 32])
    if out:
        f(8, 0xAA, 0xCC, 0xEE)
    return out


def action_label(action, profile):
    if isinstance(action, str):
        return ACTIONS[action][0]
    m = next(m for m in profile["macros"] if m["id"] == action["macro"])
    return "Макрос: " + m["name"]
