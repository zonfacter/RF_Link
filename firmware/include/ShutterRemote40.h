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
    if (!between(uint16_t(pulses[0]) * scale, physical ? 150 : 300, physical ? 5500 : 1300) ||
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
