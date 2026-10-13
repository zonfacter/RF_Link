# Rohdaten und Telegrammaufbau

Stand: BUILD 0B / REV 33, 12.10.2026. Diese Beschreibung folgt den Decodern [ShutterRemote40.h](include/ShutterRemote40.h), [HTR008W.h](include/HTR008W.h) und den aufgezeichneten Hardwaretests. Bestätigte Beobachtungen und noch offene Protokollfelder sind getrennt beschrieben.

## 1. Was eine Pulsaufzeichnung enthält

Eine Pulsfolge enthält die Dauer aufeinanderfolgender HIGH- und LOW-Abschnitte des digitalen Empfängersignals. Bei diesen beiden Protokollen beginnt das ausgewertete Fenster mit HIGH; danach wechseln HIGH und LOW. Eine Zahl bezeichnet **eine Pegeldauer**, nicht automatisch ein Datenbit. Frequenz, Signalstärke und analoge Signalform stehen nicht in dieser Liste.

Beispiel, **gekürzt**; die vollständigen 82 Werte stehen in [capture_20261012_201504.jsonl](hardware-tests/capture_20261012_201504.jsonl):

```text
20;03;TIMING;Pulses=82;Pulses(uSec)=284,1464,628,304,264,668,...,628,4412;
```

| Feld | Bedeutung |
| --- | --- |
| `20` | RFLink-Ausgabe an den seriellen Host |
| `03` | Hexadezimaler serieller Paketzähler; keine Fernbedienungs-ID und kein Rolling-Code-Zähler |
| `TIMING` | Zusätzliche direkte Zeitmessung mittels `micros()` |
| `Pulses=82` | Anzahl der ausgegebenen Pegeldauern |
| `Pulses(uSec)` | Kommagetrennte Dauern in Mikrosekunden |

Im RFLink-Puffer sind die Dauern ab `RawSignal.Pulses[1]` gespeichert. Der Decoder erhält `Pulses + 1`; seine erste Position ist deshalb Index **0**. Die Tabellen unten verwenden diese Decoder-Indizes. In normalen RFLink-Samples gilt `Dauer = Sample × RawSignal.Multiply`, hier gewöhnlich `Multiply = 30`. Die `TIMING`-Zeile enthält dagegen direkt gemessene Mikrosekunden und wird nicht nochmals mit 30 multipliziert.

Der Anfang einer Aufnahme kann angeschnitten sein. Eine abschließende lange LOW-Dauer kann vom Aufnahme-Timeout begrenzt sein. Beide Werte dürfen deshalb nicht ungeprüft als vollständiger Sendestart oder originale Sendepause übernommen werden.

## 2. RFDEBUG und RFTIMING

```text
10;RFDEBUG=ON;
10;RFTIMING=ON;
```

`RFDEBUG` gibt die historischen RFLink-Samples als `DEBUG;Pulses=...;Pulses(uSec)=...` aus. Diese Samples entstehen durch Schleifenzählung und Skalierung. In diesem Quellstand überschätzen sie die tatsächlichen Pegeldauern. `RFTIMING` ergänzt eine direkte `micros()`-Messung vor der Protokolldecodierung. Für die Entwicklung eines Senders sind die direkten Messungen maßgeblich.

Eine Messung derselben Nobily-STOP-Übertragung ergab:

| Abschnitt | Direkte Messung | Historischer RFDEBUG-Wert |
| --- | ---: | ---: |
| Synchronisation | 1464 µs | 2310 µs |
| Weitere Synchronisation | 1456 µs | 2280 µs |

Die kurzen Datenabschnitte lagen direkt ungefähr bei **268–304 µs**, die langen bei **628–684 µs**. Der beobachtete Skalierungsfehler ist **keine universelle Umrechnungsformel** für andere Hardware, Compiler oder jedes Sample. Die Senderparameter wurden gesondert am Motor getestet. Siehe [Timingvergleich](hardware-tests/NOBILY_timing_comparison.json).

Nach der Aufnahme wieder ausschalten:

```text
10;RFDEBUG=OFF;
10;RFTIMING=OFF;
```

Mehrere Zeilen können zu demselben Funkereignis gehören: direkte Zeiten, historische Debugwerte und eine decodierte Protokollmeldung. Der serielle Paketzähler wird dabei für Ausgaben erhöht und ist kein gemeinsamer Funktelegramm-Schlüssel. Zum Zuordnen Zeit, Aufnahme-Label und Reihenfolge verwenden.

## 3. Nobily / Brel: ShutterRemote40

### Datenfelder

