# Nobily regression from the 2026-10-13 export

The three complete 82-pulse DEBUG frames in nobily_clipped_start.jsonl start
with clipped marks of 210/270/240 microseconds. BUILD 0B rejected them because
its legacy start-mark minimum was 300 microseconds. BUILD 0C accepts marks
from 150 microseconds while retaining sync, data-pair and end-gap validation.

Expected words: 98461A4211 (channel 42 UP), 98461A431E (channel 43 unknown
command 1E), 98461A4411 (channel 44 UP). Incomplete 80-pulse frames remain
rejected. No meaning is assumed for command 1E.

The laptop application now stores the last known command and its timestamp
separately from the last received raw fields. An UNKNOWN follow-up remains
visible in the log/details without replacing the last known command in the
device overview. Existing records acquire this history on the next known
command; no command history is guessed from an UNKNOWN record.

BUILD 0C was compiled and installed on the laptop Mega at COM3. All 66070
flash bytes were verified; serial VERSION returned BUILD=0c and PING returned
PONG. A new live remote reception test is still pending.
