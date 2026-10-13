# BUILD 0D: complete data frames with missing startup/sync

The latest export (2026-10-13, 20:41 onward) contains 33 captures of 80 pulses:
all 40 PWM data pairs are present, but the initial startup/sync pair is missing.
These decode to ID 98461A, channel 42, commands 11/33/55/1E/3C.

The RX plugin now also accepts this shape if all bit pairs and the final gap
match a supported timing profile, the channel is 40..45, and the command is
one of the five observed codes. Two identical clipped frames within 2000 ms
are required before publication because sync and a checksum are unavailable.
Other incomplete shapes remain rejected. Commands 1E and 3C retain UNKNOWN
meaning; they are not silently mapped to a motor action.

run_clipped_nobily_tests.py replays the measured frames with their timestamps
through the actual firmware plugin: 13 confirmed outputs, including UP, DOWN
and STOP. Its harness also tests rejection of malformed pairs, incomplete
data and stale repeat confirmation. Existing 82-pulse tests and all 12 Python
registry/UI tests pass. The local Mega build succeeds (66546 flash bytes,
3836 RAM bytes). Installed on laptop COM3 with flash verification and
BUILD=0d/PONG serial confirmation. The user's fresh live export confirms
channel 42 UP at 20:48:54, STOP at 20:48:57, and DOWN at 20:49:00 on
2026-10-13. RAW 1E follows UP and RAW 3C follows DOWN in this test.
The local registry correctly retains last_known_command=DOWN after RAW 3C,
while preserving CMD=UNKNOWN and the complete last raw frame separately.

The recorded local device registry for this session still lacks the new
last_known_command fields, even after known commands. Restart the application
fully to load the current Python code; the next known command then records
its history without discarding unknown raw follow-ups.
