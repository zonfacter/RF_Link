# RFLink: Mega-Firmware und Windows-Testprogramm

Firmware BUILD **0A / REV 33** für Arduino Mega 2560 und 433 MHz. Das Projekt ergänzt den vorhandenen RFLink-Quellstand um das getestete Nobily/Brel-Protokoll und ein HTR008W-Fernbedienungsprofil.

## Windows starten

Python 3 mit Tkinter installieren und im Projektordner einmalig ausführen:

```powershell
python -m venv .venv-test
.venv-test\Scripts\python.exe -m pip install -r requirements-testprogramm.txt
```

Danach **`start.cmd` doppelklicken**, den Mega-Port auswählen und verbinden. Das Testprogramm empfängt Telegramme, bietet HOCH/STOP/RUNTER mit optionalem automatischem STOP und speichert Gerätezuordnungen auf dem Laptop. Schnittstelle: **57600 Baud, LF**.

## Firmware entwickeln

`RFLink.code-workspace` in **Visual Studio Code** öffnen und PlatformIO installieren. Projekt: `firmware`, Environment: `mega2560`.

```powershell
platformio run -d firmware
platformio run -d firmware -t upload --upload-port COM3
```

Den Port an den eigenen Mega anpassen und das Testprogramm vor dem Upload schließen. Details: `firmware/README.txt` und `RFLink_Bedienung.txt`.

## Unterstützte Fernbedienungen

| Fernbedienung | Unterstützung | Gerätekennung und Kanal |
| --- | --- | --- |
| Nobily / Brel | `ShutterRemote40`, Empfang/Senden am Motor getestet | Echte 24-Bit-ID; `41`–`45` für Kanal 1–5, `40` für alle Kanäle |
| HTR008W | Empfang/Senden des getesteten Profils | `000001` ist ein lokaler Alias; allgemeine Geräte-ID noch nicht entschlüsselt |

Die Firmware decodiert und sendet Telegramme. Namen, Räume und Gerätezuordnungen liegen extern. BUILD 0A verwendet keinen zusätzlichen EEPROM-Lernspeicher. Weitere Geräte desselben unterstützten Protokolls können extern zugeordnet werden; unbekannte Protokolle benötigen einen Decoder. HTR-Unterstützung gilt bisher für das aufgezeichnete Profil.

## ioBroker

Der [Adapter-Fork](https://github.com/zonfacter/ioBroker.rflink) legt automatisch getrennte **UP-, STOP- und DOWN-Tasten pro Rollladenkanal** an. Bereits vorhandene HTR-Tasten unter `rflink.0.channels.HTR008W_1` bleiben erhalten.

Versioniertes [Installationspaket](https://github.com/zonfacter/ioBroker.rflink/releases/tag/v2.1.13-rfbuttons.2) und [Wartungsanleitung](https://github.com/zonfacter/ioBroker.rflink/blob/master/FORK.md). Automatische RFLink-Updates deaktivieren; offizielle manuelle Updates ersetzen den Fork. Installation und Neustart sind geprüft; die Motorreaktion über die neuen direkten Adaptertasten ist noch praktisch zu bestätigen.

`iobroker/RFLink_bridge.js` bietet ergänzende Tasten und Empfangsanzeigen unter `0_userdata.0.RFLink`. Die direkten Fork-Tasten funktionieren unabhängig davon.

## Tests

Mit Python 3 und `g++` (bei Bedarf über `CXX` konfigurieren):

```powershell
python firmware/tests/run_capture_tests.py
python firmware/tests/run_htr_capture_tests.py
.venv-test\Scripts\python.exe firmware/tests/test_testprogramm.py
node firmware/tests/test_iobroker.js
node firmware/tests/test_iobroker_bridge.js
```

Die Tests verwenden echte Pulsaufzeichnungen. Der Nobily-Test prüft zusätzlich alle 65.536 Kombinationen aus Kanal- und Befehlsbyte. Der HTR-Test verwendet das zuvor erzeugte C++-Testprogramm. GUI-Tests benötigen Tkinter und eine Desktop-Sitzung.

Die [Beschreibung der Rohdaten](firmware/RAW_DATEN.md) erklärt Pulslisten, `RFDEBUG` gegenüber `RFTIMING`, den Nobily-Telegrammaufbau und die bestätigten HTR-Muster einschließlich der noch offenen Felder.

Node.js-20/22/24-Prüfungen und die automatischen Adaptertests liegen im [Adapter-Fork](https://github.com/zonfacter/ioBroker.rflink/actions).

## Lizenzen

Die Firmware basiert auf dem lokalen Quellstand aus [jwdb/rflink](https://github.com/jwdb/rflink). Copyright-Hinweise, Quellheader und `firmware/legacy/License.txt` bleiben erhalten; deren Bedingungen gelten für diese Bestandteile. Die ioBroker-Parser-Testdateien behalten ihre MIT-Lizenz. Dieses Repository erklärt die ursprünglichen Bestandteile nicht pauschal als MIT-lizenziert.
