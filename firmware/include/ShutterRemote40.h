#ifndef SHUTTER_REMOTE_40_H
#define SHUTTER_REMOTE_40_H

#include <stdint.h>
#include <stddef.h>

// Protocol observed in the January 2026 captures. No checksum is assumed.
namespace ShutterRemote40 {
struct Frame {
    uint32_t id;
    uint8_t channelByte;
    uint8_t command;
};

inline bool between(uint16_t value, uint16_t low, uint16_t high) {
    return value >= low && value <= high;
}

// Input starts at pulse 1 in RFLink; the caller passes Pulses + 1.
inline bool decode(const uint8_t *pulses, size_t count, uint8_t scale, Frame &frame) {
    if (count != 82 || scale == 0) return false;
    // Legacy RFDEBUG overstates widths; direct micros() measurement confirms
    // a separate physical profile. Never use legacy sample times for TX.
    const uint16_t sync = uint16_t(pulses[1]) * scale;
    const bool physical = between(sync, 1200, 1800);
    if (!physical && !between(sync, 2200, 2600)) return false;
    // The receiver can clip the startup mark: complete October captures start
    // at 210/240/270 us in legacy DEBUG. Still validate sync and all data pairs.
    if (!between(uint16_t(pulses[0]) * scale, 150, physical ? 5500 : 1300) ||
        !between(uint16_t(pulses[81]) * scale, physical ? 3800 : 5000, 7650)) return false;
    const uint16_t shortMin = physical ? 180 : 300;
    const uint16_t shortMax = physical ? 420 : 650;
    const uint16_t longMin = physical ? 500 : 800;
    const uint16_t longMax = physical ? 850 : 1300;

    uint32_t id = 0;
    uint16_t tail = 0;
    for (uint8_t bit = 0; bit < 40; ++bit) {
        uint16_t mark = uint16_t(pulses[2 + 2 * bit]) * scale;
        uint16_t space = uint16_t(pulses[3 + 2 * bit]) * scale;
        bool one = between(mark, longMin, longMax);
        bool zero = between(mark, shortMin, shortMax);
        if (!one && !zero) return false;
        // Last space is the frame gap, not the second half of a PWM bit.
        if (bit != 39 && !(one ? between(space, shortMin, shortMax) : between(space, longMin, longMax)))
            return false;
        if (bit < 24) id = (id << 1) | uint32_t(one);
        else tail = (tail << 1) | uint16_t(one);
    }
    frame.id = id;
    frame.channelByte = uint8_t(tail >> 8);
    frame.command = uint8_t(tail);
    return true;
}

// Some receiver captures contain all 40 data pairs, but no startup/sync pair.
// Only accept the observed channel/command family; callers must confirm repeats.
inline bool decodeClipped(const uint8_t *pulses, size_t count, uint8_t scale, Frame &frame) {
    if (count != 80 || scale != 30) return false;
    uint8_t full[82];
    full[0] = 300 / scale;
    for (size_t i = 0; i < 80; ++i) full[i + 2] = pulses[i];
    const uint16_t syncs[] = {1470, 2310};
    bool valid = false;
    for (uint8_t i = 0; i < 2; ++i) {
        full[1] = syncs[i] / scale;
        if (decode(full, 82, scale, frame)) { valid = true; break; }
    }
    if (!valid || frame.channelByte < 0x40 || frame.channelByte > 0x45) return false;
    return frame.command == 0x11 || frame.command == 0x33 || frame.command == 0x55 ||
           frame.command == 0x1E || frame.command == 0x3C;
}

inline bool encode(const Frame &frame, uint8_t *pulses, size_t capacity, uint8_t scale) {
    if (capacity < 82 || scale != 30 || frame.id > 0xFFFFFFUL) return false;
    // Long OOK startup mark allows the receiver to settle. Its beginning is
    // clipped in RFLink captures. Data/sync timings follow the direct measurement.
    pulses[0] = 4800 / scale;
    pulses[1] = 1470 / scale;
    for (uint8_t bit = 0; bit < 40; ++bit) {
        bool one;
        if (bit < 24) one = (frame.id >> (23 - bit)) & 1;
        else if (bit < 32) one = (frame.channelByte >> (31 - bit)) & 1;
        else one = (frame.command >> (39 - bit)) & 1;
        pulses[2 + 2 * bit] = (one ? 660 : 300) / scale;
        pulses[3 + 2 * bit] = (one ? 300 : 660) / scale;
    }
    pulses[81] = 6990 / scale;
    return true;
}

// Conventional Brel/Dooya meanings; physical button mapping needs confirmation.
inline const char *commandName(uint8_t command) {
    switch (command) {
        case 0x11: return "UP";
        case 0x33: return "DOWN";
        case 0x55: return "STOP";
        default: return "UNKNOWN";
    }
}
}
#endif
