#include <iostream>
#include <iomanip>
#include <vector>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <strings.h>
#include <string>
#include "ShutterRemote40.h"

// Exercise the actual RFLink adapter and command parser without hardware.
using byte = uint8_t;
using boolean = bool;
#define PLUGIN_084
#define PLUGIN_TX_084
#define PSTR(text) text
#define snprintf_P snprintf
#define RAW_BUFFER_SIZE 512
#define PIN_RF_RX_VCC 16
#define PIN_RF_TX_VCC 15
#define PIN_RF_TX_DATA 14
#define TRANSMITTER_STABLE_DELAY 500
#define LOW 0
#define HIGH 1
struct { int Number; byte Multiply; byte Repeats; unsigned long Time; byte Pulses[514]; } RawSignal;
char pbuffer[60];
byte PKSequenceNumber = 0;
bool txInProgress;
unsigned long lastTX;
struct {
    std::string output;
    void print(const char *text) { output += text; }
    void println(const char *text) { output += text; output += '\n'; }
} Serial;
std::vector<unsigned> emitted;
bool dataWritten;
void digitalWrite(int pin, int) { dataWritten = pin == PIN_RF_TX_DATA; }
void delayMicroseconds(unsigned duration) { if (dataWritten) emitted.push_back(duration); }
void noInterrupts() {}
void interrupts() {}
void RFLinkHW() {}
unsigned long testNowMs = 1234;
unsigned long millis() { return testNowMs; }
#include "../legacy/Plugins/Plugin_084.c"
#define PLUGIN_085
#define PLUGIN_TX_085
#include "../legacy/Plugins/Plugin_085.c"
uint16_t RealPulseWidths[514];

static bool transmit(const char *text) {
    char buffer[100];
    strcpy(buffer, text);
    emitted.clear();
    dataWritten = false;
    bool result = PluginTX_084(0, buffer);
    assert(strcmp(buffer, text) == 0);
    return result;
}

int main(int argc, char **) {
    using namespace ShutterRemote40;
    // Encode/decode all command bytes and channels; preserve the final bit.
    for (unsigned channel = 0; channel < 256; ++channel) {
        for (unsigned command = 0; command < 256; ++command) {
            Frame input = {0x98461A, uint8_t(channel), uint8_t(command)}, output;
            uint8_t pulses[82];
            assert(encode(input, pulses, 82, 30));
            assert(decode(pulses, 82, 30, output));
            assert(output.id == input.id && output.channelByte == channel && output.command == command);
            assert(!decode(pulses, 81, 30, output));
            assert(!decode(pulses, 82, 0, output));
            pulses[3] = pulses[2]; // invalid equal-length pair
            assert(!decode(pulses, 82, 30, output));
        }
    }
    uint8_t pulses[82];
    Frame frame = {0x1000000, 0x43, 0x11};
    assert(!encode(frame, pulses, 82, 30));
    frame.id = 0x98461A;
    assert(!encode(frame, pulses, 81, 30));
    assert(!encode(frame, pulses, 82, 0));

    assert(transmit("10;ShutterRemote40;98461A;43;UP"));
    assert(emitted.size() == 6 * 82);
    assert(emitted[0] == 4800 && emitted[1] == 1470);
    assert(emitted[2] == 660 && emitted[3] == 300); // ID starts with a one.
    for (unsigned repeat = 0; repeat < 6; ++repeat) {
        for (unsigned i = 0; i < 82; ++i) pulses[i] = emitted[repeat * 82 + i] / 30;
        assert(decode(pulses, 82, 30, frame));
        assert(frame.id == 0x98461A && frame.channelByte == 0x43 && frame.command == 0x11);
        assert(emitted[repeat * 82 + 81] == 6990);
    }
    assert(transmit("10;ShutterRemote40;98461A;45;3C"));
    assert(decode(RawSignal.Pulses + 1, 82, 30, frame));
    assert(frame.channelByte == 0x45 && frame.command == 0x3C);
    const char *invalid[] = {
        "10;Other;98461A;43;UP", "10;ShutterRemote40;98461A;43;",
        "10;ShutterRemote40;98461A;43;UP;EXTRA", "10;ShutterRemote40;98461G;43;UP",
        "10;ShutterRemote40;98461A;GG;UP", "10;ShutterRemote40;98461A;43;UP_MORE",
        "10;ShutterRemote40;98461A;43;123", "10;ShutterRemote40;1;43;UP"
    };
    for (const char *text : invalid) {
        assert(!transmit(text));
        assert(emitted.empty());
    }
    frame = {0x98461A, 0x43, 0x11};
    assert(encode(frame, RawSignal.Pulses + 1, 512, 30));
    RawSignal.Number = 82;
    RawSignal.Multiply = 30;
    Serial.output.clear();
    assert(Plugin_084(0, nullptr));
    assert(Serial.output == "20;00;ShutterRemote40;ID=98461A;SWITCH=43;CHANNELBYTE=43;RAW=11;CMD=UP;\n");
    assert(RawSignal.Number == 0 && RawSignal.Repeats);

    for (uint8_t cmd = 1; cmd <= 3; ++cmd) {
        uint8_t htrPulses[230];
        size_t size = HTR008W::encode(cmd, htrPulses, sizeof(htrPulses), 30);
        assert(size == (cmd == 1 ? 152 : cmd == 2 ? 230 : 154));
        HTR008W::Frame decoded;
        assert(HTR008W::decode(htrPulses, size, 30, decoded));
        assert(decoded.command == cmd);
        htrPulses[5 + 8] = 13; // corrupt a fixed learned fingerprint symbol
        assert(!HTR008W::decode(htrPulses, size, 30, decoded));
        assert(!HTR008W::decode(htrPulses, 75, 30, decoded));
        char tx[32];
        snprintf(tx, sizeof(tx), "10;HTR008W;%s", HTR008W::name(cmd));
        emitted.clear(); dataWritten = false;
        assert(PluginTX_085(0, tx));
        assert(emitted.size() == size && emitted[0] == 1890 && emitted.back() == 7500);
        for (size_t i = 0; i < size; ++i) htrPulses[i] = emitted[i] / 30;
        assert(HTR008W::decode(htrPulses, size, 30, decoded));
        assert(decoded.command == cmd);
    }
    char invalidHtr[] = "10;HTR008W;UP_EXTRA";
    emitted.clear();
    assert(!PluginTX_085(0, invalidHtr) && emitted.empty());

    unsigned count, value;
    while (std::cin >> count) {
        std::vector<uint8_t> samples;
        for (unsigned i = 0; i < count; ++i) {
            std::cin >> value;
            samples.push_back(uint8_t(value));
        }
        HTR008W::Frame htr;
        if (argc > 1 && HTR008W::decode(samples.data(), samples.size(), 30, htr)) {
            std::cout << "HTR:" << HTR008W::name(htr.command) << '\n';
        } else if (argc == 1 && decode(samples.data(), samples.size(), 30, frame)) {
            std::cout << std::hex << std::uppercase << std::setfill('0')
                      << std::setw(6) << frame.id << std::setw(2) << unsigned(frame.channelByte)
                      << std::setw(2) << unsigned(frame.command) << '\n';
        } else std::cout << "REJECT\n";
    }
    return 0;
}
