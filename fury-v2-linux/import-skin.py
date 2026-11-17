#!/usr/bin/env python3
"""Import selected artwork from the user's own extracted vendor installation."""

import argparse
import os
import shutil
from pathlib import Path


def import_skin(source, target):
    source = Path(source).expanduser().resolve()
    candidates = [source, source / "Skins", source / "skins", source / "Skin"]
    candidates += list(source.glob("*/Skins")) + list(source.glob("*/skins"))
    found = next(
        (
            p
            for p in candidates
            if (p / "bk/bk.jpg").is_file() and (p / "mouse/mouse.png").is_file()
        ),
        None,
    )
    if found is None:
        raise ValueError(
            "Укажи папку оформления, содержащую bk/bk.jpg и mouse/mouse.png."
        )
    names = ["bk/bk.jpg", "mouse/mouse.png", "guangyun.png"]
    names += [f"mouse/mouse_{i}.png" for i in range(1, 8)]
    names += [
        f"{name}_{state}.png"
        for name in ("min", "close", "add", "delete", "menu", "reset", "button")
        for state in (1, 2, 3)
    ]
    count = 0
    for name in names:
        src = found / name
        if src.is_file():
            dst = Path(target) / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    target = (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        / "fury-v2-linux/skins"
    )
    try:
        count = import_skin(args.source, target)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"Импортировано файлов: {count}. Перезапусти Fury V2 Linux. Тема: {target}")
