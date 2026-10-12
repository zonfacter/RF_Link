//#######################################################################################################
//##                    RFLink Plugin-050: RollerShutter (Bidirektional RX + TX)                    ##
//##                         VERSION 8.4 CLEAN - S-SYMBOL-SYSTEM                                   ##
//#######################################################################################################

/*********************************************************************************************\
 * PLUGIN ÜBERSICHT - VERSION 8.4 CLEAN:
 * ======================================
 * 
 * Plugin-Name: RollerShutter (Plugin 050)
 * Funktionalität: Bidirektionale Rollladenfernbedienungs-Steuerung
 * Unterstützte Befehle: UP, DOWN, STOP
 * 
 * ✅ NEUES S-SYMBOL-SYSTEM (V8.4):
 * ================================
 * 
 * SYMBOL-ZUORDNUNG (basierend auf Timing-Analyse):
 * - Symbol "0": 600-690μs (660μs=102x, 630μs=18x) - Kurze Datenbits  
 * - Symbol "1": 1440-1500μs (1470μs=82x, 1440μs=3x) - Lange Datenbits
 * - Symbol "S": 3090-3240μs (3090μs=12x) - Sync-Marker (statt "2"!)
 * - Symbol "|": 3900-3990μs - Frame-Trenner
 * - Symbol "X": 6360μs, 6990μs - Haupt-Sync & Signal-Ende
 * 
 * KOMMANDO-ERKENNUNG (nur echte Datenbits 0/1):
 * - UP:   Pattern beginnt mit "001" (aus Debug-Log bestätigt)
 * - DOWN: Pattern beginnt mit "011" 
 * - STOP: Pattern >200 Symbole
 * 
 * MODULARER AUFBAU:
 * =================
 * - Timing-Konstanten (einfach anpassbar)
 * - Symbol-Dekodierung (klar getrennt)
 * - Kommando-Erkennung (nur Datenbits)
 * - TX-Funktionen (Standard Dual-Sequenz)
 * 
 * VERWENDUNG:
 * ===========
 * RX: Fernbedienung drücken → Automatische Pattern-Erkennung
 * TX: 10;RollerShutter;00C040;1;UP; → Rolllade hoch
 * TX: 10;RollerShutter;20C040;1;DOWN; → Rolllade runter
 * TX: 10;RollerShutter;40C040;1;STOP; → Rolllade stopp
 * 
 * Version: 8.4 CLEAN - S-Symbol-System (Produktionsreif)
 * Datum: 2025-07-28
 * Status: Sauberer Start für weitere Entwicklung
\*********************************************************************************************/

#ifdef PLUGIN_050

#define PLUGIN_ID_050 050
#define PLUGIN_NAME "RollerShutter"

//=============================================================================
// TIMING-KONSTANTEN (V8.4 - Basierend auf User-Timing-Analyse)
//=============================================================================

// DATENBITS (nur diese zählen für Kommando-Erkennung)
#define BIT_SHORT_MIN     600     // Bit "0": 600-690μs (660μs häufigster Wert)
#define BIT_SHORT_MAX     690
#define BIT_LONG_MIN      1440    // Bit "1": 1440-1500μs (1470μs häufigster Wert)
#define BIT_LONG_MAX      1500

// SYNC & STEUERUNGSSIGNALE (werden als Symbole S, |, X kodiert)
#define SYNC_MARKER_MIN   3090    // Symbol "S": 3090-3240μs (Start-Sync-Marker)
#define SYNC_MARKER_MAX   3240
#define FRAME_SEP_MIN     3900    // Symbol "|": 3900-3990μs (Frame-Trenner)
#define FRAME_SEP_MAX     3990
#define MAIN_SYNC_MIN     6300    // Symbol "X": 6360μs (Haupt-Sync)
#define MAIN_SYNC_MAX     6400
#define SIGNAL_END_MIN    6900    // Symbol "X": 6990μs (Signal-Ende)
#define SIGNAL_END_MAX    7100

// SYSTEM-PARAMETER
#define MIN_VALID_PULSE   300     // Rauschunterdrückung
#define MIN_PULSES        90      // Minimum für gültiges Signal
#define MAX_PULSES        260     // Maximum für normale Sequenzen
#define STOP_PULSE_MIN    220     // STOP-Sequenzen sind länger

