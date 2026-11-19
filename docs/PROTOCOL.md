# Fury V2 protocol notes

Target: ARDOR GAMING Fury V2 ARD-FRV2-3327-WT, USB 04d9:a09f,
bcdDevice 0307. Other products may share this USB ID and use a different
codec or command mapping. Do not broaden support based on the ID alone.

The configuration interface is USB interface 2, interrupt OUT endpoint 0x03.
It has no interrupt IN endpoint on the inspected device, so a missing
configuration hidraw node does not imply missing Linux mouse support.
Interfaces 0 and 1 remain attached to their existing input drivers.

Feature writes use bmRequestType=0x21, bRequest=0x09, wValue=0x0300,
wIndex=2, length=8. The decoded report is command + six argument bytes +
checksum; the sum of all eight bytes modulo 256 is 255. `core.encode`
implements the vendor's byte permutation, XOR, rotation and addition.
The public protocol constant is not an authentication credential.
Interrupt OUT data is sent in unencoded 32-byte chunks. Each transaction
ends with command 0x08, arguments aa cc ee. The transport pauses 20 ms
between packets, checks transfer lengths and always releases the interface.

## Buttons and macros

- Command 0x12, arguments 01 40: first button layer, 64 bytes of assignments.
- Each assignment occupies four bytes. Macro assignment: 09 MODE SLOT 00.
- MODE: 0 = repeat count, 1 = toggle, 2 = hold.
- Slots start at 1; each physical button binding gets its own macro slot.
- Command 0x13, arguments SLOT 80: 128-byte macro, four OUT packets.
- Macro bytes 0–1: repeat count, big endian (UI range 1–999).
- Short event: timing byte then key usage. For delay <=1270 ms,
  timing=(delay//10)|1, with bit 7 added for release.
- Long event: timing, key, 00, 01, units-high, units-low, where
  units,remainder=divmod(delay,20), timing=(remainder+5)//10, plus release bit.
- Keyboard usages use the USB HID keyboard page. Mouse usages f0–f4 are
  vendor-defined. Movement, wheel and media macro events are not implemented.
- The vendor editor allows 40 events; the 128-byte storage limit includes
  the repeat header. Long delays consume six bytes rather than two.
- Unused bytes are zero-filled. Unknown keys, unmatched releases, held keys
  at the end, duplicate presses, oversized bodies and invalid references
  are rejected before any transfer. There is no silent truncation.

The timing formula matches the original program, including its quantization.
Actual firmware timing, toggle/hold behavior and persistence after reconnect
still require physical testing. The editor attaches a recorded interval to
its preceding event; this timing interpretation also needs a hardware check.

## Verification and provenance

The Linux implementation was written independently using analysis of the
user's installed FuryV2.exe and Data.ini. Isolated x86 procedures were run
in an emulator with USB calls intercepted; they never accessed the mouse.
100 configuration vectors and 120 macro vectors are retained as JSON tests.
The wire codec was separately compared on 1,003 inputs. These are test data,
not bundled vendor executable code.

The button vectors intentionally cover only the first layer. The vendor's
second-layer writes and unrelated special-effect palette writes are omitted.
There is no firmware update command and no configuration readback.

Reference product: https://ardor-gaming.com/product/30013173/mysh-provodnaya-ardor-gaming-fury-v2/
Related independent project: https://github.com/JConradoN/pcyes-argus-mouse-linux
The related device uses different protocol details; its packets must not be
assumed compatible with Fury V2.

Successful USB transfer is not verification that firmware applied a setting.
If a transfer fails, a prefix of the transaction may already be on the device.

## Corrected action semantics in 0.2.1

The original action-label routine (0x4083e0; selector 0x40900c, jump table
0x408efc) identifies action 6 as dpi_cycle_text, 7 as dpi_up_text,
8 as dpi_down_text and 50 as light_mode_switch_text. The action table at
0x426120 maps these to 07 00 03 00, 07 00 01 00, 07 00 02 00 and
0b 00 00 00 respectively. Data.ini's default button bytes do not establish
these meanings. Version 0.2 incorrectly labeled 07 00 01 00 as a DPI cycle
and 08 00 03 00 as a lighting cycle. The regression fixture explicitly uses
original action IDs 6 and 50 instead of deriving IDs from the Linux map.

A user has confirmed a recorded Ctrl+Shift+C macro plays on their mouse.
This does not yet verify hold/toggle modes, timing or persistence.

After applying 0.2.1, the user confirmed DPI wraps from the sixth stage
back to the first and the lighting button cycles effects again.

## Double-click assignment in 0.3.0

The action-label jump table identifies action 9 as double_click_text.
Its entry in the original action table is 0a f0 32 02. The Linux action
`double_click` uses these bytes. The double-click regression fixture is
captured using original action ID 9 independently of the Linux action map,
with the corrected DPI and lighting cycles still present in the table.
Physical double-click playback is not yet confirmed. GNOME's double-click
interval is a separate desktop preference and does not generate input.

## Desktop preferences in 0.3.0

`linux_settings.py` accesses the installed schema
org.gnome.desktop.peripherals.mouse through gsettings: speed [-1,1],
accel-profile {default,flat,adaptive}, double-click (milliseconds).
Only explicitly edited keys are written, then read back. On failure the
backend attempts rollback to the immediately preceding snapshot. This is
not a transaction across multiple processes: external writers may race.
No root privileges, USB writes or synthetic input are involved. The UI
uses a separate Apply in Linux action and keeps desktop values outside
hardware profiles. Non-GNOME desktops are not enabled just because the
schema happens to be installed.
