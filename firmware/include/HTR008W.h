#ifndef HTR008W_LEARNED_H
#define HTR008W_LEARNED_H
#include <stdint.h>
#include <stddef.h>

// Learned fingerprints for this user's remote. These are pulse-width symbols,
// not a claim about the manufacturer's logical bit encoding or rolling code.
namespace HTR008W {
static const char UP_PATTERN[] = "0100000011000000000000001100000011011011100101110100000010001100100000";
static const char STOP_PATTERN[] = "0110000011000000010000001000000010011011110101110000000011110100100100";
static const char DOWN_PATTERN[] = "0010000011000000010000001000000010011011110101110000000011111100100100";
static const char THIRD_PROFILE[] = "0100000011000000011000001010000010111011111101110010000011010101101100";

struct Frame { uint8_t profile; uint8_t command; char symbols[71]; };
inline bool range(uint16_t value, uint16_t low, uint16_t high) {
    return value >= low && value <= high;
}
inline bool decode(const uint8_t *pulses, size_t count, uint8_t scale, Frame &out) {
    if (scale == 0 || count < 76) return false;
    uint16_t sync = uint16_t(pulses[4]) * scale;
    bool physical = range(sync, 3400, 4300);
    if (!physical && !range(sync, 5500, 6800)) return false;
    for (uint8_t i = 1; i < 4; ++i)
        if (!range(uint16_t(pulses[i]) * scale, physical ? 1600 : 2600, physical ? 2200 : 3500))
            return false;
    if (!range(uint16_t(pulses[0]) * scale, physical ? 1000 : 1500, physical ? 2400 : 4000))
        return false;
    for (uint8_t i = 0; i < 70; ++i) {
        uint16_t duration = uint16_t(pulses[5 + i]) * scale;
        if (range(duration, physical ? 300 : 450, physical ? 520 : 800)) out.symbols[i] = '0';
        else if (range(duration, physical ? 750 : 1100, physical ? 1050 : 1700)) out.symbols[i] = '1';
        else return false;
    }
    out.symbols[70] = 0;
    if (!range(uint16_t(pulses[75]) * scale, physical ? 2000 : 3200, 7650)) return false;
    const char *profiles[] = {UP_PATTERN, STOP_PATTERN, THIRD_PROFILE};
    out.profile = 0;
    for (uint8_t profile = 0; profile < 3; ++profile) {
        bool match = true;
        for (uint8_t i = 3; i < 70; ++i) {
            if (i == 59 || i == 60) continue;
            if (out.symbols[i] != profiles[profile][i]) { match = false; break; }
        }
        if (match) { out.profile = profile + 1; break; }
    }
    if (!out.profile) return false;
    out.command = (out.symbols[59] == '1' ? 2 : 0) | (out.symbols[60] == '1' ? 1 : 0);
    return out.command != 0;
}
inline const char *name(uint8_t command) {
    return command == 1 ? "UP" : command == 2 ? "STOP" : command == 3 ? "DOWN" : "UNKNOWN";
}

// Reproduce the full main packet structure: 2 subframes for UP/DOWN, 3 for STOP.
// The final low space is a capture timeout, so use a deliberate 7500 us gap.
inline size_t encode(uint8_t command, uint8_t *pulses, size_t capacity, uint8_t scale) {
    if (scale != 30 || command < 1 || command > 3) return 0;
    uint8_t repeats = command == 2 ? 3 : 2;
    bool tailMark = command != 1;
    size_t required = repeats * 76 + (tailMark ? 2 : 0);
    if (capacity < required) return 0;
    const char *symbols = command == 1 ? UP_PATTERN : command == 2 ? STOP_PATTERN : DOWN_PATTERN;
    size_t cursor = 0;
    for (uint8_t repeat = 0; repeat < repeats; ++repeat) {
        for (uint8_t i = 0; i < 4; ++i) pulses[cursor++] = 1890 / scale;
        pulses[cursor++] = 3870 / scale;
        for (uint8_t i = 0; i < 70; ++i) pulses[cursor++] = (symbols[i] == '1' ? 900 : 390) / scale;
        pulses[cursor++] = 2370 / scale;
    }
    if (tailMark) { pulses[cursor++] = 1890 / scale; pulses[cursor++] = 7500 / scale; }
    else pulses[cursor - 1] = 7500 / scale;
    return cursor;
}
}
#endif
