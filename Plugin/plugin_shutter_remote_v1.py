#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shutter Remote Plugin v1.0 - Rollladen Funkfernbedienung Decoder

Protokoll-Analyse basierend auf RFDEBUG Ausgabe:
================================================
Format: PWM (Pulse Width Modulation)
- Sync: ~600-750µs Preamble + ~2370-2400µs Sync-Puls
- Bit 0: Kurz-Lang (~450µs + ~1050µs)
- Bit 1: Lang-Kurz (~1050µs + ~450µs)
- 40 Datenbits
- End-Pause: ~6990µs

Bit-Struktur (40 Bits):
=======================
┌────────────────────────┬──────────┬──────────┬──────────┐
│ Remote ID (24 Bits)    │ CH (4 B) │ CMD (4 B)│ CHK (8 B)│
│ Bits 0-23              │ Bits 24-27│Bits 28-31│Bits 32-39│
└────────────────────────┴──────────┴──────────┴──────────┘

Ermittelte Werte (Kanal 3 RUNTER):
==================================
Remote ID:   0x98461A
Channel:     0x4 (intern) → CH3 auf Fernbedienung
Command:     0x3 = DOWN

Befehls-Codes (zu verifizieren mit weiteren Tests):
===================================================
0x1 = STOP (vermutlich)
0x2 = UP (vermutlich)  
0x3 = DOWN (bestätigt)
0x8 = PROG (vermutlich)
"""

import re
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime


@dataclass
class ShutterCommand:
    """Repräsentiert einen dekodierten Rollladen-Befehl."""
    raw_bits: str
    remote_id: int
    channel: int           # Interner Kanal (0-basiert)
    channel_label: int     # Kanal auf Fernbedienung (wie beschriftet)
    command: str
    command_code: int
    checksum: int
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    def to_dict(self) -> dict:
        return {
            'raw_bits': self.raw_bits,
            'remote_id': f"0x{self.remote_id:06X}",
            'channel': self.channel,
            'channel_label': self.channel_label,
            'command': self.command,
            'command_code': self.command_code,
            'checksum': f"0x{self.checksum:02X}",
        }


class ShutterRemoteProtocol:
    """
    Protokoll-Handler für Rollladen-Funkfernbedienungen.
    
    Unterstützt:
    - Dekodierung von RFDEBUG Pulsen
    - Lernen von neuen Fernbedienungen/Befehlen
    - Generierung von Sende-Sequenzen
    """
    
    # Timing-Konstanten (µs)
    SYNC_MIN = 2200
    SYNC_MAX = 2500
    SHORT_MIN = 350
    SHORT_MAX = 600
    LONG_MIN = 900
    LONG_MAX = 1200
    END_MIN = 5000
    
    # Standard-Befehle (können durch Lernen überschrieben werden)
    DEFAULT_COMMANDS = {
        0x1: "STOP",
        0x2: "UP",
        0x3: "DOWN",
        0x4: "UP",      # Alternative
        0x5: "DOWN",    # Alternative
        0x8: "PROG",
        0xA: "STOP",    # Alternative
    }
    
    def __init__(self):
        # Gelernte Daten
        self.learned_remotes: Dict[int, str] = {}           # remote_id -> name
        self.learned_commands: Dict[str, str] = {}          # bits -> command_name
        self.channel_mapping: Dict[int, Dict[int, int]] = {} # remote_id -> {internal: label}
        
        # Statistiken
        self.decode_count = 0
        self.last_command: Optional[ShutterCommand] = None
        self.history: List[ShutterCommand] = []
        
        # Lade gespeicherte Daten
        self._load_learned_data()
    
    def _load_learned_data(self):
        """Lädt gelernte Daten aus Datei."""
        config_file = os.path.expanduser("~/.shutter_remote_config.json")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)
                    self.learned_remotes = {int(k, 16): v for k, v in data.get('remotes', {}).items()}
                    self.learned_commands = data.get('commands', {})
                    self.channel_mapping = {int(k, 16): v for k, v in data.get('channels', {}).items()}
            except Exception as e:
                print(f"[WARN] Config laden fehlgeschlagen: {e}")
    
    def _save_learned_data(self):
        """Speichert gelernte Daten in Datei."""
        config_file = os.path.expanduser("~/.shutter_remote_config.json")
        try:
            data = {
                'remotes': {f"0x{k:06X}": v for k, v in self.learned_remotes.items()},
                'commands': self.learned_commands,
                'channels': {f"0x{k:06X}": v for k, v in self.channel_mapping.items()},
            }
            with open(config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[WARN] Config speichern fehlgeschlagen: {e}")
    
    def decode_pulses(self, pulses: List[int]) -> Optional[ShutterCommand]:
        """
        Dekodiert eine Puls-Sequenz zu einem ShutterCommand.
        
        Args:
            pulses: Liste von Puls-Dauern in Mikrosekunden
            
        Returns:
            ShutterCommand oder None bei Fehler
        """
        if not pulses or len(pulses) < 78:
            return None
        
        # Finde Sync-Puls
        sync_idx = -1
        for i in range(min(5, len(pulses))):
            if self.SYNC_MIN <= pulses[i] <= self.SYNC_MAX:
                sync_idx = i
                break
        
        # Fallback: Suche nach Puls > 2000µs
        if sync_idx < 0:
            for i in range(min(5, len(pulses))):
                if pulses[i] > 2000:
                    sync_idx = i
                    break
        
        if sync_idx < 0:
            return None
        
        # Extrahiere Datenpulse
        data_pulses = pulses[sync_idx + 1:]
        
        # Entferne End-Puls
        if data_pulses and data_pulses[-1] >= self.END_MIN:
            data_pulses = data_pulses[:-1]
        
        # Dekodiere Bits
        bits = []
        for i in range(0, len(data_pulses) - 1, 2):
            p1, p2 = data_pulses[i], data_pulses[i + 1]
            
            p1_is_short = self.SHORT_MIN <= p1 <= self.SHORT_MAX
            p1_is_long = self.LONG_MIN <= p1 <= self.LONG_MAX
            p2_is_short = self.SHORT_MIN <= p2 <= self.SHORT_MAX
            p2_is_long = self.LONG_MIN <= p2 <= self.LONG_MAX
            
            if p1_is_long and p2_is_short:
                bits.append('1')
            elif p1_is_short and p2_is_long:
                bits.append('0')
            else:
                # Toleranter Fallback
                if p1 > p2:
                    bits.append('1')
                else:
                    bits.append('0')
        
        # Mindestens 36 Bits benötigt
        if len(bits) < 36:
            return None
        
        bit_string = ''.join(bits)
        
        # Auf 40 Bits auffüllen falls nötig
        while len(bit_string) < 40:
            bit_string += '0'
        bit_string = bit_string[:40]  # Auf 40 begrenzen
        
        # Parse Felder
        try:
            remote_id = int(bit_string[0:24], 2)
            channel_internal = int(bit_string[24:28], 2)
            command_code = int(bit_string[28:32], 2)
            checksum = int(bit_string[32:40], 2)
        except ValueError:
            return None
        
        # Ermittle Kanal-Label (Mapping oder Heuristik)
        channel_label = self._get_channel_label(remote_id, channel_internal)
        
        # Ermittle Befehlsname
        command_name = self._get_command_name(command_code, bit_string)
        
        cmd = ShutterCommand(
            raw_bits=bit_string,
            remote_id=remote_id,
            channel=channel_internal,
            channel_label=channel_label,
            command=command_name,
            command_code=command_code,
            checksum=checksum,
        )
        
        self.decode_count += 1
        self.last_command = cmd
        self.history.append(cmd)
        if len(self.history) > 100:
            self.history.pop(0)
        
        return cmd
    
    def _get_channel_label(self, remote_id: int, internal: int) -> int:
        """Ermittelt das Kanal-Label basierend auf Mapping oder Heuristik."""
        # Prüfe gelerntes Mapping
        if remote_id in self.channel_mapping:
            mapping = self.channel_mapping[remote_id]
            if str(internal) in mapping:
                return mapping[str(internal)]
        
        # Heuristik: Basierend auf bekannter Fernbedienung 0x98461A
        # Internal 4 → Label 3 (bestätigt durch User)
        # Vermutung: Label = Internal - 1
        if internal > 0:
            return internal - 1
        return internal
    
    def _get_command_name(self, code: int, bits: str) -> str:
        """Ermittelt den Befehlsnamen."""
        # Prüfe gelernte Befehle
        if bits in self.learned_commands:
            return self.learned_commands[bits]
        
        # Standard-Befehle
        return self.DEFAULT_COMMANDS.get(code, f"CMD_{code:X}")
    
    def learn_remote(self, remote_id: int, name: str) -> None:
        """Speichert einen Fernbedienungs-Namen."""
        self.learned_remotes[remote_id] = name
        self._save_learned_data()
        print(f"[LEARN] Fernbedienung 0x{remote_id:06X} = '{name}'")
    
    def learn_channel(self, remote_id: int, internal: int, label: int) -> None:
        """Speichert ein Kanal-Mapping."""
        if remote_id not in self.channel_mapping:
            self.channel_mapping[remote_id] = {}
        self.channel_mapping[remote_id][str(internal)] = label
        self._save_learned_data()
        print(f"[LEARN] Kanal-Mapping: Remote 0x{remote_id:06X}, Internal {internal} = Label {label}")
    
    def learn_command(self, bits: str, name: str) -> None:
        """Speichert einen Befehlsnamen für ein Bit-Muster."""
        self.learned_commands[bits] = name.upper()
        self._save_learned_data()
        print(f"[LEARN] Befehl '{name}' = {bits[:20]}...")
    
    def generate_pulses(self, remote_id: int, channel: int, command: str) -> List[int]:
        """
        Generiert Puls-Sequenz für einen Befehl.
        
        Args:
            remote_id: Fernbedienungs-ID (24 Bit)
            channel: Kanal-Label (wie auf FB beschriftet)
            command: Befehlsname (UP, DOWN, STOP)
            
        Returns:
            Liste von Puls-Dauern in Mikrosekunden
        """
        # Kommando-Codes
        cmd_codes = {
            'STOP': 0x1,
            'UP': 0x2,
            'DOWN': 0x3,
            'PROG': 0x8,
        }
        
        command_code = cmd_codes.get(command.upper(), 0x1)
        
        # Channel-Label zu Internal umwandeln
        # Umkehrung der Heuristik: Internal = Label + 1
        channel_internal = channel + 1
        
        # Checksum berechnen (einfache XOR oder konstant)
        # Basierend auf Analyse: Checksum scheint 0x32 oder 0x33 zu sein
        checksum = 0x32
        
        # Bit-String erstellen
        bits = (f"{remote_id:024b}"
                f"{channel_internal:04b}"
                f"{command_code:04b}"
                f"{checksum:08b}")
        
        # Pulse generieren
        pulses = []
        
        # Preamble + Sync
        pulses.append(700)   # Preamble
        pulses.append(2400)  # Sync
        
        # Datenbits
        for bit in bits:
            if bit == '1':
                pulses.append(1050)  # Lang
                pulses.append(450)   # Kurz
            else:
                pulses.append(450)   # Kurz
                pulses.append(1050)  # Lang
        
        # End-Pause
        pulses.append(7000)
        
        return pulses
    
    def format_rflink_send(self, pulses: List[int], repeat: int = 5) -> str:
        """
        Formatiert Pulse für RFLink-kompatibles Senden.
        
        Hinweis: Standard RFLink unterstützt kein direktes Puls-Senden.
        Dies ist für alternative Firmware oder eigene Hardware gedacht.
        """
        pulse_str = ",".join(str(p) for p in pulses)
        return f"10;PULSE={repeat};{len(pulses)};{pulse_str};\n"


class ShutterRemotePlugin:
    """
    Plugin für RS485 Sniffer / RFLink Logger.
    Verarbeitet RFDEBUG-Ausgaben und dekodiert Rollladen-Befehle.
    """
    
    name = "Shutter Remote"
    description = "Dekodiert und sendet Rollladen-Funkbefehle (40-bit PWM)"
    version = "1.0.0"
    
    def __init__(self):
        self.protocol = ShutterRemoteProtocol()
        self.enabled = True
        self.debug_mode = False
    
    def process_message(self, message: str) -> Optional[Dict]:
        """
        Verarbeitet eine RFLink-Nachricht oder RFDEBUG-Zeile.
        
        Args:
            message: Die zu verarbeitende Nachricht
            
        Returns:
            Dictionary mit dekodierten Daten oder None
        """
        # Prüfe ob es eine DEBUG-Zeile ist
        if "[DEBUG]" not in message and "Pulses=" not in message:
            return None
        
        # Extrahiere Pulse
        pulses = self._extract_pulses(message)
        if not pulses:
            return None
        
        # Filtere nach Puls-Anzahl (78-86 für dieses Protokoll)
        if not (78 <= len(pulses) <= 86):
            return None
        
        # Dekodiere
        cmd = self.protocol.decode_pulses(pulses)
        if not cmd:
            return None
        
        # Ergebnis formatieren
        result = {
            'type': 'shutter',
            'protocol': 'ShutterRemote40',
            'remote_id': f"0x{cmd.remote_id:06X}",
            'remote_name': self.protocol.learned_remotes.get(cmd.remote_id, "Unknown"),
            'channel': cmd.channel_label,
            'channel_internal': cmd.channel,
            'command': cmd.command,
            'command_code': f"0x{cmd.command_code:X}",
            'checksum': f"0x{cmd.checksum:02X}",
            'bits': cmd.raw_bits,
            'timestamp': cmd.timestamp,
        }
        
        if self.debug_mode:
            result['debug'] = {
                'raw_bits': cmd.raw_bits,
                'pulse_count': len(pulses),
            }
        
        return result
    
    def _extract_pulses(self, line: str) -> Optional[List[int]]:
        """Extrahiert Pulse aus einer Zeile."""
        # Format: Pulses(uSec)=123,456,789,...
        match = re.search(r"Pulses\(uSec\)=([0-9,]+)", line)
        if match:
            try:
                return [int(p) for p in match.group(1).split(",")]
            except ValueError:
                pass
        
        # Alternatives Format: pulse_timings: [...]
        match = re.search(r"'pulse_timings':\s*\[([0-9,\s]+)\]", line)
        if match:
            try:
                return [int(p.strip()) for p in match.group(1).split(",")]
            except ValueError:
                pass
        
        return None
    
    def learn_current(self, command_name: str) -> bool:
        """Lernt den letzten Befehl unter einem Namen."""
        if self.protocol.last_command:
            self.protocol.learn_command(
                self.protocol.last_command.raw_bits,
                command_name
            )
            return True
        return False
    
    def learn_channel_mapping(self, label: int) -> bool:
        """Lernt das Kanal-Mapping für den letzten Befehl."""
        if self.protocol.last_command:
            cmd = self.protocol.last_command
            self.protocol.learn_channel(cmd.remote_id, cmd.channel, label)
            return True
        return False
    
    def create_send_command(self, remote_id: int, channel: int, command: str) -> Dict:
        """Erstellt einen Sende-Befehl."""
        pulses = self.protocol.generate_pulses(remote_id, channel, command)
        
        # Generiere auch Bit-String für Anzeige
        cmd_codes = {'STOP': 0x1, 'UP': 0x2, 'DOWN': 0x3, 'PROG': 0x8}
        cmd_code = cmd_codes.get(command.upper(), 0x1)
        channel_internal = channel + 1
        checksum = 0x32
        bits = f"{remote_id:024b}{channel_internal:04b}{cmd_code:04b}{checksum:08b}"
        
        return {
            'remote_id': f"0x{remote_id:06X}",
            'channel': channel,
            'command': command.upper(),
            'bits': bits,
            'pulses': pulses,
            'pulse_count': len(pulses),
            'rflink_format': self.protocol.format_rflink_send(pulses),
        }
    
    def get_statistics(self) -> Dict:
        """Gibt Statistiken zurück."""
        return {
            'decode_count': self.protocol.decode_count,
            'learned_remotes': len(self.protocol.learned_remotes),
            'learned_commands': len(self.protocol.learned_commands),
            'history_size': len(self.protocol.history),
            'last_command': self.protocol.last_command.to_dict() if self.protocol.last_command else None,
        }


# =============================================================================
# Test und Demo
# =============================================================================

def demo():
    """Demonstriert das Plugin mit den gegebenen Testdaten."""
    
    plugin = ShutterRemotePlugin()
    plugin.debug_mode = True
    
    # Testdaten (Kanal 3 RUNTER)
    test_lines = [
        "20:49:22.281 ◀ [DEBUG] Pulses=82 | Pulses(uSec)=750,2370,1050,450,450,1050,450,1050,1050,480,1050,480,450,1080,450,1080,450,1110,450,1080,1050,480,450,1050,450,1050,450,1050,1050,480,1050,480,450,1080,450,1050,450,1050,450,1080,1050,480,1050,480,450,1080,1050,450,450,1110,450,1050,1050,450,450,1050,450,1050,450,1050,450,1050,1050,480,1050,510,450,1080,450,1080,1050,450,1050,480,450,1050,450,1050,1050,450,1050,6990",
        "20:49:32.060 ◀ [DEBUG] Pulses=82 | Pulses(uSec)=720,2400,1050,480,450,1050,450,1080,1050,480,1050,480,450,1050,450,1050,450,1080,450,1050,1050,450,450,1050,450,1050,450,1050,1050,480,1050,480,450,1110,450,1080,450,1050,450,1050,1050,450,1050,480,450,1050,1050,480,450,1080,450,1050,1050,480,450,1080,450,1080,450,1080,450,1080,1050,450,1050,510,450,1050,450,1050,1050,480,1050,480,450,1050,450,1050,1050,480,1050,6990",
    ]
    
    print("=" * 70)
    print("SHUTTER REMOTE PLUGIN - DEMO")
    print("=" * 70)
    print()
    
    for line in test_lines:
        result = plugin.process_message(line)
        if result:
            print(f"✓ Dekodiert:")
            print(f"  Remote:   {result['remote_id']}")
            print(f"  Kanal:    {result['channel']} (intern: {result['channel_internal']})")
            print(f"  Befehl:   {result['command']} ({result['command_code']})")
            print(f"  Checksum: {result['checksum']}")
            print()
    
    # Kanal-Mapping lernen (User sagt CH3, intern ist es 4)
    print("=" * 70)
    print("KANAL-MAPPING LERNEN")
    print("=" * 70)
    
    # Lerne: Internal 4 = Label 3
    plugin.protocol.learn_channel(0x98461A, 4, 3)
    
    # Teste erneut
    result = plugin.process_message(test_lines[0])
    if result:
        print(f"\nNach Lernen: Kanal = {result['channel']} ✓")
    
    # Befehl lernen
    print()
    print("=" * 70)
    print("BEFEHL LERNEN")
    print("=" * 70)
    
    plugin.learn_current("DOWN")  # Lernt den letzten Befehl als DOWN
    
    # Sende-Befehl generieren
    print()
    print("=" * 70)
    print("SENDE-BEFEHLE GENERIEREN")
    print("=" * 70)
    
    for cmd_name in ["UP", "DOWN", "STOP"]:
        send_data = plugin.create_send_command(0x98461A, 3, cmd_name)
        print(f"\n{cmd_name} für Kanal 3:")
        print(f"  Remote:  {send_data['remote_id']}")
        print(f"  Bits:    {send_data['bits']}")
        print(f"  Pulse:   {send_data['pulse_count']}")
    
    # Statistiken
    print()
    print("=" * 70)
    print("STATISTIKEN")
    print("=" * 70)
    stats = plugin.get_statistics()
    print(f"Dekodiert:          {stats['decode_count']} Befehle")
    print(f"Gelernte Remotes:   {stats['learned_remotes']}")
    print(f"Gelernte Befehle:   {stats['learned_commands']}")
    
    print()
    print("=" * 70)
    print("NÄCHSTE SCHRITTE")
    print("=" * 70)
    print("""
Um das Protokoll vollständig zu verifizieren, teste bitte:

1. ANDERE BEFEHLE auf Kanal 3:
   - Taste HOCH (UP)
   - Taste STOP
   → Damit können wir die Command-Codes verifizieren

2. ANDERE KANÄLE:
   - Kanal 1, 2, 4 etc.
   → Damit können wir das Channel-Encoding verstehen

3. PROGRAMMIER-MODUS (falls vorhanden)
   → Für Kopplungs-Funktion

Sende mir die RFDEBUG-Ausgaben und ich aktualisiere das Plugin!
""")


if __name__ == "__main__":
    demo()
