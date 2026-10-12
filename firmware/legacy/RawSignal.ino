/*********************************************************************************************/
// ENGLISH: This routine is part of the main loop and is executed every 125µs
// DEUTSCH: Diese Routine ist Teil der Hauptschleife und wird alle 125µs durchlaufen
boolean ScanEvent(void) {
  unsigned long Timer = millis() + SCAN_HIGH_TIME;

  while(Timer > millis() || RepeatingTimer > millis()) {
       // ENGLISH: RF data start - check for incoming RF signal
       // DEUTSCH: RF-Daten Start - prüfe auf eingehendes RF-Signal
       if (FetchSignal(PIN_RF_RX_DATA, HIGH)) {
          // ENGLISH: Check all plugins to see which plugin can handle the received signal
          // DEUTSCH: Prüfe alle Plugins, um zu sehen welches Plugin das empfangene Signal verarbeiten kann
          if (PluginRXCall(0, 0)) {
             RepeatingTimer = millis() + SIGNAL_REPEAT_TIME;
             return true;
          }
       }
  } // while
  return false;
}

/**********************************************************************************************\
 * ENGLISH: Fetch the pulses and place in buffer
 * DEUTSCH: Hole die Pulse und platziere sie im Puffer
 * 
 * ENGLISH: For TSOP1738: output is HIGH when idle, StateSignal must be LOW
 * DEUTSCH: Für TSOP1738: Ausgang ist HIGH in Ruhe, StateSignal muss LOW sein
 * 
 * ENGLISH: For 433RX: output is LOW when idle, StateSignal must be HIGH  
 * DEUTSCH: Für 433RX: Ausgang ist LOW in Ruhe, StateSignal muss HIGH sein
\*********************************************************************************************/

// ENGLISH: Timing constants for pulse measurement
// DEUTSCH: Timing-Konstanten für Pulse-Messung
const unsigned long LoopsPerMilli = 345;  // ENGLISH: Calibrated loops per millisecond / DEUTSCH: Kalibrierte Schleifen pro Millisekunde
const unsigned long Overhead = 0;         // ENGLISH: Processing overhead compensation / DEUTSCH: Verarbeitungszeit-Kompensation

// ENGLISH: Global variables for time-critical routine (avoid initialization overhead)
// DEUTSCH: Globale Variablen für zeitkritische Routine (Initialisierungsaufwand vermeiden)
int RawCodeLength = 0;
unsigned long PulseLength = 0L;
unsigned long numloops = 0L;
unsigned long maxloops = 0L;

// ENGLISH: State variables for signal processing
// DEUTSCH: Zustandsvariablen für Signalverarbeitung
boolean Ftoggle = false;
uint8_t Fbit_global = 0;      // ENGLISH: Renamed to avoid confusion with local variable / DEUTSCH: Umbenannt um Verwirrung mit lokaler Variable zu vermeiden
uint8_t Fport_global = 0;     // ENGLISH: Renamed to avoid confusion with local variable / DEUTSCH: Umbenannt um Verwirrung mit lokaler Variable zu vermeiden
uint8_t FstateMask_global = 0; // ENGLISH: Renamed to avoid confusion with local variable / DEUTSCH: Umbenannt um Verwirrung mit lokaler Variable zu vermeiden