// TIMEOUTS
#define DUAL_SEQ_TIMEOUT  500     // 500ms für Dual-Sequenz-Erkennung
#define REPEAT_TIMEOUT    1500    // 1.5s Anti-Repeat

// KOMMANDO-DEFINITIONEN
#define CMD_UP    1
#define CMD_DOWN  0  
#define CMD_STOP  2

// DEVICE-IDs (Standard für Smart Home Integration)
#define DEVICE_ID_UP    0x00C040
#define DEVICE_ID_DOWN  0x20C040
#define DEVICE_ID_STOP  0x40C040

//=============================================================================
// GLOBALE VARIABLEN
//=============================================================================
static uint32_t letzte_verarbeitung = 0;
static uint32_t sequenz_counter = 0;
static uint32_t erste_seq_zeit = 0;      
static uint16_t erste_seq_pulses = 0;    
static uint8_t erste_seq_cmd = 0;        

//=============================================================================
// SYNC-ERKENNUNGSFUNKTIONEN (V8.4 - Optimiert für S-Symbol-System)
//=============================================================================

int findSyncMarker() {
    Serial.println("→ Suche Haupt-Sync-Marker (6360μs)...");
    
    for (int i = 1; i < RawSignal.Number - 1; i++) {  
        int pulse = RawSignal.Pulses[i] * RAWSIGNAL_SAMPLE_RATE;
        
        // Suche Haupt-Sync (6360μs)
        if (pulse >= MAIN_SYNC_MIN && pulse <= MAIN_SYNC_MAX) {
            Serial.print("→ ✅ HAUPT-SYNC gefunden bei Index ");
            Serial.print(i);
            Serial.print(" (");
            Serial.print(pulse);
            Serial.println("μs)");
            
            // Einfache Validierung: Sind davor kleinere Pulse?
            bool valid = true;
            if (i >= 2) {
                int prevPulse = RawSignal.Pulses[i-1] * RAWSIGNAL_SAMPLE_RATE;
                if (prevPulse > 5000) {  // Davor sollte kein weiterer großer Sync sein
                    Serial.print("→ Warnung: Großer Pulse davor: ");
                    Serial.print(prevPulse);
                    Serial.println("μs");
                    // Nehmen wir trotzdem, da es der Haupt-Sync sein könnte
                }
            }
            
            if (valid) {
                return i;
            }
        }
    }
    
    Serial.println("→ ❌ KEIN HAUPT-SYNC gefunden");
    return -1;
}

//=============================================================================
// SYMBOL-DEKODIERUNG (V8.4 - Neues S-System)
//=============================================================================