Das erkannte Datenwort hat **40 Bit**, MSB zuerst:

```text
[ Geräte-ID: 24 Bit ][ Kanalbyte: 8 Bit ][ Befehlsbyte: 8 Bit ]
```

Beispiel STOP auf Kanal 1:

```text
98 46 1A 41 55
└── ID ──┘ │  └─ Befehl
           └─ Kanal
```

| Feld | Beispiel | Interpretation |
| --- | --- | --- |
| Geräte-ID | `98461A` | Aus den ersten 24 Datenbits gelesen |
| Kanalbyte | `41` | Einzelkanal 1 |
| Befehlsbyte | `55` | STOP |

| Kanalbyte, hex | Bestätigte Auswahl |
| --- | --- |
| `40` | Alle Kanäle, separate Auswahl an der Fernbedienung |
| `41`–`45` | Einzelkanäle 1–5; Kanal 5 ist kein Gruppenkanal |

| Rohbefehl, hex | Bedeutung |
| --- | --- |
| `11` | UP / HOCH |
| `33` | DOWN / RUNTER |
| `55` | STOP |
| `1E`, `3C` | In älteren Aufzeichnungen beobachtete weitere Befehle; genaue Funktion nicht bestätigt |

Andere Befehlsbytes bleiben als `RAW` erhalten und ergeben `CMD=UNKNOWN`. Es wird keine unbestätigte Prüfsumme angenommen. Die vollständigen acht Kanalbits bleiben erhalten; der Decoder reduziert sie nicht auf das untere Nibble.

### Pulsstruktur

Ein ausgewerteter Rahmen hat **82 Pegeldauern**:

| Decoder-Index | Abschnitt |
| --- | --- |
| `0` | Start-HIGH; im Empfangsmitschnitt häufig angeschnitten |
| `1` | Synchronisations-LOW |
| `2`–`81` | 40 HIGH/LOW-Paare; beim letzten Bit ist LOW die Rahmenpause |

Für die Datenbits gilt:

| Bit | HIGH | LOW |
| --- | ---: | ---: |
| `0` | kurz, etwa 300 µs | lang, etwa 660 µs |
| `1` | lang, etwa 660 µs | kurz, etwa 300 µs |

Beim **letzten Bit** entscheidet nur die HIGH-Dauer über den Bitwert. Das folgende LOW ist die Pause und kein normaler kurzer/langer zweiter Bitabschnitt. Der Decoder berücksichtigt diese Ausnahme ausdrücklich.

Der Sender verwendet ein am Motor getestetes Start-HIGH von **4800 µs**, Synchronisations-LOW **1470 µs**, Datenabschnitte **300/660 µs** und Schluss-LOW **6990 µs**. Er wiederholt den 82er-Rahmen sechsmal. Ein kurzer Startwert im Mitschnitt und etwa 4,4 ms am Aufnahmeende widerlegen diese TX-Werte nicht: Aufnahmebeginn und Timeout können das Fenster begrenzen.

Zur Wiederauswertung alter Aufzeichnungen akzeptiert der Decoder zusätzlich ein historisches Profil: Synchronisation **2200–2600 µs**, kurze Abschnitte **300–650 µs**, lange **800–1300 µs**. Das direkte Profil akzeptiert Synchronisation **1200–1800 µs**, kurz **180–420 µs**, lang **500–850 µs**. Das sind Erkennungstoleranzen, keine alternativen Sendesollwerte.

### Serielle Ausgabe und Senden

```text
20;01;ShutterRemote40;ID=98461A;SWITCH=41;CHANNELBYTE=41;RAW=55;CMD=STOP;
10;ShutterRemote40;98461A;41;STOP;
```

`SWITCH` ist das vollständige Kanalbyte für die externe Zuordnung und den passenden Sendebefehl. `CHANNELBYTE` wiederholt es zur Analyse. `RAW` zeigt das ursprüngliche Befehlsbyte, `CMD` dessen bekannte Bedeutung. Der Wert `01` nach `20` ist wieder nur der serielle Paketzähler.

Einige historische CSV-Dateinamen passen nicht zum tatsächlich enthaltenen Kanal/Befehl. Für die Interpretation das decodierte Datenwort und die später ausdrücklich beschrifteten Hardwaretests verwenden, nicht allein den Dateinamen. Die [Kanalvalidierung](hardware-tests/NOBILY_channel_validation.json) unterscheidet bestätigte und noch nicht einzeln bestätigte Motorreaktionen.

## 4. HTR008W: bestätigtes Pulsprofil

### Bestätigt und noch offen

