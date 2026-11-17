"""Fury V2 on-device macros, independently implemented from observed wire formats.

Event timing bytes match the vendor serializer; firmware timing still needs
physical verification. No host keyboard injection or Windows binary is used.
"""

BLOCK_SIZE = 128
MAX_EVENTS = 40  # Vendor editor's event limit, independent of encoded byte limit.
MODES = {
    "count": ("Указанное число повторов", 0),
    "toggle": ("До повторного нажатия", 1),
    "hold": ("Пока кнопка удерживается", 2),
}
KEYS = {chr(65 + i): 4 + i for i in range(26)}
KEYS.update({c: 30 + i for i, c in enumerate("1234567890")})
KEYS.update(
    dict(
        zip(
            [
                "Enter",
                "Esc",
                "Backspace",
                "Tab",
                "Space",
                "-",
                "=",
                "[",
                "]",
                "\\",
                "NonUS#",
                ";",
                "'",
                "`",
                ",",
                ".",
                "/",
                "CapsLock",
            ],
            range(40, 58),
        )
    )
)
KEYS.update({f"F{i+1}": 58 + i for i in range(12)})
KEYS.update(
    dict(
        zip(
            [
                "PrintScreen",
                "ScrollLock",
                "Pause",
                "Insert",
                "Home",
                "PageUp",
                "Delete",
                "End",
                "PageDown",
                "Right",
                "Left",
                "Down",
                "Up",
                "NumLock",
                "Num/",
                "Num*",
                "Num-",
                "Num+",
                "NumEnter",
                "Num1",
                "Num2",
                "Num3",
                "Num4",
                "Num5",
                "Num6",
                "Num7",
                "Num8",
                "Num9",
                "Num0",
                "Num.",
                "NonUS\\",
                "Menu",
            ],
            range(70, 102),
        )
    )
)
KEYS.update(
    dict(
        zip(
            ["LCtrl", "LShift", "LAlt", "LWin", "RCtrl", "RShift", "RAlt", "RWin"],
            range(224, 232),
        )
    )
)
KEYS.update(
    {
        "MouseLeft": 240,
        "MouseRight": 241,
        "MouseMiddle": 242,
        "MouseBack": 243,
        "MouseForward": 244,
    }
)
NAMES = {v: k for k, v in KEYS.items()}
ALIASES = {
    "CTRL": "LCtrl",
    "CONTROL": "LCtrl",
    "SHIFT": "LShift",
    "ALT": "LAlt",
    "META": "LWin",
    "WIN": "LWin",
    "ESCAPE": "Esc",
    "RETURN": "Enter",
    "DEL": "Delete",
    "INS": "Insert",
    "PGUP": "PageUp",
    "PGDOWN": "PageDown",
    "BACKSPACE": "Backspace",
    "SPACE": "Space",
}
CASE_NAMES = {k.upper(): k for k in KEYS}


def canonical_key(key):
    if not isinstance(key, str):
        raise ValueError("Название клавиши должно быть строкой.")
    name = ALIASES.get(key.upper(), CASE_NAMES.get(key.upper()))
    if name is None:
        raise ValueError(
            f"Неизвестная клавиша «{key}». Выбери её из списка или запиши заново."
        )
    return name


def key_code(key):
    return KEYS[canonical_key(key)]


def macro_body(macro, require_balanced=True):
    """Unpadded 2-byte repeat count + events, byte-identical to vendor code.

    Existing editor drafts can be saved with unsupported/unbalanced events;
    compilation refuses them before any USB transaction is opened.
    """
    repeat = macro["repeat"]
    events = macro["events"]
    if type(repeat) is not int or not 1 <= repeat <= 999:
        raise ValueError("Число повторов должно быть от 1 до 999.")
    if not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError(
            f"Для мыши нужно от 1 до {MAX_EVENTS} событий (нажатие и отпускание считаются отдельно)."
        )
    data = bytearray(repeat.to_bytes(2, "big"))
    pressed = set()
    for index, e in enumerate(events, 1):
        code = key_code(e["key"])
        kind = e["kind"]
        delay = e["delay"]
        if (
            kind not in ("down", "up")
            or type(delay) is not int
            or not 0 <= delay <= 65535
        ):
            raise ValueError(f"Событие {index}: неверное действие или задержка.")
        if require_balanced:
            if kind == "down":
                if code in pressed:
                    raise ValueError(f'Событие {index}: «{e["key"]}» уже нажата.')
                pressed.add(code)
            else:
                if code not in pressed:
                    raise ValueError(
                        f'Событие {index}: отпускание «{e["key"]}» без нажатия.'
                    )
                pressed.remove(code)
        release = 0x80 if kind == "up" else 0
        if delay <= 1270:
            data.extend([(delay // 10) | 1 | release, code])
        else:
            units, remainder = divmod(delay, 20)
            data.extend(
                [((remainder + 5) // 10) | release, code, 0, 1, units >> 8, units & 255]
            )
    if require_balanced and pressed:
        raise ValueError(
            "Добавь отпускание клавиш: " + ", ".join(NAMES[c] for c in sorted(pressed))
        )
    if len(data) > BLOCK_SIZE:
        raise ValueError(
            f"Макрос занимает {len(data)}/{BLOCK_SIZE} байт. Сократи события или длинные задержки."
        )
    return bytes(data)


def compile_macro(macro):
    return macro_body(macro).ljust(BLOCK_SIZE, b"\0")


# Linux evdev key positions -> USB usages. X11 nativeScanCode is evdev + 8.
EVDEV_TO_HID = {
    1: 41,
    14: 42,
    15: 43,
    28: 40,
    29: 224,
    42: 225,
    54: 229,
    56: 226,
    57: 44,
    58: 57,
    69: 83,
    70: 71,
    96: 88,
    97: 228,
    98: 84,
    99: 70,
    100: 230,
    102: 74,
    103: 82,
    104: 75,
    105: 80,
    106: 79,
    107: 77,
    108: 81,
    109: 78,
    110: 73,
    111: 76,
    119: 72,
    125: 227,
    126: 231,
    127: 101,
    86: 100,
    55: 85,
    74: 86,
    78: 87,
    83: 99,
}
for codes, names in [
    (range(2, 14), list("1234567890-=")),
    (range(16, 28), list("QWERTYUIOP[]")),
    (range(30, 42), list("ASDFGHJKL;'`")),
    (range(43, 54), list("\\ZXCVBNM,./")),
    (range(59, 69), [f"F{i}" for i in range(1, 11)]),
    ([87, 88], ["F11", "F12"]),
    (
        [71, 72, 73, 75, 76, 77, 79, 80, 81, 82],
        [
            "Num7",
            "Num8",
            "Num9",
            "Num4",
            "Num5",
            "Num6",
            "Num1",
            "Num2",
            "Num3",
            "Num0",
        ],
    ),
]:
    EVDEV_TO_HID.update({c: KEYS[n] for c, n in zip(codes, names)})