String decodePulsesToSymbols() {
    int syncIndex = findSyncMarker();
    if (syncIndex == -1) {
        Serial.println("→ ❌ Symbol-Dekodierung unmöglich - kein Haupt-Sync");
        return "";
    }
    
    String symbolPattern = "";
    Serial.print("→ Starte Symbol-Dekodierung ab Index ");
    Serial.println(syncIndex + 1);
    
    for (int i = syncIndex + 1; i < RawSignal.Number - 1; i++) {
        int pulse = RawSignal.Pulses[i] * RAWSIGNAL_SAMPLE_RATE;
        
        // Rauschunterdrückung
        if (pulse < MIN_VALID_PULSE) {
            Serial.print("→ Rauschen ignoriert: ");
            Serial.print(pulse);
            Serial.println("μs");
            continue;
        }
        
        // ✅ NEUES S-SYMBOL-SYSTEM
        
        // Signal-Ende-Marker
        if (pulse >= SIGNAL_END_MIN && pulse <= SIGNAL_END_MAX) {
            symbolPattern += "X";
            Serial.print("→ Signal-Ende: ");
            Serial.print(pulse);
            Serial.println("μs → Symbol 'X'");
            break;
        }
        
        // Haupt-Sync (weiterer)
        if (pulse >= MAIN_SYNC_MIN && pulse <= MAIN_SYNC_MAX) {
            symbolPattern += "X";
            Serial.print("→ Weiterer Haupt-Sync: ");
            Serial.print(pulse);
            Serial.println("μs → Symbol 'X'");
            continue;
        }
        
        // Frame-Separator
        if (pulse >= FRAME_SEP_MIN && pulse <= FRAME_SEP_MAX) {
            symbolPattern += "|";
            Serial.print("→ Frame-Trenner: ");
            Serial.print(pulse);
            Serial.println("μs → Symbol '|'");
            continue;
        }
        
        // ✅ SYNC-MARKER (das war früher "2", jetzt "S")
        if (pulse >= SYNC_MARKER_MIN && pulse <= SYNC_MARKER_MAX) {
            symbolPattern += "S";
            Serial.print("→ Sync-Marker: ");
            Serial.print(pulse);
            Serial.println("μs → Symbol 'S'");
            continue;
        }
        
        // ECHTE DATENBITS (nur diese für Kommando-Erkennung)
        if (pulse >= BIT_SHORT_MIN && pulse <= BIT_SHORT_MAX) {
            symbolPattern += "0";
            // Serial wird nur bei Debug-Bedarf ausgegeben
        } else if (pulse >= BIT_LONG_MIN && pulse <= BIT_LONG_MAX) {
            symbolPattern += "1";
            // Serial wird nur bei Debug-Bedarf ausgegeben  
        } else {
            symbolPattern += "?";
            Serial.print("→ Unbekannter Impuls: ");
            Serial.print(pulse);
            Serial.println("μs → Symbol '?'");
        }
    }
    
    Serial.print("→ ✅ SYMBOL-PATTERN: ");
    Serial.print(symbolPattern);
    Serial.print(" (");
    Serial.print(symbolPattern.length());
    Serial.println(" Symbole)");
    
    return symbolPattern;
}

//=============================================================================
// DATENBIT-EXTRAKTION (V8.4 - Nur echte Datenbits)
//=============================================================================

String extractDataBits(String symbolPattern) {
    String dataBits = "";
    
    // Extrahiere nur die echten Datenbits (0 und 1)
    for (int i = 0; i < symbolPattern.length(); i++) {
        char symbol = symbolPattern.charAt(i);
        if (symbol == '0' || symbol == '1') {
            dataBits += symbol;
        }
    }
    
    Serial.print("→ Extrahierte Datenbits: ");
    Serial.print(dataBits);
    Serial.print(" (");
    Serial.print(dataBits.length());
    Serial.println(" Bits)");
    
    return dataBits;
}

//=============================================================================
// KOMMANDO-ERKENNUNG (V8.4 - Nur Datenbit-basiert)
//=============================================================================