Der aktuelle HTR-Decoder erkennt die aufgezeichnete Fernbedienung anhand von Pulsbreitenmustern. Die Zeichen `0` und `1` in den Profilkonstanten bedeuten **kurze bzw. lange Pegeldauer**. Sie sind keine Behauptung über das logische Bitformat des Herstellers.

Eine allgemeine Hersteller-/Geräte-ID, die Kanalcodierung, Prüfsummen und eine mögliche Rolling-Code-Struktur sind nicht nachgewiesen. Deshalb gibt Plugin 085 derzeit **`ID=000001;SWITCH=00` als lokalen Profilalias** aus. Diese Felder werden nicht als echte ID und echter Kanal aus dem Funktelegramm herausgelesen. Weitere HTR-Fernbedienungen können damit bisher nicht zuverlässig unterschieden werden.

### Aufbau eines Teilrahmens

Ein vollständiger Teilrahmen hat **76 Pegeldauern**:

| Decoder-Index | Abschnitt | TX-Sollwert |
| --- | --- | ---: |
| `0`–`3` | Vier wechselnde Header-Dauern | jeweils 1890 µs |
| `4` | Synchronisation | 3870 µs |
| `5`–`74` | 70 aufeinanderfolgende Pulsbreitensymbole | kurz 390 µs / lang 900 µs |
| `75` | LOW-Pause | 2370 µs innerhalb des gesendeten Hauptpakets |

Der Decoder wertet den ersten vollständigen Teilrahmen aus. Drei stabile Musterprofile sind im Quellcode hinterlegt (`UP_PATTERN`, `STOP_PATTERN`, `THIRD_PROFILE`). Die ersten drei Symbole dürfen variieren. Vom Symbolindex **3 bis 69** müssen alle Positionen außer **59 und 60** zum Profil passen.

Die beiden Befehlspositionen sind **Index 59 und 60 innerhalb der 70 Symbole**, nullbasiert. Sie entsprechen **Pulsindex 64 und 65** des Teilrahmens:

| Symbol 59 / Symbol 60 | Aktuelle Zuordnung |
| --- | --- |
| `0 / 1` | UP |
| `1 / 0` | STOP |
| `1 / 1` | DOWN |
| `0 / 0` | Nicht als gültiger Befehl akzeptiert |

Diese Zuordnung ist für die aufgezeichneten Profile und Motorversuche bestätigt, nicht als allgemeine vollständige Hersteller-Protokollspezifikation.

### Gesendetes Hauptpaket

| Befehl | Teilrahmen | Zusätzlicher Abschluss | Gesamtdauern |
| --- | ---: | --- | ---: |
| UP | 2 × 76 | Letzte LOW-Pause auf 7500 µs verlängert | 152 |
| DOWN | 2 × 76 | HIGH 1890 µs, LOW 7500 µs | 154 |
| STOP | 3 × 76 | HIGH 1890 µs, LOW 7500 µs | 230 |

Die Sendemuster stehen als feste, zuvor beobachtete Profile im Firmware-Quellcode. Es handelt sich nicht um EEPROM-Anlernen. Das Senden dieser Pakete wurde für die vorhandene Fernbedienung am Motor bestätigt; siehe [HTR008W_TX_result.json](hardware-tests/HTR008W_TX_result.json).

```text
20;01;HTR008W;ID=000001;SWITCH=00;CMD=STOP;
10;HTR008W;000001;00;STOP;
```

Die [beschriftete Aufnahme](hardware-tests/capture_20261012_201834.jsonl) enthält UP, STOP und DOWN. Der HTR-Capturetest prüft die passenden Rahmen aus direkten und historischen Zeitprofilen.

## 5. Aufzeichnungsdateien lesen

### Ergänzung BUILD 0B: BL999 / TFA-TwinPlus-Sensorfamilie

Die aufgezeichneten vollständigen 74-Puls-Rahmen ergeben beide das 36-Bit-Wort `140BB0DD5`. Der neue [BL999-Decoder](include/BL999.h) prüft die Pulsbreiten, die feste Kennung und eine Vier-Bit-Nibbelsumme. [Plugin 086](legacy/Plugins/Plugin_086.c) fordert zusätzlich zwei gleiche gültige Rahmen innerhalb von zwei Sekunden und unterdrückt unmittelbare Wiederholungen.

