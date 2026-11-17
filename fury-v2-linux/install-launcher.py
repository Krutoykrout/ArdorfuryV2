#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(__file__).resolve().parent
applications = Path.home() / ".local/share/applications"
applications.mkdir(parents=True, exist_ok=True)


def desktop_quote(s):
    return (
        '"'
        + str(s)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
        .replace("%", "%%")
        + '"'
    )


text = "\n".join(
    [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Fury V2 Linux",
        "Comment=Настройка мыши ARDOR GAMING Fury V2",
        "Exec=" + desktop_quote(root / "run.sh"),
        "Path=" + str(root),
        "Icon=" + str(root / "assets/icon.svg"),
        "Terminal=false",
        "Categories=Settings;HardwareSettings;",
        "StartupWMClass=Fury V2 Linux",
        "",
    ]
)
for dest in (applications / "fury-v2-linux.desktop", root / "Fury V2 Linux.desktop"):
    dest.write_text(text)
    dest.chmod(0o755)
print("Ярлык установлен: " + str(applications / "fury-v2-linux.desktop"))
