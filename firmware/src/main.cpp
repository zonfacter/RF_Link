// Keep the legacy Arduino tabs in their original compilation order.
#include <Arduino.h>
#include <ctype.h>
bool RFTiming = false;
uint16_t RealPulseWidths[514];

void setup();
void loop();
unsigned long str2int(char *string);
int str2cmd(char *command);
float ul2float(unsigned long value);
byte PluginInitCall(byte function, char *string);
byte PluginTXInitCall(byte function, char *string);
byte PluginRXCall(byte function, char *string);
byte PluginTXCall(byte function, char *string);
boolean ScanEvent();
boolean FetchSignal(byte pin, boolean state);
void RawSendRF();
boolean ProbeSignal();

#include "../legacy/RFLink.ino"
#include "../legacy/Base.ino"
#include "../legacy/Misc.ino"
#include "../legacy/Plugin.ino"
#include "../legacy/RawSignal.ino"
#include "TimingProbe.h"