/*********************************************************************************************/
boolean FetchSignal(byte DataPin, boolean StateSignal) {
   // ENGLISH: Calculate bit mask and port for fast digital pin access
   // DEUTSCH: Berechne Bit-Maske und Port für schnellen Digitalpinzugriff
   uint8_t Fbit = digitalPinToBitMask(DataPin);
   uint8_t Fport = digitalPinToPort(DataPin);
   uint8_t FstateMask = (StateSignal ? Fbit : 0);

   // ENGLISH: Check if signal is present on the pin
   // DEUTSCH: Prüfe ob Signal am Pin anliegt
   if ((*portInputRegister(Fport) & Fbit) == FstateMask) {
     
     // ENGLISH: Handle repeating signals - wait for signal gap to avoid capturing mid-transmission
     // DEUTSCH: Behandle sich wiederholende Signale - warte auf Signalpause um Aufnahme mitten in Übertragung zu vermeiden
     if (RawSignal.Time) { // ENGLISH: Quick check first (time critical section) / DEUTSCH: Schnellprüfung zuerst (zeitkritischer Bereich)
        if (RawSignal.Repeats && (RawSignal.Time + SIGNAL_REPEAT_TIME) > millis()) {
           // ENGLISH: Set timeout for signal gap detection
           // DEUTSCH: Setze Timeout für Signalpause-Erkennung
           PulseLength = micros() + SIGNAL_TIMEOUT * 1000;
           
           // ENGLISH: Wait while signal is still repeating
           // DEUTSCH: Warte während Signal noch wiederholt wird
           while ((RawSignal.Time + SIGNAL_REPEAT_TIME) > millis() && PulseLength > micros()) {
              if ((*portInputRegister(Fport) & Fbit) == FstateMask) {
                 PulseLength = micros() + SIGNAL_TIMEOUT * 1000; // ENGLISH: Reset timeout / DEUTSCH: Timeout zurücksetzen
              }
           }
           
           // ENGLISH: Wait for signal to go idle
           // DEUTSCH: Warte bis Signal in Ruhezustand geht
           while((RawSignal.Time + SIGNAL_REPEAT_TIME) > millis() && 
                 (*portInputRegister(Fport) & Fbit) != FstateMask);
        }
     }
     
     // ENGLISH: Initialize pulse capture
     // DEUTSCH: Initialisiere Pulse-Aufnahme
     RawCodeLength = 1; // ENGLISH: Start at 1 for legacy reasons. Element 0 can be used for special info / DEUTSCH: Beginne bei 1 aus Legacy-Gründen. Element 0 kann für spezielle Info genutzt werden
     Ftoggle = false;
     maxloops = (SIGNAL_TIMEOUT * LoopsPerMilli);
     
     // ENGLISH: Main pulse capture loop
     // DEUTSCH: Haupt-Pulse-Aufnahme-Schleife
     do {
       numloops = 0;
       unsigned long measuredStart = micros();
       
       // ENGLISH: Measure pulse duration by counting loops
       // DEUTSCH: Messe Pulsdauer durch Zählen von Schleifen
       while (((*portInputRegister(Fport) & Fbit) == FstateMask) ^ Ftoggle) {
          if (numloops++ == maxloops) break; // ENGLISH: Timeout protection / DEUTSCH: Timeout-Schutz
       }
       
       RealPulseWidths[RawCodeLength] = uint16_t(micros() - measuredStart);

       // ENGLISH: Convert loop count to microseconds
       // DEUTSCH: Konvertiere Schleifenanzahl zu Mikrosekunden
       PulseLength = ((numloops + Overhead) * 1000) / LoopsPerMilli;
       
       // ENGLISH: Filter out pulses that are too short (noise)
       // DEUTSCH: Filtere Pulse die zu kurz sind (Rauschen)
       if (PulseLength < MIN_PULSE_LENGTH) break;
       
       Ftoggle = !Ftoggle; // ENGLISH: Toggle state for next pulse / DEUTSCH: Schalte Zustand für nächsten Puls um
       
       // ENGLISH: Store pulse in buffer with sample rate scaling
       // DEUTSCH: Speichere Puls im Puffer mit Sample-Rate-Skalierung
       RawSignal.Pulses[RawCodeLength++] = PulseLength / (unsigned long)(RAWSIGNAL_SAMPLE_RATE);
       
    } while (RawCodeLength < RAW_BUFFER_SIZE && numloops <= maxloops);
    
    // ENGLISH: Check if we captured enough pulses for a valid signal
    // DEUTSCH: Prüfe ob wir genug Pulse für ein gültiges Signal aufgenommen haben
    if (RawCodeLength >= MIN_RAW_PULSES) {
       RawSignal.Repeats = 0;                          // ENGLISH: No repeats initially / DEUTSCH: Zunächst keine Wiederholungen
       RawSignal.Multiply = RAWSIGNAL_SAMPLE_RATE;     // ENGLISH: Sample size / DEUTSCH: Sample-Größe
       RawSignal.Number = RawCodeLength - 1;           // ENGLISH: Number of pulse times / DEUTSCH: Anzahl der Pulszeiten
       RawSignal.Pulses[RawSignal.Number + 1] = 0;     // ENGLISH: Last element contains timeout / DEUTSCH: Letztes Element enthält Timeout
       RawSignal.Time = millis();                      // ENGLISH: Timestamp for retransmit detection / DEUTSCH: Zeitstempel für Wiederholungserkennung
       if (RFTiming) {
          snprintf_P(pbuffer, sizeof(pbuffer), PSTR("20;%02X;TIMING;Pulses=%d;Pulses(uSec)="),
                     PKSequenceNumber++, RawSignal.Number);
          Serial.print(pbuffer);
          for (int i = 1; i <= RawSignal.Number; ++i) {
             Serial.print(RealPulseWidths[i]);
             if (i < RawSignal.Number) Serial.print(',');
          }
          Serial.println(';');
       }
       return true;
    } else {
      RawSignal.Number = 0; // ENGLISH: Invalid signal, reset / DEUTSCH: Ungültiges Signal, zurücksetzen
    }
  }
  return false;
}

