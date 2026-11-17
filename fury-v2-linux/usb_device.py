"""libusb transport, restricted to 04d9:a09f interface 2; never detaches input drivers."""

import ctypes as C
import ctypes.util
import os, time
from pathlib import Path
from core import encode

VID, PID = 0x04D9, 0xA09F


def discover():
    devices = []
    for path in Path("/sys/bus/usb/devices").glob("*"):
        try:
            if (path / "idVendor").read_text().strip() != "04d9" or (
                path / "idProduct"
            ).read_text().strip() != "a09f":
                continue
            bus = int((path / "busnum").read_text())
            dev = int((path / "devnum").read_text())
            node = Path(f"/dev/bus/usb/{bus:03}/{dev:03}")
            devices.append(
                dict(
                    path=str(path),
                    node=str(node),
                    accessible=os.access(node, os.R_OK | os.W_OK),
                    version=(path / "bcdDevice").read_text().strip(),
                )
            )
        except (OSError, ValueError):
            continue
    return devices


class USBError(RuntimeError):
    pass


class Device:
    def __init__(self):
        self.lib = None
        self.ctx = C.c_void_p()
        self.handle = C.c_void_p()
        self.claimed = False

    def __enter__(self):
        devices = discover()
        if not devices:
            raise USBError("Fury V2 не подключена.")
        if len(devices) != 1:
            raise USBError("Подключи только одну Fury V2 для настройки.")
        if not devices[0]["accessible"]:
            raise USBError("Нет доступа к USB. Нажми «Настроить доступ» внизу окна.")
        if devices[0]["version"] != "0307":
            raise USBError(
                "Эта версия прошивки ещё не проверена: " + devices[0]["version"]
            )
        path = ctypes.util.find_library("usb-1.0")
        if not path:
            raise USBError("Не найдена библиотека libusb-1.0.")
        l = self.lib = C.CDLL(path)
        sigs = {
            "libusb_init": ([C.POINTER(C.c_void_p)], C.c_int),
            "libusb_exit": ([C.c_void_p], None),
            "libusb_open_device_with_vid_pid": (
                [C.c_void_p, C.c_uint16, C.c_uint16],
                C.c_void_p,
            ),
            "libusb_close": ([C.c_void_p], None),
            "libusb_claim_interface": ([C.c_void_p, C.c_int], C.c_int),
            "libusb_release_interface": ([C.c_void_p, C.c_int], C.c_int),
            "libusb_control_transfer": (
                [
                    C.c_void_p,
                    C.c_uint8,
                    C.c_uint8,
                    C.c_uint16,
                    C.c_uint16,
                    C.c_void_p,
                    C.c_uint16,
                    C.c_uint,
                ],
                C.c_int,
            ),
            "libusb_interrupt_transfer": (
                [
                    C.c_void_p,
                    C.c_ubyte,
                    C.c_void_p,
                    C.c_int,
                    C.POINTER(C.c_int),
                    C.c_uint,
                ],
                C.c_int,
            ),
            "libusb_error_name": ([C.c_int], C.c_char_p),
        }
        for n, (args, result) in sigs.items():
            getattr(l, n).argtypes = args
            getattr(l, n).restype = result
        try:
            self.check(l.libusb_init(C.byref(self.ctx)))
            self.handle = C.c_void_p(
                l.libusb_open_device_with_vid_pid(self.ctx, VID, PID)
            )
            if not self.handle:
                raise USBError(
                    "Не удалось открыть USB-устройство. Проверь подключение и права."
                )
            self.check(l.libusb_claim_interface(self.handle, 2))
            self.claimed = True
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def check(self, result):
        if result < 0:
            raise USBError(self.lib.libusb_error_name(result).decode())

    def send(self, packets, progress=None):
        # Validate the entire transaction before sending any prefix to the device.
        packets = list(packets)
        for kind, payload in packets:
            if not isinstance(payload, bytes):
                raise USBError("Пакет должен содержать байты.")
            if kind == "feature":
                if len(payload) != 8 or sum(payload) & 255 != 255:
                    raise USBError("Ошибка контрольной суммы пакета.")
            elif kind == "out":
                if len(payload) != 32:
                    raise USBError("Неверный размер OUT-пакета.")
            else:
                raise USBError("Неизвестный тип USB-пакета.")
        for i, (kind, payload) in enumerate(packets):
            if kind == "feature":
                if len(payload) != 8 or sum(payload) & 255 != 255:
                    raise USBError("Ошибка контрольной суммы пакета.")
                wire = encode(payload)
                buf = C.create_string_buffer(wire, len(wire))
                n = self.lib.libusb_control_transfer(
                    self.handle, 0x21, 0x09, 0x0300, 2, buf, 8, 1000
                )
                self.check(n)
                if n != 8:
                    raise USBError("Неполная передача Feature Report.")
            elif kind == "out":
                if len(payload) != 32:
                    raise USBError("Неверный размер OUT-пакета.")
                buf = C.create_string_buffer(payload, len(payload))
                done = C.c_int()
                self.check(
                    self.lib.libusb_interrupt_transfer(
                        self.handle, 0x03, buf, 32, C.byref(done), 1000
                    )
                )
                if done.value != 32:
                    raise USBError("Неполная передача OUT-пакета.")
            else:
                raise USBError("Неизвестный тип USB-пакета.")
            time.sleep(0.02)
            if progress:
                progress(i + 1, len(packets))

    def __exit__(self, *args):
        if self.lib:
            if self.handle:
                if self.claimed:
                    self.lib.libusb_release_interface(self.handle, 2)
                self.lib.libusb_close(self.handle)
            if self.ctx:
                self.lib.libusb_exit(self.ctx)
        self.handle = C.c_void_p()
        self.ctx = C.c_void_p()
        self.claimed = False
