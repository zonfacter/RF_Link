# Rollladen-Fernbedienung Protokoll-Dokumentation

## Analyse-Ergebnis

**Fernbedienung:** Unbekannter Hersteller (vermutlich 433MHz)  
**Protokoll:** 40-Bit PWM  
**Erkannte Remote-ID:** `0x98461A`

## Protokoll-Struktur

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        SIGNAL-AUFBAU                                    │
├─────────────────────────────────────────────────────────────────────────┤
│ Preamble │ Sync     │ 40 Datenbits (80 Pulse)           │ End-Pause    │
│ ~700µs   │ ~2400µs  │ Kurz-Lang=0, Lang-Kurz=1          │ ~7000µs      │
└─────────────────────────────────────────────────────────────────────────┘

Timing:
- Kurzer Puls: 420-510 µs (Ø 458 µs)
- Langer Puls: 1050-1110 µs (Ø 1059 µs)
- Sync-Puls: 2370-2400 µs
- End-Pause: ~7000 µs
```

## Datenstruktur (40 Bits)

```
┌────────────────────────┬──────────┬──────────┬──────────┐
│ Remote ID              │ Channel  │ Command  │ Checksum │
│ 24 Bits (0-23)         │ 4 Bits   │ 4 Bits   │ 8 Bits   │
│                        │ (24-27)  │ (28-31)  │ (32-39)  │
└────────────────────────┴──────────┴──────────┴──────────┘
```

## Dekodierte Werte (Kanal 3 RUNTER)

| Feld | Bits | Wert | Bedeutung |
|------|------|------|-----------|
| Remote ID | 0-23 | `100110000100011000011010` | `0x98461A` |
| Channel | 24-27 | `0100` | 4 (intern) → **CH3** (Label) |
| Command | 28-31 | `0011` | `0x3` = **DOWN** |
| Checksum | 32-39 | `00110010` | `0x32` |

**Kompletter Bitstream:**
```
1001 1000 0100 0110 0001 1010 0100 0011 0011 0010
 9    8    4    6    1    A    4    3    3    2
```

## Kanal-Mapping

Die Fernbedienung verwendet ein internes Mapping:

| FB-Label | Intern (vermutlich) |
|----------|---------------------|
| CH1 | 2 |
| CH2 | 3 |
| CH3 | 4 ✓ (bestätigt) |
| CH4 | 5 |
| CH-ALL | 0 oder 1 ? |

## Befehls-Codes (zu verifizieren)

| Code | Vermuteter Befehl |
|------|-------------------|
| `0x1` | STOP |
| `0x2` | UP |
| `0x3` | **DOWN** ✓ (bestätigt) |
| `0x8` | PROG |

## Sende-Sequenzen

### Kanal 3 - UP
```
Bits:   1001100001000110000110100100001000110010
Hex:    98461A 4 2 32
Pulse:  700,2400, 1050,450,450,1050,450,1050,1050,450,...,7000
```

### Kanal 3 - DOWN (bestätigt)
```
Bits:   1001100001000110000110100100001100110010
Hex:    98461A 4 3 32
Pulse:  700,2400, 1050,450,450,1050,450,1050,1050,450,...,7000
```

### Kanal 3 - STOP
```
Bits:   1001100001000110000110100100000100110010
Hex:    98461A 4 1 32
Pulse:  700,2400, 1050,450,450,1050,450,1050,450,1050,...,7000
```

## Nächste Schritte

Um das Protokoll vollständig zu verifizieren:

1. **Andere Befehle auf Kanal 3 testen:**
   - Taste HOCH (UP) drücken
   - Taste STOP drücken
   - RFDEBUG Ausgaben sammeln

2. **Andere Kanäle testen:**
   - Kanal 1, 2, 4 etc.
   - Jeweils RUNTER drücken
   - Kanal-Mapping verifizieren

3. **Checksum verifizieren:**
   - Verschiedene Kombinationen testen
   - Prüfen ob Checksum berechnet wird oder konstant ist

## Plugin-Verwendung

```python
from plugin_shutter_remote_v1 import ShutterRemotePlugin

# Plugin initialisieren
plugin = ShutterRemotePlugin()

# RFDEBUG-Zeile verarbeiten
result = plugin.process_message(debug_line)
if result:
    print(f"Kanal {result['channel']}: {result['command']}")

# Befehl lernen
plugin.learn_current("DOWN")

# Kanal-Mapping lernen
plugin.learn_channel_mapping(3)  # Aktueller Befehl ist für CH3

# Sende-Befehl generieren
send = plugin.create_send_command(0x98461A, 3, "UP")
print(f"Pulse: {send['pulses']}")
```

## Hinweis zum Senden

Standard RFLink-Firmware unterstützt **kein direktes Pulse-Senden**.

Für das Senden von Befehlen gibt es folgende Optionen:

1. **RFLink-Alternative:** Prüfen ob dein Protokoll bereits in RFLink integriert ist
2. **Custom Firmware:** RFLink-Fork mit Raw-Send Funktion
3. **Eigene Hardware:** Arduino/ESP mit 433MHz Sender
4. **RF-Bridge:** Sonoff RF-Bridge mit Tasmota Firmware

## Dateien

- `plugin_shutter_remote_v1.py` - Vollständiges Plugin mit Lern-Funktion
- `analyze_detailed.py` - Analyse-Skript
- `~/.shutter_remote_config.json` - Gespeicherte Lern-Daten