/*********************************************************************************************/
// ENGLISH: RFLink Board specific: Generate short pulse to switch Aurel Transceiver from TX to RX mode
// DEUTSCH: RFLink Board spezifisch: Generiere kurzen Puls um Aurel Transceiver von TX zu RX Modus zu schalten
void RFLinkHW(void) {
     delayMicroseconds(36);        // ENGLISH: Timing critical delay / DEUTSCH: Timing-kritische Verzögerung
     digitalWrite(PIN_BSF_0, LOW);
     delayMicroseconds(16);        // ENGLISH: Minimum switching time / DEUTSCH: Minimale Schaltzeit
     digitalWrite(PIN_BSF_0, HIGH);
     return;
}

/*********************************************************************************************\
 * ENGLISH: Send raw signal buffer to RF transmitter
 * DEUTSCH: Sende Rohsignal-Puffer an RF-Sender
 * 
 * WARNING: This function is marked as DEPRECATED - DO NOT USE for new implementations
 * WARNUNG: Diese Funktion ist als DEPRECATED markiert - NICHT für neue Implementierungen verwenden
 * 
 * ENGLISH: Use newer transmission functions instead
 * DEUTSCH: Verwende stattdessen neuere Übertragungsfunktionen
\*********************************************************************************************/
void RawSendRF(void) {
  int x;
  
  // ENGLISH: Power management: Turn off receiver to prevent interference, turn on transmitter
  // DEUTSCH: Power-Management: Schalte Empfänger aus um Interferenz zu vermeiden, schalte Sender ein
  digitalWrite(PIN_RF_RX_VCC, LOW);   // ENGLISH: Turn off RF receiver / DEUTSCH: RF-Empfänger ausschalten
  digitalWrite(PIN_RF_TX_VCC, HIGH);  // ENGLISH: Turn on 433MHz transmitter / DEUTSCH: 433MHz-Sender einschalten
  
  // ENGLISH: Wait for transmitter to stabilize (Aurel RTX MID needs 500µs)
  // DEUTSCH: Warte bis Sender stabil ist (Aurel RTX MID benötigt 500µs)
  delayMicroseconds(TRANSMITTER_STABLE_DELAY);

  // ENGLISH: BUG FIX: Arduino 1.0.1 array access bug workaround
  // DEUTSCH: BUGFIX: Workaround für Arduino 1.0.1 Array-Zugriffs-Bug
  RawSignal.Pulses[RawSignal.Number] = 1;

  // ENGLISH: Repeat transmission loop
  // DEUTSCH: Wiederholungs-Übertragungsschleife
  for(byte y = 0; y < RawSignal.Repeats; y++) {
     x = 1;
     noInterrupts(); // ENGLISH: Disable interrupts for timing accuracy / DEUTSCH: Deaktiviere Interrupts für Timing-Genauigkeit
     
     // ENGLISH: Transmit pulse pairs (HIGH/LOW)
     // DEUTSCH: Übertrage Puls-Paare (HIGH/LOW)
     while(x < RawSignal.Number) {
        digitalWrite(PIN_RF_TX_DATA, HIGH);
        // ENGLISH: Small timing correction (-5µs) for digitalWrite overhead
        // DEUTSCH: Kleine Timing-Korrektur (-5µs) für digitalWrite-Overhead
        delayMicroseconds(RawSignal.Pulses[x++] * RawSignal.Multiply - 5);
        
        digitalWrite(PIN_RF_TX_DATA, LOW);
        // ENGLISH: Small timing correction (-7µs) for digitalWrite overhead
        // DEUTSCH: Kleine Timing-Korrektur (-7µs) für digitalWrite-Overhead
        delayMicroseconds(RawSignal.Pulses[x++] * RawSignal.Multiply - 7);
     }
     interrupts(); // ENGLISH: Re-enable interrupts / DEUTSCH: Aktiviere Interrupts wieder
     
     // ENGLISH: Delay between repeats (must be outside interrupt-disabled section)
     // DEUTSCH: Verzögerung zwischen Wiederholungen (muss außerhalb des Interrupt-deaktivierten Bereichs sein)
     if (y + 1 < RawSignal.Repeats) {
        delay(RawSignal.Delay);
     }
  }

  // ENGLISH: Restore normal operation: stabilize, turn off transmitter, turn on receiver
  // DEUTSCH: Stelle normalen Betrieb wieder her: stabilisieren, Sender ausschalten, Empfänger einschalten
  delayMicroseconds(TRANSMITTER_STABLE_DELAY);
  digitalWrite(PIN_RF_TX_VCC, LOW);   // ENGLISH: Turn off transmitter / DEUTSCH: Sender ausschalten
  digitalWrite(PIN_RF_RX_VCC, HIGH);  // ENGLISH: Turn on receiver / DEUTSCH: Empfänger einschalten
  RFLinkHW(); // ENGLISH: Switch transceiver back to RX mode / DEUTSCH: Schalte Transceiver zurück in RX-Modus
}

/*********************************************************************************************/

/*********************************************************************************************\
 * ENGLISH: Code Review Summary - Identified Issues and Improvements:
 * DEUTSCH: Code-Review Zusammenfassung - Identifizierte Probleme und Verbesserungen:
 * 
 * 1. FIXED: Variable name conflicts (Fbit, Fport, FstateMask) - renamed globals
 *    BEHOBEN: Variablennamenskonflikte - globale Variablen umbenannt
 * 
 * 2. IMPROVED: Added comprehensive bilingual comments (EN/DE)
 *    VERBESSERT: Umfassende zweisprachige Kommentare hinzugefügt
 * 
 * 3. WARNING: RawSendRF() is deprecated - should use newer transmission methods
 *    WARNUNG: RawSendRF() ist veraltet - sollte neuere Übertragungsmethoden verwenden
 * 
 * 4. DOCUMENTED: Magic numbers and timing values explained
 *    DOKUMENTIERT: Magic Numbers und Timing-Werte erklärt
 * 
 * 5. CLARIFIED: Complex logic in FetchSignal() with step-by-step comments
 *    VERDEUTLICHT: Komplexe Logik in FetchSignal() mit Schritt-für-Schritt Kommentaren
\*********************************************************************************************/