Die Datenstruktur dieser Sensorfamilie und die LSB-Bitreihenfolge sind im [rtl_433-Decoder für TFA TwinPlus / BL999](https://github.com/merbanan/rtl_433/blob/master/src/devices/tfa_twin_plus_30.3049.c) beschrieben. Unsere Implementierung verwendet die direkt gemessenen Zeiten: HIGH etwa 380 µs, LOW etwa 1890 bzw. 3960 µs. Die historischen DEBUG-Zeiten sind dafür zu groß; Plugin 086 nutzt `RealPulseWidths` auch bei ausgeschaltetem RFTIMING.

Das empfangene Wort liefert Sensor-ID `08`, Rohkanal `1`, Temperatur `22,1 °C`, Feuchte `31 %` und Batterie OK. Dies beschreibt die Sensorfamilie, bestätigt aber keinen bestimmten Herstelleraufdruck des entfernten Geräts. Die vollständigen Pulsaufzeichnungen liegen als [Testfixture](tests/bl999_measured_pulses.json) vor.

```text
20;01;BL999;ID=0108;CHAN=1;TEMP=00DD;HUM=31;BAT=OK;
```

Für gewöhnliche RFLink-Clients kombiniert `ID` den Rohkanal im oberen Byte mit der sechs Bit großen Sensor-ID im unteren Byte: `(Kanal << 8) | Sensor-ID`. `CHAN` erhält den Rohkanal separat. Die Sensor-ID kann sich nach einem Batteriewechsel ändern. Teilrahmen mit 20, 22, 30, 32 oder 34 Pegeldauern werden nicht als vollständige Geräte-Meldung angenommen.

Die lokale Geräteübersicht nimmt nur decodierte Meldungen mit ID auf. `DEBUG` und `TIMING` allein enthalten keine solche Zuordnung und werden im Reiter Rohsignale gesammelt. Ein Empfangszähler in der Geräteansicht macht diesen Unterschied sichtbar.

Die JSONL-Dateien enthalten pro Zeile ein JSON-Objekt:

```json
{"time":"2026-10-12T20:15:40.149980+02:00","label":"NOBILY_CH1_STOP_TIMING_PAIRED","direction":"rx","raw":"20;03;TIMING;Pulses=82;Pulses(uSec)=...;"}
```

Das Beispiel ist gekürzt. `time` ist die Host-Zeit mit Zeitzone; `label` ist die beim Versuch vergebene Beschriftung; `direction` unterscheidet `rx` und `tx`; `raw` enthält die serielle Zeile. Labels sind Versuchskontext und nicht durch den Decoder bestätigte Funkfelder. Zwischen gültigen Rahmen können Fremdsignale oder unvollständige Aufnahmen vorkommen.

| Datei | Inhalt |
| --- | --- |
| [capture_20261012_201504.jsonl](hardware-tests/capture_20261012_201504.jsonl) | Gepaarte direkte/historische Nobily-STOP-Zeiten |
| [capture_20261012_201834.jsonl](hardware-tests/capture_20261012_201834.jsonl) | Beschriftete HTR-Tasten und weitere Sendetests |
| [capture_20261012_203317.jsonl](hardware-tests/capture_20261012_203317.jsonl) | Spätere HTR- und Nobily-Kanalversuche |

Für neue Protokollanalysen mehrere kurze Tastendrücke je Taste und Kanal getrennt beschriften, direkte Zeiten aufnehmen und wiederholte Rahmen vergleichen. Unbekannte Abschnitte zunächst offen lassen. Fremdsignale, abgeschnittene Header und Aufnahme-Timeouts nicht als gesicherte Protokollfelder behandeln.

## Nobily-Ergaenzung BUILD 0C/0D

Der Empfaenger kann den Startpuls verkuerzen oder das Start-/Sync-Paar ganz verlieren. BUILD 0C akzeptiert bei vollstaendigen 82-Puls-Telegrammen einen Startpuls ab 150 us. BUILD 0D prueft zusaetzlich 80-Puls-Telegramme mit allen 40 Datenpaaren und Schlussluecke. Ohne Sync werden nur Kanalbytes 40..45 und die beobachteten Rohkommandos 11/33/55/1E/3C akzeptiert; zwei gleiche Rahmen innerhalb von 2000 ms sind erforderlich. Andere unvollstaendige Rahmen bleiben ungueltig.

Am 13.10.2026 wurden Kanal 42 UP, STOP und DOWN live bestaetigt. Im selben Test folgt RAW 1E auf UP und RAW 3C auf DOWN. Dies beweist noch keine allgemeine Bedeutung der Folgetelegramme; CMD bleibt UNKNOWN. Die lokale Geraeteverwaltung speichert `last_known_command` und dessen Zeitstempel separat vom letzten Rohtelegramm.
