#!/bin/sh
set -eu
if [ "$(id -u)" != 0 ]; then
    exec pkexec /bin/sh "$(realpath "$0")"
fi
# uaccess grants only the active local session access to this exact USB ID.
cat > /etc/udev/rules.d/70-fury-v2-linux.rules <<'EOF'
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="04d9", ATTR{idProduct}=="a09f", TAG+="uaccess"
EOF
udevadm control --reload-rules
udevadm trigger --subsystem-match=usb --attr-match=idVendor=04d9 --attr-match=idProduct=a09f --action=change
udevadm settle
