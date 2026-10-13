// Decoder and transmitter for the 40-bit PWM frames captured locally.
// Separate from BrelMotor: the observed timings differ from Dooya Plugin 083.
#include "ShutterRemote40.h"

#ifdef PLUGIN_084
boolean Plugin_084(byte, char *) {
    ShutterRemote40::Frame frame;
    if (!ShutterRemote40::decode(RawSignal.Pulses + 1, RawSignal.Number,
                                 RawSignal.Multiply, frame)) {
        if (!ShutterRemote40::decodeClipped(RawSignal.Pulses + 1, RawSignal.Number,
                                           RawSignal.Multiply, frame)) return false;
        static bool haveCandidate = false;
        static ShutterRemote40::Frame candidate;
        static unsigned long candidateAt = 0;
        const unsigned long now = millis();
        const bool confirmed = haveCandidate && candidate.id == frame.id &&
            candidate.channelByte == frame.channelByte && candidate.command == frame.command &&
            (now - candidateAt) <= 2000;
        candidate = frame;
        candidateAt = now;
        haveCandidate = true;
        if (!confirmed) return false;
    }
    snprintf_P(pbuffer, sizeof(pbuffer),
        PSTR("20;%02X;ShutterRemote40;ID=%06lX;"), PKSequenceNumber++, (unsigned long)frame.id);
    Serial.print(pbuffer);
    snprintf_P(pbuffer, sizeof(pbuffer),
        PSTR("SWITCH=%02X;CHANNELBYTE=%02X;RAW=%02X;CMD=%s;"),
        frame.channelByte, frame.channelByte, frame.command,
        ShutterRemote40::commandName(frame.command));
    Serial.println(pbuffer);
    RawSignal.Repeats = true;
    RawSignal.Number = 0;
    return true;
}
#endif

#ifdef PLUGIN_TX_084
// Parse without modifying the shared command buffer used by other plugins.
static bool shutter40Hex(const char *text, byte digits, uint32_t &value) {
    value = 0;
    for (byte i = 0; i < digits; ++i) {
        char c = text[i];
        byte nibble;
        if (c >= '0' && c <= '9') nibble = c - '0';
        else if (c >= 'a' && c <= 'f') nibble = c - 'a' + 10;
        else if (c >= 'A' && c <= 'F') nibble = c - 'A' + 10;
        else return false;
        value = (value << 4) | nibble;
    }
    return true;
}

boolean PluginTX_084(byte, char *string) {
    // 10;ShutterRemote40;98461A;43;UP
    const char *prefix = "10;ShutterRemote40;";
    size_t prefixLength = strlen(prefix);
    if (strncasecmp(string, prefix, prefixLength) != 0) return false;
    const char *idText = string + prefixLength;
    if (strlen(idText) < 12 || idText[6] != ';' || idText[9] != ';') return false;
    uint32_t id, channel;
    if (!shutter40Hex(idText, 6, id) || !shutter40Hex(idText + 7, 2, channel)) return false;
    const char *cmd = idText + 10;
    uint8_t command;
    uint32_t raw;
    if (!strcasecmp(cmd, "UP")) command = 0x11;
    else if (!strcasecmp(cmd, "DOWN")) command = 0x33;
    else if (!strcasecmp(cmd, "STOP")) command = 0x55;
    else if (strlen(cmd) == 2 && shutter40Hex(cmd, 2, raw)) command = uint8_t(raw);
    else return false;

    if (channel <= 0x0F) channel |= 0x40; // accept older logical-channel commands too
    ShutterRemote40::Frame frame = {id, uint8_t(channel), command};
    if (!ShutterRemote40::encode(frame, RawSignal.Pulses + 1, RAW_BUFFER_SIZE, 30))
        return false;
    RawSignal.Number = 82;
    RawSignal.Multiply = 30;
    txInProgress = true;
    digitalWrite(PIN_RF_RX_VCC, LOW);
    digitalWrite(PIN_RF_TX_VCC, HIGH);
    delayMicroseconds(TRANSMITTER_STABLE_DELAY);
    for (byte repeat = 0; repeat < 6; ++repeat) {
        // Retain the final 6990 us gap (legacy RawSendRF overwrites it).
        noInterrupts();
        for (byte pulse = 1; pulse <= 82; pulse += 2) {
            digitalWrite(PIN_RF_TX_DATA, HIGH);
            delayMicroseconds(uint16_t(RawSignal.Pulses[pulse]) * 30);
            digitalWrite(PIN_RF_TX_DATA, LOW);
            delayMicroseconds(uint16_t(RawSignal.Pulses[pulse + 1]) * 30);
        }
        interrupts();
    }
    digitalWrite(PIN_RF_TX_DATA, LOW);
    digitalWrite(PIN_RF_TX_VCC, LOW);
    digitalWrite(PIN_RF_RX_VCC, HIGH);
    RFLinkHW();
    lastTX = millis();
    txInProgress = false;
    RawSignal.Number = 0;
    RawSignal.Time = 0;
    RawSignal.Repeats = 0;
    return true;
}
#endif
