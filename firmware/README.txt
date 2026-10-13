RFLink fuer Arduino Mega 2560 / 433 MHz

PlatformIO-Projekt: dieser Ordner; Environment mega2560.
In VS Code den uebergeordneten RFLink.code-workspace oeffnen.
Seriell: 57600 Baud, LF. Quellstand BUILD 0D, REV 33.
Build: platformio run -d firmware (vom uebergeordneten Ordner).

Quelle: Arbeitskopie von C:/Entwicklung/RFLink mit lokalen Aenderungen.
Urspruengliches Remote https://github.com/jwdb/rflink.git.
Originalquellen und Lizenzheader bleiben in legacy erhalten.
src/main.cpp bindet die bisherigen Arduino-Tabs ein.
scripts/legacy_dependencies.py sorgt fuer Neubauten bei Aenderungen der Includes.

Plugin 084: ShutterRemote40, 24-Bit-ID, Kanalbyte, Rohbefehl.
RX gibt vollstaendiges Kanalbyte als SWITCH aus; TX akzeptiert dieselben Werte.
Motor-getestete Nobily-ID 98461A; Kanaele 41-45, alle Kanaele 40.
Plugin 085: HTR008W, das konkret getestete Fernbedienungsprofil.
ID 000001 ist bisher ein lokaler Alias; keine universelle HTR-Geraeteerkennung.
Experimentelle Plugins 050 und 083 bleiben deaktiviert.
Die aktuelle Firmware enthaelt keine zusaetzliche EEPROM-Lernfunktion.
Geraetezuordnungen erfolgen extern im Laptop-Testprogramm oder ioBroker.

RFDEBUG enthaelt historische, durch Loop-Zaehlung skalierte Pulszeiten.
RFTIMING=ON ergaenzt tatsaechlich gemessene Mikrosekunden fuer weitere Analysen.
Sendepulszeiten wurden anhand echter Messungen korrigiert und am Motor getestet.

Tests: tests/run_capture_tests.py, tests/run_htr_capture_tests.py,
tests/test_iobroker.js, tests/test_iobroker_bridge.js, tests/test_testprogramm.py.
Hardware-Mitschnitte und dokumentierte Motorreaktionen: hardware-tests.
Verworfener Lernversuch: experiments/retired-eeprom-learning, nicht eingebunden.
BUILD 0B ist auf dem Laptop-Mega COM3 installiert: Flash verifiziert, VERSION/PING OK.
Der Mega am ioBroker-Rechner wurde zuvor auf BUILD 0A aktualisiert.
Ausfuehrliche Bedienung und Einschraenkungen: ../RFLink_Bedienung.txt.

Plugin 086: BL999/TFA-TwinPlus-Empfang mit physikalischen Pulszeiten,
Nibbelsumme und zwei gleichen gueltigen Rahmen vor der Ausgabe.
Sensor-Test: tests/run_bl999_capture_tests.py.

BUILD 0D: Nobily mit verkurztem Startpuls bzw. fehlendem Start-/Sync-Paar.
80-Puls-Daten benoetigen zwei identische Telegramme innerhalb von 2000 ms.
Kanal 42 live mit UP/STOP/DOWN bestaetigt; RAW 1E/3C bleiben UNKNOWN.
Siehe tests/nobily_missing_sync.md und run_clipped_nobily_tests.py.
Laptop-Mega: BUILD 0D installiert und verifiziert; ioBroker-Mega unveraendert.
