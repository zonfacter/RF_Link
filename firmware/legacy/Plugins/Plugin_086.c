// TFA TwinPlus / Conrad KW9010 / BL999 sensor family, measured PPM timing.
#include "BL999.h"

#ifdef PLUGIN_086
boolean Plugin_086(byte, char *) {
    BL999::Frame frame;
    if (!BL999::decode(RealPulseWidths + 1, RawSignal.Number, frame)) return false;
    // The checksum is only four bits: require two matching complete frames.
    static bool haveCandidate = false;
    static uint64_t candidateWord = 0;
    static unsigned long candidateAt = 0;
    static bool havePublished = false;
    static uint64_t publishedWord = 0;
    static unsigned long publishedAt = 0;
    const unsigned long now = millis();
    const bool confirmed = haveCandidate && candidateWord == frame.word && (now - candidateAt) <= 2000;
    haveCandidate = true;
    candidateWord = frame.word;
    candidateAt = now;
    if (!confirmed) return false;
    if (!(havePublished && publishedWord == frame.word && (now - publishedAt) <= 3000)) {
        havePublished = true;
        publishedWord = frame.word;
        publishedAt = now;
        // Include the raw channel in ID so ordinary RFLink clients separate sensors.
        const uint16_t identifier = (uint16_t(frame.channel) << 8) | frame.sensorId;
        const uint16_t temperature = frame.temperature < 0 ? uint16_t(-frame.temperature) | 0x8000 : uint16_t(frame.temperature);
        snprintf_P(pbuffer, sizeof(pbuffer), PSTR("20;%02X;BL999;ID=%04X;CHAN=%u;"), PKSequenceNumber++, identifier, frame.channel);
        Serial.print(pbuffer);
        snprintf_P(pbuffer, sizeof(pbuffer), PSTR("TEMP=%04X;HUM=%02u;BAT=%s;"), temperature, frame.humidity, frame.batteryLow ? "LOW" : "OK");
        Serial.println(pbuffer);
    }
    RawSignal.Repeats = true;
    RawSignal.Number = 0;
    return true;
}
#endif
