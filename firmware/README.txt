RFLink fuer Arduino Mega 2560 / 433 MHz

PlatformIO-Projekt: dieser Ordner; Environment mega2560.
In VS Code den uebergeordneten RFLink.code-workspace oeffnen.
Seriell: 57600 Baud, LF. Quellstand BUILD 0A, REV 33.
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
BUILD 0A ist auf beiden Megas installiert (COM4 und nach Geraetetausch COM3).
Beide Flash-Uploads verifiziert, VERSION/PING OK. Aktueller Laptop-Port: COM3.
Ausfuehrliche Bedienung und Einschraenkungen: ../RFLink_Bedienung.txt.
