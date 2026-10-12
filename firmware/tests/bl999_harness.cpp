#include <cassert>
#include <iostream>
#include <cstdio>
#include <string>
#include "BL999.h"
using byte = uint8_t;
using boolean = bool;
#define PLUGIN_086
#define PSTR(text) text
#define snprintf_P snprintf
struct { int Number; byte Repeats; } RawSignal;
uint16_t RealPulseWidths[514];
byte PKSequenceNumber = 0;
char pbuffer[60];
unsigned long nowMs = 10000;
unsigned long millis() { return nowMs; }
struct { std::string output; void print(const char *text) { output += text; } void println(const char *text) { output += text; output += '\n'; } } Serial;
#include "../legacy/Plugins/Plugin_086.c"

void makePulses(uint64_t word, uint16_t *widths) {
    for (unsigned i = 0; i < 36; ++i) {
        widths[2*i] = 380;
        widths[2*i+1] = (word & (uint64_t(1) << (35-i))) ? 3960 : 1890;
    }
    widths[72] = 380; widths[73] = 4408;
}

int main() {
    uint16_t widths[74]; BL999::Frame frame;
    makePulses(0x140BB0DD5ULL,widths);
    assert(BL999::decode(widths,74,frame));
    assert(frame.sensorId==8 && frame.channel==1 && frame.temperature==221 && frame.humidity==31 && !frame.batteryLow);
    makePulses(0xE44C1F73FULL,widths);
    assert(BL999::decode(widths,74,frame));
    assert(frame.temperature==-125 && frame.humidity==50);
    assert(!BL999::decode(widths,72,frame));
    widths[0]=1500;assert(!BL999::decode(widths,74,frame));
    makePulses(0x140BB0DD5ULL,widths);widths[1]=3960;
    assert(!BL999::decode(widths,74,frame)); // corrupted checksum
    unsigned count,value;
    while (std::cin >> count) {
        assert(count < 514);
        for (unsigned i=1;i<=count;++i) { std::cin>>value;RealPulseWidths[i]=uint16_t(value); }
        RawSignal.Number=count;
        const auto before=Serial.output.size();
        Plugin_086(0,nullptr);
        std::cout<<Serial.output.substr(before);
        nowMs+=100;
    }
    const auto before=Serial.output.size();
    makePulses(0x140BB0DD5ULL,RealPulseWidths+1);
    nowMs+=10000;RawSignal.Number=74;assert(!Plugin_086(0,nullptr)); // stale candidate
    assert(Serial.output.size()==before);
    nowMs+=100;RawSignal.Number=74;assert(Plugin_086(0,nullptr));
    const auto after=Serial.output.size();assert(after>before);
    nowMs+=100;RawSignal.Number=74;assert(Plugin_086(0,nullptr));
    assert(Serial.output.size()==after); // repeat suppression
}
