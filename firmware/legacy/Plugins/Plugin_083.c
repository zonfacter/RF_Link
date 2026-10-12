//#######################################################################################################
//## RFLink Plugin-083: BrelMotor (Bidirektionaler RX + TX)                                            ##
//## Kompatibel zu RFLink und RFLinkLoader – Produktionsreif                                           ##
//#######################################################################################################

#ifdef PLUGIN_083

#define PLUGIN_ID_083 083
#define PLUGIN_NAME "BrelMotor"

// ------------------------
// Kommandos
// ------------------------
#define CMD_UP    1
#define CMD_DOWN  0
#define CMD_STOP  2

#define PULSE_MID_THRESHOLD 384

// =======================
// Empfangslogik (RX)
// =======================
boolean Plugin_083(byte function, char *string) {
    // Funktion wird nur ausgeführt, wenn genug Pulse empfangen wurden
    if (RawSignal.Number != 82) return false;

    byte data[10];
    byte idx = 0;

    // Dekodierung der empfangenen Pulse in 8-Bit-Daten
    for (int j = 3; j < RawSignal.Number - 1; j += 8) {
        byte val = 0;
        for (int i = 0; i < 8; i += 2) {
            val <<= 1;
            if (RawSignal.Pulses[j + i] < PULSE_MID_THRESHOLD)
                val |= 0;
            else
                val |= 1;
        }
        data[idx++] = val;
    }

    // Adresse (6 Nibbles)
    unsigned long address = 0;
    for (int i = 0; i < 6; i++) {
        address = (address << 4) | (data[i] & 0x0F);
    }

    byte channel = data[7];
    byte commandByte = (data[8] << 4) | (data[9] & 0x0F);

    byte command;
    const char *commandStr;

    // Befehl dekodieren
    switch (commandByte) {
        case 0x11: command = CMD_UP; commandStr = "UP"; break;
        case 0x33: command = CMD_DOWN; commandStr = "DOWN"; break;
        case 0x55: command = CMD_STOP; commandStr = "STOP"; break;
        default: return false;  // unbekannter Befehl
    }

    // Ausgabe über serielle Schnittstelle im RFLink-Format
    sprintf_P(pbuffer, PSTR("20;%02X;%s;ID=%06lX;SWITCH=%d;CMD=%s;"),
              PKSequenceNumber++, PLUGIN_NAME, address, channel, commandStr);
    Serial.println(pbuffer);

    // Signal verarbeiten
    RawSignal.Repeats = true;
    RawSignal.Number = 0;
    return true;
}
#endif // PLUGIN_083

// =======================
// Sendelogik (TX)
// =======================
#ifdef PLUGIN_TX_083

boolean PluginTX_083(byte function, char *string) {
    // Nur verarbeiten, wenn der Gerätename enthalten ist
    if (!strstr(string, "BrelMotor")) return false;

    // Eingabebeispiel: 10;BrelMotor;2B40C8;01;UP;
    char *token;
    byte fields = 0;
    char *address = nullptr;
    char *channel = nullptr;
    char *cmd = nullptr;

    token = strtok(string, ";");
    while (token != nullptr) {
        switch (fields) {
            case 2: address = token; break;
            case 3: channel = token; break;
            case 4: cmd = token; break;
        }
        token = strtok(nullptr, ";");
        fields++;
    }

    if (!address || !channel || !cmd) return false;

    byte commandByte;
    if (!strcasecmp(cmd, "UP")) commandByte = 0x11;
    else if (!strcasecmp(cmd, "DOWN")) commandByte = 0x33;
    else if (!strcasecmp(cmd, "STOP")) commandByte = 0x55;
    else return false;

    // Hexadezimalstring zusammensetzen: Adresse + Kanal + Befehl
    char fullHex[19];
    snprintf(fullHex, sizeof(fullHex), "%s%s%02X", address, channel, commandByte);

    int pulseIndex = 0;
    RawSignal.Multiply = 32;
    RawSignal.Repeats = 6;

    // Startsequenz
    RawSignal.Pulses[++pulseIndex] = 141;  // 4512 µs
    RawSignal.Pulses[++pulseIndex] = 46;   // 1472 µs

    // Senden der Datenbits (4 Bit pro Hex-Zeichen)
    for (byte i = 0; i < strlen(fullHex); i++) {
        char hexStr[2] = { fullHex[i], '\0' };
        byte hexVal = strtol(hexStr, NULL, 16);
        for (int b = 3; b >= 0; b--) {
            if ((hexVal >> b) & 1) {
                RawSignal.Pulses[++pulseIndex] = 19;  // 608 µs
                RawSignal.Pulses[++pulseIndex] = 6;   // 192 µs
            } else {
                RawSignal.Pulses[++pulseIndex] = 6;   // 192 µs
                RawSignal.Pulses[++pulseIndex] = 19;  // 608 µs
            }
        }
    }

    // Endsequenz
    RawSignal.Pulses[++pulseIndex] = 0;
    RawSignal.Pulses[++pulseIndex] = 156;  // 4992 µs

    RawSignal.Number = pulseIndex;

    RawSendRF();  // Signal über RF senden
    return true;
}
#endif // PLUGIN_TX_083