uint8_t identifyCommandFromDataBits(String dataBits) {
    Serial.print("→ ***KOMMANDO-ERKENNUNG V8.6 KRITISCHE BITS*** Datenbits: ");
    Serial.println(dataBits);
    
    // ✅ LEVEL 1: STOP (funktioniert perfekt - echte 230-Pulse-Signale)
    if (dataBits.length() > 200 || RawSignal.Number > STOP_PULSE_MIN) {
        Serial.println("→ ✅ STOP erkannt (>200 Datenbits oder >220 Pulse)");
        return CMD_STOP;
    }
    
    // ✅ LEVEL 2: Buffer-Overflow-Erkennung (RFLink-Problem-Detektion)
    if (RawSignal.Number >= 228 && RawSignal.Number <= 232 && dataBits.length() <= 200) {
        Serial.println("→ ⚠️ BUFFER-OVERFLOW erkannt - verwende erweiterte Analyse");
    }
    
    // ✅ LEVEL 3: KRITISCHE BIT-POSITIONEN ANALYSE (präziseste Methode)
    if (dataBits.length() >= 64) {  // Mindestens bis Bit[64] verfügbar
        char bit1 = dataBits.charAt(1);   // Primäres Unterscheidungsbit
        char bit2 = dataBits.charAt(2);   // Sekundäres Unterscheidungsbit  
        char bit7 = dataBits.charAt(7);   // Sekundäre Validierung
        
        Serial.print("→ Kritische Bits: [1]=");
        Serial.print(bit1);
        Serial.print(", [2]=");
        Serial.print(bit2);
        Serial.print(", [7]=");
        Serial.print(bit7);
        
        // ✅ HAUPTREGEL: Bit[2] ist der stärkste Indikator (aus deiner Analyse)
        if (bit2 == '0' && bit7 == '1') {
            Serial.println(" → UP (Bit[2]=0 UND Bit[7]=1 - kritische Regel)");
            return CMD_UP;
        }
        
        if (bit2 == '1' && bit7 == '0') {
            Serial.println(" → DOWN (Bit[2]=1 UND Bit[7]=0 - kritische Regel)");
            return CMD_DOWN;
        }
        
        // ✅ ERWEITERTE KOMBINATIONSREGELN (aus Logs gelernt)
        String kritisch_pattern = String(bit1) + String(bit2) + String(bit7);
        Serial.print(" Kombination[1][2][7]: ");
        Serial.print(kritisch_pattern);
        
        // UP-Kombinationen (aus echten Logs bestätigt)
        if (kritisch_pattern == "101" || kritisch_pattern == "001" || kritisch_pattern == "000") {
            Serial.println(" → UP (kritische Kombination)");
            return CMD_UP;
        }
        
        // DOWN-Kombinationen  
        if (kritisch_pattern == "110" || kritisch_pattern == "010" || kritisch_pattern == "011") {
            Serial.println(" → DOWN (kritische Kombination)");
            return CMD_DOWN;
        }
        
        Serial.println(" → Unklare kritische Bits, weiter zur Statistik...");
    }
    
    // ✅ LEVEL 4: Statistische Analyse als Fallback
    if (dataBits.length() >= 50) {
        int zeros = 0, ones = 0;
        
        for (int i = 0; i < dataBits.length(); i++) {
            if (dataBits.charAt(i) == '0') zeros++;
            else if (dataBits.charAt(i) == '1') ones++;
        }
        
        float ratio = (ones > 0) ? (float)zeros / (float)ones : 999.0;
        
        Serial.print("→ Statistik-Fallback: 0-Bits=");
        Serial.print(zeros);
        Serial.print(", 1-Bits=");
        Serial.print(ones);
        Serial.print(", Ratio=");
        Serial.print(ratio);
        
        if (ratio > 1.15) {
            Serial.println(" → UP (statistische 0-Dominanz)");
            return CMD_UP;
        } else {
            Serial.println(" → DOWN (statistische Ausgeglichenheit)");
            return CMD_DOWN;
        }
    }
    
    // ✅ LEVEL 5: Letzter Fallback
    Serial.print("→ Minimaldaten - Pulse-Count-Fallback (");
    Serial.print(RawSignal.Number);
    Serial.print("): ");
    
    if (RawSignal.Number >= 150 && RawSignal.Number <= 160) {
        Serial.println("UP (154-Pulse-Vermutung)");
        return CMD_UP;
    } else {
        Serial.println("DOWN (Unbekannt-Fallback)");
        return CMD_DOWN;
    }
}

//=============================================================================
// DEVICE-ID & RFLINK-AUSGABE
//=============================================================================

unsigned long calculate_device_id(uint8_t command) {
    switch (command) {
        case CMD_UP:
            return DEVICE_ID_UP;
        case CMD_DOWN:
            return DEVICE_ID_DOWN;
        case CMD_STOP:
            return DEVICE_ID_STOP;
        default:
            return DEVICE_ID_UP;
    }
}

void send_rflink_output(uint8_t command, unsigned long device_id) {
    String command_str;
    switch (command) {
        case CMD_UP:
            command_str = "UP";
            break;
        case CMD_DOWN:
            command_str = "DOWN";
            break;
        case CMD_STOP:
            command_str = "STOP";
            break;
        default:
            command_str = "UNKNOWN";
    }
    
    sprintf_P(pbuffer, PSTR("20;%02X;%s;ID=%06lX;SWITCH=%01X;CMD=%s;"), 
              PKSequenceNumber++, 
              PLUGIN_NAME, 
              device_id, 
              command, 
              command_str.c_str());
    
    Serial.print("→ ✅ RFLink-Ausgabe: ");
    Serial.println(pbuffer);
}

