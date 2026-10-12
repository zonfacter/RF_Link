#include "HTR008W.h"

#ifdef PLUGIN_085
boolean Plugin_085(byte, char *) {
    HTR008W::Frame frame;
    if (!HTR008W::decode(RawSignal.Pulses + 1, RawSignal.Number, RawSignal.Multiply, frame)) return false;
    snprintf_P(pbuffer, sizeof(pbuffer), PSTR("20;%02X;HTR008W;ID=000001;SWITCH=00;CMD=%s;"),
               PKSequenceNumber++, HTR008W::name(frame.command));
    Serial.println(pbuffer);
    RawSignal.Repeats = true;
    RawSignal.Number = 0;
    return true;
}
#endif

#ifdef PLUGIN_TX_085
boolean PluginTX_085(byte, char *string) {
    const char *prefix = "10;HTR008W;";
    if (strncasecmp(string, prefix, strlen(prefix)) != 0) return false;
    const char *cmd = string + strlen(prefix);
    if (!strncasecmp(cmd,"000001;00;",10)) cmd += 10;
    uint8_t command = !strcasecmp(cmd, "UP") ? 1 : !strcasecmp(cmd, "STOP") ? 2 : !strcasecmp(cmd, "DOWN") ? 3 : 0;
    size_t count = HTR008W::encode(command, RawSignal.Pulses + 1, RAW_BUFFER_SIZE, 30);
    if (!count) return false;
    txInProgress = true;
    digitalWrite(PIN_RF_RX_VCC, LOW);
    digitalWrite(PIN_RF_TX_VCC, HIGH);
    delayMicroseconds(TRANSMITTER_STABLE_DELAY);
    noInterrupts();
    for (size_t i = 0; i < count; i += 2) {
        digitalWrite(PIN_RF_TX_DATA, HIGH);
        delayMicroseconds(uint16_t(RawSignal.Pulses[i + 1]) * 30);
        digitalWrite(PIN_RF_TX_DATA, LOW);
        delayMicroseconds(uint16_t(RawSignal.Pulses[i + 2]) * 30);
    }
    interrupts();
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
