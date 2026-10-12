#ifndef RFLINK_BL999_H
#define RFLINK_BL999_H
#include <stdint.h>
#include <stddef.h>

// Independently implemented from the observed 36-bit PPM recordings and the
// published TFA TwinPlus / BL999 field description. No waveform is learned.
namespace BL999 {
struct Frame {
    uint64_t word;
    uint8_t sensorId;
    uint8_t channel;
    int16_t temperature; // tenths of a degree Celsius
    uint8_t humidity;
    bool batteryLow;
};
inline uint8_t reverse8(uint8_t value) {
    uint8_t reversed = 0;
    for (uint8_t i = 0; i < 8; ++i) { reversed = uint8_t((reversed << 1) | (value & 1)); value >>= 1; }
    return reversed;
}
inline bool range(uint16_t value, uint16_t low, uint16_t high) { return value >= low && value <= high; }
inline bool decode(const uint16_t *widths, size_t count, Frame &frame) {
    if (count != 74) return false;
    uint64_t word = 0;
    for (uint8_t i = 0; i < 36; ++i) {
        if (!range(widths[2 * i], 250, 650)) return false;
        const uint16_t space = widths[2 * i + 1];
        bool bit;
        if (range(space, 1500, 2400)) bit = false;
        else if (range(space, 3300, 4600)) bit = true;
        else return false;
        word = (word << 1) | uint64_t(bit);
    }
    if (!range(widths[72], 250, 650) || !range(widths[73], 4200, 12000)) return false;
    const uint8_t first = uint8_t(word >> 28);
    const uint8_t second = uint8_t(word >> 20);
    const uint8_t third = uint8_t(word >> 12);
    const uint8_t fourth = uint8_t(word >> 4);
    const uint8_t reversed[] = {reverse8(first), reverse8(second), reverse8(third), reverse8(fourth)};
    uint8_t sum = 0;
    for (uint8_t i = 0; i < 4; ++i) sum += uint8_t((reversed[i] >> 4) + (reversed[i] & 15));
    const uint8_t checksum = reverse8(uint8_t(word & 15)) >> 4;
    if ((sum & 15) != checksum || !(fourth & 1)) return false;
    const uint8_t sign = third & 7;
    if (sign != 0 && sign != 7) return false;
    const uint8_t encodedHumidity = reversed[3] & 127;
    if (encodedHumidity < 28 || encodedHumidity > 128) return false;
    const int16_t magnitude = int16_t((uint16_t(reversed[2] & 31) << 4) | (reversed[1] >> 4));
    frame.word = word;
    frame.sensorId = uint8_t((reversed[0] & 15) | ((reversed[0] & 192) >> 2));
    frame.channel = (first >> 2) & 3;
    frame.temperature = sign ? magnitude - 512 : magnitude;
    frame.humidity = encodedHumidity - 28;
    frame.batteryLow = (second & 128) != 0;
    return true;
}
}
#endif