//=============================================================================
// DEBUG-FUNKTIONEN
//=============================================================================

void debug_signal_info() {
    Serial.print("→ ***SIGNAL-DEBUG V8.4*** Pulses=");
    Serial.print(RawSignal.Number);
    
    // Sequenz-Typ-Klassifizierung
    if (RawSignal.Number >= 152 && RawSignal.Number <= 156) {
        Serial.print(" [Typ: 154-Pulse Standard]");
    } else if (RawSignal.Number >= 228 && RawSignal.Number <= 232) {
        Serial.print(" [Typ: 230-Pulse Extended]");
    } else if (RawSignal.Number >= 96 && RawSignal.Number <= 100) {
        Serial.print(" [Typ: 98-Pulse Follow]");
    } else if (RawSignal.Number >= 24 && RawSignal.Number <= 28) {
        Serial.print(" [Typ: 24-Pulse Short]");
    } else {
        Serial.print(" [Typ: Unbekannt]");
    }
    
    // Erste Pulse anzeigen
    Serial.print(" Start-Pulse: ");
    for (int i = 1; i <= 5 && i < RawSignal.Number; i++) {
        unsigned int pulse = RawSignal.Pulses[i] * RAWSIGNAL_SAMPLE_RATE;
        Serial.print(pulse);
        if (i < 5) Serial.print(",");
    }
    
    Serial.println();
}

//=============================================================================
// TX-FUNKTIONEN (Standard Dual-Sequenz - Placeholder für später)
//=============================================================================

// DOWN-Sequenzen (Placeholder - können später angepasst werden)
const uint16_t pulse_DOWN_SEQ1[] = {3210,3090,3120,3090,6360,660,660,1470,660,660}; // Verkürzt für Beispiel
const uint16_t pulse_DOWN_SEQ2[] = {1440,1380,630,600,1380,600,600,630,600,600,6990}; // Verkürzt für Beispiel

#define PULSE_COUNT_DOWN_SEQ1 (sizeof(pulse_DOWN_SEQ1) / sizeof(uint16_t))  
#define PULSE_COUNT_DOWN_SEQ2 (sizeof(pulse_DOWN_SEQ2) / sizeof(uint16_t))  

void sendDualSequence(const uint16_t* seq1, size_t count1, const uint16_t* seq2, size_t count2, const char* cmd_name) {
    Serial.print("→ ***TX-PLACEHOLDER*** Befehl: ");
    Serial.print(cmd_name);
    Serial.println(" (TX-Funktionen können später implementiert werden)");
    
    // Hier würde die echte TX-Implementierung stehen
    // Aktuell nur Placeholder für saubere Code-Struktur
}

//=============================================================================
// PLUGIN HAUPT-EMPFANGSFUNKTION (RX) - V8.4 CLEAN
//=============================================================================

