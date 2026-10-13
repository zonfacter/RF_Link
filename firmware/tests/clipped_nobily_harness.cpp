#define main originalHarnessMain
#include "capture_harness.cpp"
#undef main

int main() {
    ShutterRemote40::Frame input = {0xABCDEF, 0x42, 0x11}, decoded;
    uint8_t full[82];
    assert(ShutterRemote40::encode(input, full, 82, 30));
    assert(ShutterRemote40::decodeClipped(full + 2, 80, 30, decoded));
    assert(decoded.id == input.id && decoded.command == input.command);
    assert(!ShutterRemote40::decodeClipped(full + 2, 79, 30, decoded));
    const uint8_t commands[] = {0x11, 0x33, 0x55, 0x1E, 0x3C};
    for (uint8_t command : commands) {
        ShutterRemote40::Frame sample = {0xABCDEF, 0x42, command};
        assert(ShutterRemote40::encode(sample, full, 82, 30));
        assert(ShutterRemote40::decodeClipped(full + 2, 80, 30, decoded));
        assert(decoded.command == command);
    }
    assert(ShutterRemote40::encode(input, full, 82, 30));
    full[5] = full[4];
    assert(!ShutterRemote40::decodeClipped(full + 2, 80, 30, decoded));
    assert(ShutterRemote40::encode(input, full, 82, 30));
    for (unsigned i = 0; i < 80; ++i) RawSignal.Pulses[i + 1] = full[i + 2];
    RawSignal.Multiply = 30;
    RawSignal.Number = 80;
    assert(!Plugin_084(0, nullptr)); // first clipped packet is not enough
    testNowMs += 3000;
    assert(!Plugin_084(0, nullptr)); // stale matching packet is not enough
    testNowMs += 100;
    assert(Plugin_084(0, nullptr));
    assert(Serial.output.find("CMD=UP;") != std::string::npos);
    Serial.output.clear();

    unsigned count, value;
    while (std::cin >> testNowMs >> count) {
        assert(count < 514);
        for (unsigned i = 1; i <= count; ++i) {
            std::cin >> value;
            assert(value <= 255);
            RawSignal.Pulses[i] = uint8_t(value);
        }
        RawSignal.Number = count;
        Plugin_084(0, nullptr);
        std::cout << Serial.output;
        Serial.output.clear();
    }
}