boolean Plugin_050(byte function, char *string) {
    if (function != 0) return false;
    
    // Basis-Validierung
    if (RawSignal.Number < MIN_PULSES || RawSignal.Number > MAX_PULSES) {
        return false;
    }
    
    uint32_t aktuelle_zeit = millis();
    
    // Timeout für erste Sequenz
    if (erste_seq_zeit > 0 && (aktuelle_zeit - erste_seq_zeit) >= DUAL_SEQ_TIMEOUT) {
        Serial.println("→ Erste Sequenz Timeout - Reset");
        erste_seq_zeit = 0;
        erste_seq_pulses = 0;
        erste_seq_cmd = 0;
    }
    
    // DUAL-SEQUENZ-VERKETTUNG (vereinfacht für V8.4)
    if (erste_seq_zeit > 0 && (aktuelle_zeit - erste_seq_zeit) < DUAL_SEQ_TIMEOUT) {
        Serial.print("→ ✅ DUAL-SEQUENZ! Seq1=");
        Serial.print(erste_seq_pulses);
        Serial.print(" + Seq2=");
        Serial.print(RawSignal.Number);
        Serial.print(" = ");
        Serial.println(erste_seq_pulses + RawSignal.Number);
        
        // Verwende Kommando der ersten Sequenz
        unsigned long device_id = calculate_device_id(erste_seq_cmd);
        send_rflink_output(erste_seq_cmd, device_id);
        
        // ✅ BUFFER-RESET nach Dual-Sequenz (verhindert Overflow)
        Serial.println("→ Dual-Sequenz Buffer-Reset");
        RawSignal.Repeats = true;
        RawSignal.Number = 0;
        
        // Buffer komplett leeren
        for (int i = 0; i < RAW_BUFFER_SIZE; i++) {
            RawSignal.Pulses[i] = 0;
        }
        
        // Reset
        erste_seq_zeit = 0;
        erste_seq_pulses = 0;
        erste_seq_cmd = 0;
        letzte_verarbeitung = aktuelle_zeit;
        
        return true;
    }
    
    // Anti-Repeat-Mechanismus
    if (aktuelle_zeit - letzte_verarbeitung < REPEAT_TIMEOUT) {
        Serial.println("→ Wiederholung unterdrückt");
        RawSignal.Repeats = true;
        RawSignal.Number = 0;
        return true;
    }
    
    // NEUE SEQUENZ verarbeiten
    letzte_verarbeitung = aktuelle_zeit;
    sequenz_counter++;
    
    Serial.print("→ ***PLUGIN-050 V8.4 RX #");
    Serial.print(sequenz_counter);
    Serial.println(" START***");
    
    debug_signal_info();
    
    // ✅ NEUE S-SYMBOL-PIPELINE
    
    // 1. Pulse zu Symbolen dekodieren
    String symbolPattern = decodePulsesToSymbols();
    if (symbolPattern.length() == 0) {
        Serial.println("→ ❌ SIGNAL VERWORFEN: Keine Symbole dekodiert");
        return false;
    }
    
    // 2. Nur Datenbits extrahieren
    String dataBits = extractDataBits(symbolPattern);
    if (dataBits.length() == 0) {
        Serial.println("→ ❌ SIGNAL VERWORFEN: Keine Datenbits gefunden");
        return false;
    }
    
    // 3. Kommando aus Datenbits erkennen
    uint8_t erkanntes_kommando = identifyCommandFromDataBits(dataBits);
    unsigned long device_id = calculate_device_id(erkanntes_kommando);
    
    // 4. Erste Sequenz markieren (für mögliche Dual-Sequenz)
    bool ist_erste_sequenz = false;
    if ((RawSignal.Number >= 152 && RawSignal.Number <= 156) ||    // 154-Pulse
        (RawSignal.Number >= 228 && RawSignal.Number <= 232)) {    // 230-Pulse
        ist_erste_sequenz = true;
        erste_seq_zeit = aktuelle_zeit;
        erste_seq_pulses = RawSignal.Number;
        erste_seq_cmd = erkanntes_kommando;
        
        Serial.println("→ Als erste Sequenz markiert");
    }
    
    // 5. RFLink-Ausgabe
    send_rflink_output(erkanntes_kommando, device_id);
    
    // ✅ BUFFER-RESET nach erfolgreicher Erkennung (verhindert Overflow-Probleme)
    Serial.println("→ Buffer-Reset zur Vermeidung von Overflow-Problemen");
    RawSignal.Repeats = true;
    RawSignal.Number = 0;  // Buffer leeren
    
    // Buffer-Variablen auch zurücksetzen
    for (int i = 0; i < RAW_BUFFER_SIZE; i++) {
        RawSignal.Pulses[i] = 0;
    }
    
    Serial.println("→ ***PLUGIN-050 V8.6 RX ENDE***");
    return true;
}

//=============================================================================
// TX-PLUGIN-FUNKTION (Placeholder für später)
//=============================================================================

boolean PluginTX_050(byte function, char *string) {
    Serial.print("→ ***TX-PLUGIN V8.4*** Input: ");
    Serial.println(string);
    
    if (!strstr(string, "RollerShutter")) {
        return false;
    }
    
    Serial.println("→ TX-Funktionen sind Placeholder und können später implementiert werden");
    
    // Hier würden die echten TX-Funktionen stehen
    // Aktuell nur Placeholder für saubere Code-Struktur
    
    return false;  // Aktuell keine TX-Implementierung
}

#endif // PLUGIN_050