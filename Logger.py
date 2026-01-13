#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RS485 Sniffer v2.0.0 - HausBus mit RFLink Plugin-System
Features: Multi-byte delimiter, timeout-based framing, ASCII+Hex view, 
          Bus load calculation, RFLink protocol decoder, Plugin system
"""

import serial
import serial.tools.list_ports
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import binascii
import queue
from typing import Optional, List, Dict, Any, Callable
import sys
import time
from collections import deque
import re
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

__version__ = "2.0.0"
__changelog__ = [
    {"version": "2.0.0", "date": "2026-01-13", "author": "Assistant",
     "description": "Added RFLink protocol support, plugin system, device tracking"},
    {"version": "1.4.0", "date": "2026-01-13", "author": "Assistant",
     "description": "Added bus load calculation, statistics panel, live graphs"},
    {"version": "1.3.0", "date": "2026-01-12", "author": "Assistant",
     "description": "Multi-byte delimiter, timeout framing, ASCII+Hex dual view"},
]


# =============================================================================
# RFLink Protocol Definitions
# =============================================================================

class RFLinkFieldType(Enum):
    """RFLink data field types with their parsing rules."""
    ID = ("ID", "hex", "Device ID")
    SWITCH = ("SWITCH", "str", "Switch/Button")
    CMD = ("CMD", "str", "Command")
    SET_LEVEL = ("SET_LEVEL", "int", "Dim Level")
    TEMP = ("TEMP", "temp", "Temperature °C")
    HUM = ("HUM", "int", "Humidity %")
    BARO = ("BARO", "hex", "Barometer hPa")
    HSTATUS = ("HSTATUS", "int", "Humidity Status")
    BFORECAST = ("BFORECAST", "int", "Weather Forecast")
    UV = ("UV", "hex", "UV Index")
    LUX = ("LUX", "hex", "Light Intensity")
    BAT = ("BAT", "str", "Battery Status")
    RAIN = ("RAIN", "rain", "Rain mm")
    RAINRATE = ("RAINRATE", "rain", "Rain Rate mm/h")
    WINSP = ("WINSP", "wind", "Wind Speed km/h")
    AWINSP = ("AWINSP", "wind", "Avg Wind km/h")
    WINGS = ("WINGS", "hex", "Wind Gust km/h")
    WINDIR = ("WINDIR", "int", "Wind Direction")
    WINCHL = ("WINCHL", "temp", "Wind Chill °C")
    WINTMP = ("WINTMP", "temp", "Wind Temp °C")
    CHIME = ("CHIME", "int", "Chime Number")
    SMOKEALERT = ("SMOKEALERT", "str", "Smoke Alert")
    PIR = ("PIR", "str", "PIR Motion")
    CO2 = ("CO2", "int", "CO2 ppm")
    SOUND = ("SOUND", "int", "Sound Level")
    KWATT = ("KWATT", "hex", "Power kW")
    WATT = ("WATT", "hex", "Power W")
    CURRENT = ("CURRENT", "int", "Current A")
    CURRENT2 = ("CURRENT2", "int", "Current Ph2 A")
    CURRENT3 = ("CURRENT3", "int", "Current Ph3 A")
    DIST = ("DIST", "int", "Distance")
    METER = ("METER", "int", "Meter Value")
    VOLT = ("VOLT", "int", "Voltage V")
    RGBW = ("RGBW", "hex", "RGB Color")


@dataclass
class RFLinkMessage:
    """Parsed RFLink message."""
    raw: str
    node: str  # 20 = from RFLink, 10 = to RFLink
    sequence: str
    protocol: str
    fields: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]


@dataclass  
class RFLinkDevice:
    """Tracked RFLink device."""
    protocol: str
    device_id: str
    switch: str = ""
    last_seen: str = ""
    last_cmd: str = ""
    values: Dict[str, Any] = field(default_factory=dict)
    message_count: int = 0
    
    @property
    def unique_id(self) -> str:
        if self.switch:
            return f"{self.protocol}:{self.device_id}:{self.switch}"
        return f"{self.protocol}:{self.device_id}"


# =============================================================================
# Plugin System Base Classes
# =============================================================================

class PluginBase(ABC):
    """Base class for all plugins."""
    
    name: str = "BasePlugin"
    description: str = "Base plugin class"
    version: str = "1.0.0"
    
    def __init__(self, sniffer: "RS485Sniffer"):
        self.sniffer = sniffer
        self.enabled = True
    
    @abstractmethod
    def process_message(self, msg: RFLinkMessage) -> Optional[Dict[str, Any]]:
        """Process an RFLink message. Return dict with additional data or None."""
        pass
    
    def on_enable(self) -> None:
        """Called when plugin is enabled."""
        pass
    
    def on_disable(self) -> None:
        """Called when plugin is disabled."""
        pass


class WeatherPlugin(PluginBase):
    """Plugin for weather sensor data processing."""
    
    name = "Weather Sensors"
    description = "Process weather sensor data (temp, humidity, rain, wind)"
    version = "1.0.0"
    
    WIND_DIRECTIONS = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    
    def process_message(self, msg: RFLinkMessage) -> Optional[Dict[str, Any]]:
        result = {}
        
        # Temperature conversion
        if "TEMP" in msg.fields:
            raw_temp = msg.fields["TEMP"]
            if isinstance(raw_temp, int):
                if raw_temp & 0x8000:  # Negative
                    raw_temp = -(raw_temp & 0x7FFF)
                result["temperature_c"] = raw_temp / 10.0
                result["temperature_f"] = result["temperature_c"] * 9/5 + 32
        
        # Wind direction conversion
        if "WINDIR" in msg.fields:
            dir_idx = msg.fields["WINDIR"]
            if 0 <= dir_idx < 16:
                result["wind_direction_text"] = self.WIND_DIRECTIONS[dir_idx]
                result["wind_direction_deg"] = dir_idx * 22.5
        
        # Wind speed conversion
        if "WINSP" in msg.fields:
            result["wind_speed_kmh"] = msg.fields["WINSP"] / 10.0
            result["wind_speed_ms"] = result["wind_speed_kmh"] / 3.6
        
        # Rain conversion
        if "RAIN" in msg.fields:
            result["rain_mm"] = msg.fields["RAIN"] / 10.0
        
        return result if result else None


class SwitchPlugin(PluginBase):
    """Plugin for switch/remote control processing."""
    
    name = "Switches & Remotes"
    description = "Process switch and remote control signals"
    version = "1.0.0"
    
    def __init__(self, sniffer: "RS485Sniffer"):
        super().__init__(sniffer)
        self.switch_history: Dict[str, List[Dict]] = {}
    
    def process_message(self, msg: RFLinkMessage) -> Optional[Dict[str, Any]]:
        if "CMD" not in msg.fields:
            return None
        
        device_id = msg.fields.get("ID", "unknown")
        switch = msg.fields.get("SWITCH", "")
        cmd = msg.fields.get("CMD", "")
        
        key = f"{msg.protocol}:{device_id}:{switch}"
        
        if key not in self.switch_history:
            self.switch_history[key] = []
        
        self.switch_history[key].append({
            "timestamp": msg.timestamp,
            "cmd": cmd
        })
        
        # Keep only last 100 entries
        if len(self.switch_history[key]) > 100:
            self.switch_history[key] = self.switch_history[key][-100:]
        
        return {
            "history_count": len(self.switch_history[key]),
            "last_commands": self.switch_history[key][-5:]
        }


class DebugPlugin(PluginBase):
    """Plugin for debug output processing."""
    
    name = "Debug Output"
    description = "Process RFDEBUG and RFUDEBUG output"
    version = "1.0.0"
    
    def process_message(self, msg: RFLinkMessage) -> Optional[Dict[str, Any]]:
        if msg.protocol not in ("DEBUG", "RFDEBUG", "RFUDEBUG", "QRFDEBUG"):
            return None
        
        result = {"is_debug": True}
        
        # Parse pulse data if present
        if "Pulses" in msg.raw:
            pulse_match = re.search(r"Pulses=(\d+)", msg.raw)
            if pulse_match:
                result["pulse_count"] = int(pulse_match.group(1))
            
            # Extract pulse timings
            timing_match = re.search(r"Pulses\(uSec\)=([^;]+)", msg.raw)
            if timing_match:
                pulses = [int(p) for p in timing_match.group(1).split(",") if p.isdigit()]
                result["pulse_timings"] = pulses
                if pulses:
                    result["avg_pulse"] = sum(pulses) / len(pulses)
                    result["min_pulse"] = min(pulses)
                    result["max_pulse"] = max(pulses)
        
        return result


# =============================================================================
# RFLink Protocol Parser
# =============================================================================

class RFLinkParser:
    """Parser for RFLink protocol messages."""
    
    def __init__(self):
        self.field_parsers = {
            "ID": self._parse_hex,
            "TEMP": self._parse_hex,
            "HUM": self._parse_int,
            "BARO": self._parse_hex,
            "RAIN": self._parse_hex,
            "RAINRATE": self._parse_hex,
            "WINSP": self._parse_hex,
            "AWINSP": self._parse_hex,
            "WINGS": self._parse_hex,
            "WINDIR": self._parse_int,
            "WINCHL": self._parse_hex,
            "WINTMP": self._parse_hex,
            "UV": self._parse_hex,
            "LUX": self._parse_hex,
            "BAT": self._parse_str,
            "CMD": self._parse_str,
            "SWITCH": self._parse_str,
            "SET_LEVEL": self._parse_int,
            "CHIME": self._parse_int,
            "SMOKEALERT": self._parse_str,
            "PIR": self._parse_str,
            "CO2": self._parse_int,
            "SOUND": self._parse_int,
            "KWATT": self._parse_hex,
            "WATT": self._parse_hex,
            "CURRENT": self._parse_int,
            "CURRENT2": self._parse_int,
            "CURRENT3": self._parse_int,
            "DIST": self._parse_int,
            "METER": self._parse_int,
            "VOLT": self._parse_int,
            "RGBW": self._parse_hex,
            "HSTATUS": self._parse_int,
            "BFORECAST": self._parse_int,
        }
    
    def _parse_hex(self, value: str) -> int:
        try:
            return int(value, 16)
        except ValueError:
            return 0
    
    def _parse_int(self, value: str) -> int:
        try:
            return int(value)
        except ValueError:
            return 0
    
    def _parse_str(self, value: str) -> str:
        return value
    
    def parse(self, line: str) -> Optional[RFLinkMessage]:
        """Parse an RFLink message line."""
        line = line.strip()
        if not line:
            return None
        
        parts = line.split(";")
        if len(parts) < 3:
            return None
        
        # Basic structure: NODE;SEQ;PROTOCOL;FIELDS...
        node = parts[0]
        sequence = parts[1]
        protocol = parts[2]
        
        # Special responses
        if protocol in ("OK", "PONG"):
            return RFLinkMessage(
                raw=line,
                node=node,
                sequence=sequence,
                protocol=protocol
            )
        
        # Parse fields
        fields = {}
        for part in parts[3:]:
            if "=" in part:
                key, value = part.split("=", 1)
                parser = self.field_parsers.get(key, self._parse_str)
                fields[key] = parser(value)
        
        return RFLinkMessage(
            raw=line,
            node=node,
            sequence=sequence,
            protocol=protocol,
            fields=fields
        )
    
    def format_value(self, field_type: str, raw_value: Any) -> str:
        """Format a parsed value for display."""
        if field_type == "TEMP":
            if isinstance(raw_value, int):
                if raw_value & 0x8000:
                    raw_value = -(raw_value & 0x7FFF)
                return f"{raw_value / 10.0:.1f}°C"
        elif field_type == "HUM":
            return f"{raw_value}%"
        elif field_type in ("RAIN", "RAINRATE"):
            return f"{raw_value / 10.0:.1f}mm"
        elif field_type in ("WINSP", "AWINSP"):
            return f"{raw_value / 10.0:.1f}km/h"
        elif field_type == "WINDIR":
            directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                         "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
            if 0 <= raw_value < 16:
                return f"{directions[raw_value]} ({raw_value * 22.5}°)"
        elif field_type == "ID":
            return f"0x{raw_value:X}"
        
        return str(raw_value)


# =============================================================================
# Bus Statistics (from v1.4.0)
# =============================================================================

class BusStatistics:
    """Tracks bus statistics and calculates load."""
    
    def __init__(self, baudrate: int, databits: int = 8, parity: str = "None", stopbits: float = 1.0):
        self.baudrate = baudrate
        self.databits = databits
        self.parity_bit = 1 if parity != "None" else 0
        self.stopbits = stopbits
        self.bits_per_byte = 1 + databits + self.parity_bit + stopbits
        
        self.start_time = time.perf_counter()
        self.total_bytes = 0
        self.total_frames = 0
        self.byte_history = deque(maxlen=100)
        self.last_update = time.perf_counter()
        
        self.peak_load = 0.0
        self.peak_bytes_per_sec = 0
        self.current_bytes_per_sec = 0
        self.current_load = 0.0

    def update(self, byte_count: int, frame_count: int = 0) -> None:
        now = time.perf_counter()
        self.total_bytes += byte_count
        self.total_frames += frame_count
        self.byte_history.append((now, byte_count))
        
        cutoff = now - 1.0
        recent_bytes = sum(count for ts, count in self.byte_history if ts >= cutoff)
        self.current_bytes_per_sec = recent_bytes
        
        bits_per_second = recent_bytes * self.bits_per_byte
        self.current_load = (bits_per_second / self.baudrate) * 100.0
        
        if self.current_load > self.peak_load:
            self.peak_load = self.current_load
        if self.current_bytes_per_sec > self.peak_bytes_per_sec:
            self.peak_bytes_per_sec = self.current_bytes_per_sec

    def get_runtime(self) -> float:
        return time.perf_counter() - self.start_time

    def get_average_bytes_per_sec(self) -> float:
        runtime = self.get_runtime()
        return self.total_bytes / runtime if runtime > 0 else 0

    def reset(self) -> None:
        self.start_time = time.perf_counter()
        self.total_bytes = 0
        self.total_frames = 0
        self.byte_history.clear()
        self.peak_load = 0.0
        self.peak_bytes_per_sec = 0
        self.current_bytes_per_sec = 0
        self.current_load = 0.0


# =============================================================================
# Main Sniffer Class
# =============================================================================

class RS485Sniffer:
    """RS485 Sniffer with RFLink support and plugin system."""
    
    BAUD_RATES = ["9600", "19200", "38400", "57600", "115200",
                  "230400", "250000", "460800", "500000", "921600", "1000000"]
    
    STOPBITS_MAP = {
        "1": serial.STOPBITS_ONE,
        "1.5": serial.STOPBITS_ONE_POINT_FIVE,
        "2": serial.STOPBITS_TWO
    }
    
    MODE_RAW = "raw"
    MODE_DELIMITER = "delimiter"
    MODE_TIMEOUT = "timeout"
    MODE_BOTH = "both"
    MODE_RFLINK = "rflink"

    def __init__(self, gui: "SnifferGUI") -> None:
        self.gui = gui
        self.ser: Optional[serial.Serial] = None
        self.running: bool = False
        self.thread: Optional[threading.Thread] = None
        self.logfile = None
        self.rx_queue: queue.Queue = queue.Queue()
        
        # Framing settings
        self.frame_mode: str = self.MODE_BOTH
        self.delimiter: bytes = b"\x0D\x0A"
        self.timeout_ms: int = 50
        self.show_ascii: bool = True
        self.show_hex: bool = True
        
        # Statistics
        self.stats: Optional[BusStatistics] = None
        
        # RFLink specific
        self.rflink_parser = RFLinkParser()
        self.rflink_devices: Dict[str, RFLinkDevice] = {}
        self.rflink_msg_queue: queue.Queue = queue.Queue()
        
        # RFLink debug states
        self.rfdebug_state = False
        self.rfudebug_state = False
        self.qrfdebug_state = False
        
        # Plugin system
        self.plugins: Dict[str, PluginBase] = {}
        self._init_default_plugins()

    def _init_default_plugins(self) -> None:
        """Initialize default plugins."""
        self.register_plugin(WeatherPlugin(self))
        self.register_plugin(SwitchPlugin(self))
        self.register_plugin(DebugPlugin(self))

    def register_plugin(self, plugin: PluginBase) -> None:
        """Register a plugin."""
        self.plugins[plugin.name] = plugin
        self.debug_print(f"Plugin registered: {plugin.name} v{plugin.version}")

    def unregister_plugin(self, name: str) -> None:
        """Unregister a plugin."""
        if name in self.plugins:
            self.plugins[name].on_disable()
            del self.plugins[name]

    @staticmethod
    def get_timestamp() -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def debug_print(self, msg: str) -> None:
        print(f"[DEBUG] {msg}", file=sys.stderr, flush=True)

    def set_delimiter(self, hexstr: str) -> bool:
        hexstr = hexstr.replace(" ", "").upper()
        if len(hexstr) == 0 or len(hexstr) % 2 != 0:
            self.gui.queue_msg("Ungültiger Delimiter")
            return False
        try:
            self.delimiter = bytes.fromhex(hexstr)
            self.gui.queue_msg(f"Delimiter: {hexstr} ({len(self.delimiter)} Bytes)")
            return True
        except ValueError:
            self.gui.queue_msg("Ungültiger Hex-Wert")
            return False

    def set_timeout(self, ms: int) -> None:
        self.timeout_ms = max(1, min(10000, ms))
        self.gui.queue_msg(f"Timeout: {self.timeout_ms} ms")

    def set_mode(self, mode: str) -> None:
        self.frame_mode = mode
        mode_names = {
            self.MODE_RAW: "RAW (jedes Byte)",
            self.MODE_DELIMITER: "Delimiter",
            self.MODE_TIMEOUT: "Timeout",
            self.MODE_BOTH: "Delimiter + Timeout",
            self.MODE_RFLINK: "RFLink Protokoll"
        }
        self.gui.queue_msg(f"Modus: {mode_names.get(mode, mode)}")

    def format_frame(self, data: bytes, incomplete: bool = False) -> str:
        ts = self.get_timestamp()
        parts = [f"{ts} RX [{len(data):4d}]"]
        
        if self.show_hex:
            hex_str = data.hex().upper()
            hex_spaced = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
            parts.append(hex_spaced)
        
        if self.show_ascii:
            ascii_str = ""
            for b in data:
                if 32 <= b < 127:
                    ascii_str += chr(b)
                elif b == 0x0D:
                    ascii_str += "\\r"
                elif b == 0x0A:
                    ascii_str += "\\n"
                elif b == 0x09:
                    ascii_str += "\\t"
                else:
                    ascii_str += "."
            parts.append(f'| {ascii_str}')
        
        if incomplete:
            parts.append("(incomplete)")
        
        return " ".join(parts)

    def format_rflink_message(self, msg: RFLinkMessage) -> str:
        """Format an RFLink message for display."""
        ts = msg.timestamp
        
        # Direction indicator
        direction = "◀" if msg.node == "20" else "▶"
        
        # Build field display
        field_parts = []
        for key, value in msg.fields.items():
            formatted = self.rflink_parser.format_value(key, value)
            field_parts.append(f"{key}={formatted}")
        
        fields_str = " | ".join(field_parts) if field_parts else ""
        
        return f"{ts} {direction} [{msg.protocol}] {fields_str}"

    def process_rflink_message(self, msg: RFLinkMessage) -> None:
        """Process an RFLink message through plugins and update devices."""
        
        # Update device tracking
        if "ID" in msg.fields:
            device_id = str(msg.fields["ID"])
            switch = str(msg.fields.get("SWITCH", ""))
            
            device = RFLinkDevice(
                protocol=msg.protocol,
                device_id=device_id,
                switch=switch,
                last_seen=msg.timestamp,
                last_cmd=str(msg.fields.get("CMD", "")),
                message_count=1
            )
            
            key = device.unique_id
            if key in self.rflink_devices:
                device.message_count = self.rflink_devices[key].message_count + 1
                device.values = self.rflink_devices[key].values.copy()
            
            # Update values
            for field, value in msg.fields.items():
                if field not in ("ID", "SWITCH"):
                    device.values[field] = value
            
            self.rflink_devices[key] = device
        
        # Process through plugins
        for name, plugin in self.plugins.items():
            if plugin.enabled:
                try:
                    result = plugin.process_message(msg)
                    if result:
                        msg.fields.update({f"_plugin_{name}": result})
                except Exception as e:
                    self.debug_print(f"Plugin {name} error: {e}")
        
        # Queue for GUI update
        self.rflink_msg_queue.put(msg)

    def send_rflink_command(self, command: str) -> None:
        """Send a command to RFLink."""
        if not self.ser or not self.ser.is_open:
            self.gui.queue_msg("Port nicht offen!")
            return
        
        # Ensure proper format
        if not command.endswith(";"):
            command += ";"
        if not command.startswith("10;"):
            command = "10;" + command
        
        try:
            self.ser.write((command + "\r\n").encode())
            ts = self.get_timestamp()
            self.gui.queue_msg(f"{ts} ▶ TX: {command}")
        except serial.SerialException as e:
            self.gui.queue_msg(f"TX Fehler: {e}")

    def toggle_rfdebug(self) -> None:
        """Toggle RFDEBUG mode."""
        self.rfdebug_state = not self.rfdebug_state
        state = "ON" if self.rfdebug_state else "OFF"
        self.send_rflink_command(f"RFDEBUG={state}")

    def toggle_rfudebug(self) -> None:
        """Toggle RFUDEBUG mode."""
        self.rfudebug_state = not self.rfudebug_state
        state = "ON" if self.rfudebug_state else "OFF"
        self.send_rflink_command(f"RFUDEBUG={state}")

    def toggle_qrfdebug(self) -> None:
        """Toggle QRFDEBUG mode."""
        self.qrfdebug_state = not self.qrfdebug_state
        state = "ON" if self.qrfdebug_state else "OFF"
        self.send_rflink_command(f"QRFDEBUG={state}")

    def open_logfile(self) -> None:
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), 
                       ("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.logfile = open(filename, "w", encoding="utf-8")
            self.gui.queue_msg(f"Logfile: {filename}")

    def close_logfile(self) -> None:
        if self.logfile:
            self.logfile.close()
            self.logfile = None

    def write_log(self, text: str) -> None:
        if self.logfile:
            self.logfile.write(text + "\n")
            self.logfile.flush()

    def start(self) -> None:
        if self.running:
            return

        try:
            baudrate = int(self.gui.baud_var.get())
        except ValueError:
            self.gui.queue_msg("Ungültige Baudrate!")
            return

        port = self.gui.port_var.get()
        if not port:
            self.gui.queue_msg("Kein Port ausgewählt!")
            return

        stopbits = self.STOPBITS_MAP.get(self.gui.stopbits_var.get(), serial.STOPBITS_ONE)
        stopbits_value = float(self.gui.stopbits_var.get())
        
        self.debug_print(f"Opening {port} @ {baudrate} baud, mode={self.frame_mode}")

        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=self.gui.parity_map[self.gui.parity_var.get()],
                stopbits=stopbits,
                timeout=0.001
            )
        except serial.SerialException as e:
            self.gui.queue_msg(f"Fehler: {e}")
            return

        self.stats = BusStatistics(
            baudrate=baudrate,
            databits=8,
            parity=self.gui.parity_var.get(),
            stopbits=stopbits_value
        )

        self.running = True
        self.thread = threading.Thread(target=self.reader_thread, daemon=True)
        self.thread.start()
        self.gui.set_running(True)
        self.gui.queue_msg(f"Gestartet @ {baudrate} baud | Modus: {self.frame_mode}")

    def stop(self) -> None:
        self.debug_print("Stopping...")
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
        self.close_logfile()
        self.gui.set_running(False)
        
        if self.stats:
            self.gui.queue_msg(f"Gestoppt | {self.stats.total_bytes} Bytes, {self.stats.total_frames} Frames")

    def reader_thread(self) -> None:
        self.debug_print("Reader thread started")
        buffer = b""
        last_rx_time = time.perf_counter()
        
        while self.running:
            try:
                if not self.ser or not self.ser.is_open:
                    break
                
                waiting = self.ser.in_waiting
                if waiting > 0:
                    data = self.ser.read(waiting)
                    last_rx_time = time.perf_counter()
                else:
                    data = b""
                    
            except serial.SerialException as e:
                self.debug_print(f"Serial error: {e}")
                self.rx_queue.put(f"[ERROR] {e}")
                break

            if data:
                if self.stats:
                    self.stats.update(len(data), 0)
                
                # RAW MODE
                if self.frame_mode == self.MODE_RAW:
                    for byte in data:
                        line = self.format_frame(bytes([byte]))
                        self.rx_queue.put(line)
                        self.write_log(line)
                        if self.stats:
                            self.stats.total_frames += 1
                    continue
                
                buffer += data
                
                # RFLINK MODE - line-based parsing
                if self.frame_mode == self.MODE_RFLINK:
                    while b"\r\n" in buffer or b"\n" in buffer:
                        # Find line ending
                        idx_rn = buffer.find(b"\r\n")
                        idx_n = buffer.find(b"\n")
                        
                        if idx_rn >= 0 and (idx_n < 0 or idx_rn < idx_n):
                            idx = idx_rn + 2
                        elif idx_n >= 0:
                            idx = idx_n + 1
                        else:
                            break
                        
                        line_bytes = buffer[:idx]
                        buffer = buffer[idx:]
                        
                        try:
                            line_str = line_bytes.decode("utf-8", errors="replace").strip()
                        except:
                            line_str = line_bytes.hex()
                        
                        if line_str:
                            # Parse as RFLink message
                            msg = self.rflink_parser.parse(line_str)
                            if msg:
                                self.process_rflink_message(msg)
                                formatted = self.format_rflink_message(msg)
                            else:
                                formatted = f"{self.get_timestamp()} RAW: {line_str}"
                            
                            self.rx_queue.put(formatted)
                            self.write_log(formatted)
                            if self.stats:
                                self.stats.total_frames += 1
                        
                        last_rx_time = time.perf_counter()
                    continue
                
                # DELIMITER MODE or BOTH MODE
                if self.frame_mode in (self.MODE_DELIMITER, self.MODE_BOTH):
                    while self.delimiter in buffer:
                        idx = buffer.index(self.delimiter) + len(self.delimiter)
                        frame = buffer[:idx]
                        buffer = buffer[idx:]
                        
                        line = self.format_frame(frame)
                        self.rx_queue.put(line)
                        self.write_log(line)
                        if self.stats:
                            self.stats.total_frames += 1
                        last_rx_time = time.perf_counter()
            
            # TIMEOUT MODE or BOTH MODE
            if self.frame_mode in (self.MODE_TIMEOUT, self.MODE_BOTH):
                if buffer:
                    elapsed_ms = (time.perf_counter() - last_rx_time) * 1000
                    if elapsed_ms >= self.timeout_ms:
                        line = self.format_frame(buffer)
                        self.rx_queue.put(line)
                        self.write_log(line)
                        if self.stats:
                            self.stats.total_frames += 1
                        buffer = b""
                        last_rx_time = time.perf_counter()
            
            if not data:
                time.sleep(0.001)

        # Flush remaining buffer
        if buffer:
            line = self.format_frame(buffer, incomplete=True)
            self.rx_queue.put(line)
            self.write_log(line)
            
        self.debug_print(f"Thread exit. {self.stats.total_bytes if self.stats else 0} bytes")

    def send_data(self) -> None:
        if not self.ser or not self.ser.is_open:
            self.gui.queue_msg("Port nicht offen!")
            return

        raw = self.gui.send_var.get().replace(" ", "")
        
        # RFLink mode: send as text
        if self.frame_mode == self.MODE_RFLINK:
            text = self.gui.send_var.get().strip()
            if text:
                self.send_rflink_command(text)
            return
        
        # Hex mode
        if len(raw) % 2 != 0:
            self.gui.queue_msg("Ungültige Hex-Länge")
            return

        try:
            data = bytes.fromhex(raw)
        except ValueError:
            self.gui.queue_msg("Ungültiger Hex-Wert")
            return

        try:
            self.ser.write(data)
            ts = self.get_timestamp()
            hex_spaced = " ".join(raw[i:i+2].upper() for i in range(0, len(raw), 2))
            self.gui.queue_msg(f"{ts} TX [{len(data):4d}] {hex_spaced}")
        except serial.SerialException as e:
            self.gui.queue_msg(f"TX Fehler: {e}")


# =============================================================================
# GUI Class
# =============================================================================

class SnifferGUI:
    """Tkinter GUI for RS485 Sniffer with RFLink support."""
    
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(f"RS485 Sniffer v{__version__} - RFLink Edition")
        self.root.geometry("1400x850")
        
        self.sniffer = RS485Sniffer(self)
        self.msg_queue: queue.Queue = queue.Queue()
        
        self.parity_map = {
            "None": serial.PARITY_NONE,
            "Even": serial.PARITY_EVEN,
            "Odd": serial.PARITY_ODD,
            "Mark": serial.PARITY_MARK,
            "Space": serial.PARITY_SPACE
        }
        
        # Variables
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="57600")  # RFLink default
        self.parity_var = tk.StringVar(value="None")
        self.stopbits_var = tk.StringVar(value="1")
        self.delimiter_var = tk.StringVar(value="0D0A")
        self.timeout_var = tk.StringVar(value="50")
        self.mode_var = tk.StringVar(value=RS485Sniffer.MODE_RFLINK)
        self.show_hex_var = tk.BooleanVar(value=True)
        self.show_ascii_var = tk.BooleanVar(value=True)
        self.autoscroll_var = tk.BooleanVar(value=True)
        self.send_var = tk.StringVar()
        
        # RFLink toggle states
        self.rfdebug_var = tk.BooleanVar(value=False)
        self.rfudebug_var = tk.BooleanVar(value=False)
        self.qrfdebug_var = tk.BooleanVar(value=False)
        
        self.build_gui()
        self.poll_queues()
        self.apply_settings()

    def queue_msg(self, text: str) -> None:
        self.msg_queue.put(text)

    def refresh_ports(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports and not self.port_var.get():
            self.port_combo.current(0)
        self.queue_msg(f"Ports: {len(ports)} gefunden")

    def apply_settings(self) -> None:
        self.sniffer.set_delimiter(self.delimiter_var.get())
        try:
            self.sniffer.set_timeout(int(self.timeout_var.get()))
        except ValueError:
            pass
        self.sniffer.set_mode(self.mode_var.get())
        self.sniffer.show_hex = self.show_hex_var.get()
        self.sniffer.show_ascii = self.show_ascii_var.get()
        
        # Show/hide RFLink controls
        self.update_mode_visibility()

    def update_mode_visibility(self) -> None:
        """Show/hide controls based on mode."""
        is_rflink = self.mode_var.get() == RS485Sniffer.MODE_RFLINK
        
        if is_rflink:
            self.rflink_frame.pack(fill="x", padx=5, pady=2, after=self.frame_frame)
            self.device_frame.pack(fill="both", expand=True, padx=5, pady=5)
        else:
            self.rflink_frame.pack_forget()
            self.device_frame.pack_forget()

    def build_gui(self) -> None:
        # Main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # === TAB 1: Main Sniffer ===
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text="Sniffer")
        
        # Main container with paned window
        main_container = ttk.PanedWindow(main_tab, orient="horizontal")
        main_container.pack(fill="both", expand=True)
        
        left_panel = ttk.Frame(main_container)
        main_container.add(left_panel, weight=3)
        
        right_panel = ttk.Frame(main_container)
        main_container.add(right_panel, weight=1)
        
        # === LEFT PANEL ===
        
        # Connection Frame
        conn_frame = ttk.LabelFrame(left_panel, text="Verbindung")
        conn_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, padx=2)
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_combo = ttk.Combobox(conn_frame, textvariable=self.port_var, 
                                        values=ports, width=12)
        if ports:
            self.port_combo.current(0)
        self.port_combo.grid(row=0, column=1, padx=2)
        
        ttk.Button(conn_frame, text="↻", width=3, 
                   command=self.refresh_ports).grid(row=0, column=2, padx=2)
        
        ttk.Label(conn_frame, text="Baud:").grid(row=0, column=3, padx=2)
        ttk.Combobox(conn_frame, textvariable=self.baud_var,
                     values=RS485Sniffer.BAUD_RATES, width=10).grid(row=0, column=4, padx=2)
        
        ttk.Label(conn_frame, text="Parity:").grid(row=0, column=5, padx=2)
        ttk.Combobox(conn_frame, textvariable=self.parity_var,
                     values=list(self.parity_map.keys()), width=6,
                     state="readonly").grid(row=0, column=6, padx=2)
        
        ttk.Label(conn_frame, text="Stop:").grid(row=0, column=7, padx=2)
        ttk.Combobox(conn_frame, textvariable=self.stopbits_var,
                     values=["1", "1.5", "2"], width=4,
                     state="readonly").grid(row=0, column=8, padx=2)

        # Framing Frame
        self.frame_frame = ttk.LabelFrame(left_panel, text="Frame-Erkennung")
        self.frame_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(self.frame_frame, text="Modus:").grid(row=0, column=0, padx=5)
        modes = [
            (RS485Sniffer.MODE_RFLINK, "RFLink"),
            (RS485Sniffer.MODE_DELIMITER, "Delimiter"),
            (RS485Sniffer.MODE_TIMEOUT, "Timeout"),
            (RS485Sniffer.MODE_BOTH, "Beides"),
            (RS485Sniffer.MODE_RAW, "RAW"),
        ]
        for i, (value, text) in enumerate(modes):
            ttk.Radiobutton(self.frame_frame, text=text, variable=self.mode_var, 
                           value=value, command=self.apply_settings
                           ).grid(row=0, column=i+1, padx=5)
        
        ttk.Label(self.frame_frame, text="Delimiter:").grid(row=0, column=7, padx=(20, 2))
        ttk.Entry(self.frame_frame, textvariable=self.delimiter_var, width=10).grid(row=0, column=8, padx=2)
        
        ttk.Label(self.frame_frame, text="Timeout:").grid(row=0, column=9, padx=(10, 2))
        ttk.Entry(self.frame_frame, textvariable=self.timeout_var, width=5).grid(row=0, column=10, padx=2)
        
        ttk.Button(self.frame_frame, text="Apply", 
                   command=self.apply_settings).grid(row=0, column=11, padx=10)

        # === RFLink Control Frame ===
        self.rflink_frame = ttk.LabelFrame(left_panel, text="RFLink Steuerung")
        
        # Row 1: Debug toggles
        debug_frame = ttk.Frame(self.rflink_frame)
        debug_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(debug_frame, text="Debug Modi:", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        
        self.rfdebug_btn = ttk.Checkbutton(debug_frame, text="RFDEBUG", 
                                            variable=self.rfdebug_var,
                                            command=self.sniffer.toggle_rfdebug)
        self.rfdebug_btn.pack(side="left", padx=10)
        
        self.rfudebug_btn = ttk.Checkbutton(debug_frame, text="RFUDEBUG",
                                             variable=self.rfudebug_var,
                                             command=self.sniffer.toggle_rfudebug)
        self.rfudebug_btn.pack(side="left", padx=10)
        
        self.qrfdebug_btn = ttk.Checkbutton(debug_frame, text="QRFDEBUG",
                                             variable=self.qrfdebug_var,
                                             command=self.sniffer.toggle_qrfdebug)
        self.qrfdebug_btn.pack(side="left", padx=10)
        
        # Row 2: Quick commands
        cmd_frame = ttk.Frame(self.rflink_frame)
        cmd_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(cmd_frame, text="Befehle:", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        
        ttk.Button(cmd_frame, text="PING", width=8,
                   command=lambda: self.sniffer.send_rflink_command("PING")).pack(side="left", padx=5)
        
        ttk.Button(cmd_frame, text="VERSION", width=10,
                   command=lambda: self.sniffer.send_rflink_command("VERSION")).pack(side="left", padx=5)
        
        ttk.Button(cmd_frame, text="REBOOT", width=8,
                   command=self.confirm_reboot).pack(side="left", padx=5)
        
        ttk.Separator(cmd_frame, orient="vertical").pack(side="left", padx=10, fill="y")
        
        ttk.Button(cmd_frame, text="RTS Show", width=10,
                   command=lambda: self.sniffer.send_rflink_command("RTSSHOW")).pack(side="left", padx=5)
        
        ttk.Button(cmd_frame, text="RTS Clean", width=10,
                   command=lambda: self.sniffer.send_rflink_command("RTSCLEAN")).pack(side="left", padx=5)
        
        # Row 3: Custom command
        custom_frame = ttk.Frame(self.rflink_frame)
        custom_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Label(custom_frame, text="Custom:", font=("Arial", 9, "bold")).pack(side="left", padx=5)
        
        self.custom_cmd_var = tk.StringVar()
        ttk.Entry(custom_frame, textvariable=self.custom_cmd_var, width=50).pack(side="left", padx=5)
        
        ttk.Button(custom_frame, text="Send", 
                   command=lambda: self.sniffer.send_rflink_command(self.custom_cmd_var.get())
                  ).pack(side="left", padx=5)

        # Display Options
        disp_frame = ttk.LabelFrame(left_panel, text="Anzeige")
        disp_frame.pack(fill="x", padx=5, pady=2)
        
        ttk.Checkbutton(disp_frame, text="Hex", variable=self.show_hex_var,
                        command=self.apply_settings).pack(side="left", padx=10)
        ttk.Checkbutton(disp_frame, text="ASCII", variable=self.show_ascii_var,
                        command=self.apply_settings).pack(side="left", padx=10)
        ttk.Checkbutton(disp_frame, text="Autoscroll", 
                        variable=self.autoscroll_var).pack(side="left", padx=10)

        # Text Display
        text_frame = ttk.Frame(left_panel)
        text_frame.pack(fill="both", expand=True, padx=5, pady=2)
        
        scrollbar_y = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x = ttk.Scrollbar(text_frame, orient="horizontal")
        scrollbar_x.pack(side="bottom", fill="x")
        
        self.text = tk.Text(text_frame, wrap="none", font=("Consolas", 9),
                            yscrollcommand=scrollbar_y.set,
                            xscrollcommand=scrollbar_x.set)
        self.text.pack(fill="both", expand=True)
        scrollbar_y.config(command=self.text.yview)
        scrollbar_x.config(command=self.text.xview)
        
        # Tags for coloring
        self.text.tag_configure("tx", foreground="blue")
        self.text.tag_configure("error", foreground="red")
        self.text.tag_configure("info", foreground="gray")
        self.text.tag_configure("rflink_rx", foreground="darkgreen")
        self.text.tag_configure("rflink_tx", foreground="darkblue")
        self.text.tag_configure("debug", foreground="purple")
        self.text.tag_configure("weather", foreground="teal")
        self.text.tag_configure("switch", foreground="orange")

        # Status Bar
        self.status_var = tk.StringVar(value="Bereit")
        ttk.Label(left_panel, textvariable=self.status_var, 
                  relief="sunken", anchor="w").pack(fill="x", padx=5)

        # Control Buttons
        btn_frame = ttk.Frame(left_panel)
        btn_frame.pack(fill="x", padx=5, pady=5)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ Start", 
                                     command=self.sniffer.start, width=10)
        self.start_btn.pack(side="left", padx=2)
        
        self.stop_btn = ttk.Button(btn_frame, text="■ Stop", 
                                    command=self.sniffer.stop, width=10, state="disabled")
        self.stop_btn.pack(side="left", padx=2)
        
        ttk.Button(btn_frame, text="Clear", width=8,
                   command=self.clear_text).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Log speichern", width=12,
                   command=self.sniffer.open_logfile).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Stats Reset", width=10,
                   command=self.reset_stats).pack(side="left", padx=2)

        # Send Frame
        send_frame = ttk.LabelFrame(left_panel, text="Senden (RFLink: Text / Sonst: Hex)")
        send_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Entry(send_frame, textvariable=self.send_var, width=60,
                  font=("Consolas", 10)).pack(side="left", padx=5, pady=5)
        ttk.Button(send_frame, text="SEND", 
                   command=self.sniffer.send_data).pack(side="left", padx=5)

        # === RIGHT PANEL (STATISTICS) ===
        
        stats_frame = ttk.LabelFrame(right_panel, text="Busauslastung & Statistik")
        stats_frame.pack(fill="x", padx=5, pady=5)
        
        # Live Load Display
        load_frame = ttk.Frame(stats_frame)
        load_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(load_frame, text="Auslastung:", font=("Arial", 10, "bold")).pack(anchor="w")
        
        self.load_label = ttk.Label(load_frame, text="0.0%", 
                                     font=("Arial", 20, "bold"), foreground="green")
        self.load_label.pack(pady=5)
        
        self.load_progress = ttk.Progressbar(load_frame, mode="determinate", 
                                             length=180, maximum=100)
        self.load_progress.pack(fill="x", pady=5)
        
        # Current rates
        rates_frame = ttk.LabelFrame(stats_frame, text="Aktuell (1s)")
        rates_frame.pack(fill="x", padx=10, pady=5)
        
        self.bytes_sec_label = ttk.Label(rates_frame, text="Bytes/s: 0")
        self.bytes_sec_label.pack(anchor="w", padx=5)
        
        self.bits_sec_label = ttk.Label(rates_frame, text="Bits/s: 0")
        self.bits_sec_label.pack(anchor="w", padx=5)
        
        # Total statistics
        total_frame = ttk.LabelFrame(stats_frame, text="Gesamt")
        total_frame.pack(fill="x", padx=10, pady=5)
        
        self.total_bytes_label = ttk.Label(total_frame, text="Bytes: 0")
        self.total_bytes_label.pack(anchor="w", padx=5)
        
        self.total_frames_label = ttk.Label(total_frame, text="Frames: 0")
        self.total_frames_label.pack(anchor="w", padx=5)
        
        self.runtime_label = ttk.Label(total_frame, text="Laufzeit: 0:00:00")
        self.runtime_label.pack(anchor="w", padx=5)
        
        # RFLink Device count
        self.device_count_label = ttk.Label(total_frame, text="Geräte: 0")
        self.device_count_label.pack(anchor="w", padx=5)
        
        # === DEVICE FRAME (shown in RFLink mode) ===
        self.device_frame = ttk.LabelFrame(right_panel, text="Erkannte Geräte")
        
        # Device treeview
        columns = ("Protocol", "ID", "Switch", "Last Value", "Count")
        self.device_tree = ttk.Treeview(self.device_frame, columns=columns, 
                                        show="headings", height=15)
        
        for col in columns:
            self.device_tree.heading(col, text=col)
            self.device_tree.column(col, width=80)
        
        self.device_tree.column("Last Value", width=150)
        
        device_scroll = ttk.Scrollbar(self.device_frame, orient="vertical",
                                       command=self.device_tree.yview)
        self.device_tree.configure(yscrollcommand=device_scroll.set)
        
        self.device_tree.pack(side="left", fill="both", expand=True)
        device_scroll.pack(side="right", fill="y")

        # === TAB 2: Plugins ===
        plugin_tab = ttk.Frame(self.notebook)
        self.notebook.add(plugin_tab, text="Plugins")
        
        # Plugin list
        plugin_list_frame = ttk.LabelFrame(plugin_tab, text="Aktive Plugins")
        plugin_list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.plugin_tree = ttk.Treeview(plugin_list_frame, 
                                        columns=("Name", "Version", "Description", "Enabled"),
                                        show="headings", height=10)
        
        self.plugin_tree.heading("Name", text="Name")
        self.plugin_tree.heading("Version", text="Version")
        self.plugin_tree.heading("Description", text="Beschreibung")
        self.plugin_tree.heading("Enabled", text="Aktiv")
        
        self.plugin_tree.column("Name", width=150)
        self.plugin_tree.column("Version", width=80)
        self.plugin_tree.column("Description", width=400)
        self.plugin_tree.column("Enabled", width=60)
        
        self.plugin_tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Populate plugin list
        self.update_plugin_list()
        
        # Plugin info
        info_frame = ttk.LabelFrame(plugin_tab, text="Plugin Info")
        info_frame.pack(fill="x", padx=10, pady=10)
        
        info_text = """
Das Plugin-System ermöglicht die Erweiterung des Sniffers.

Verfügbare Plugin-Typen:
• Weather Sensors - Verarbeitet Wetterdaten (Temperatur, Luftfeuchtigkeit, Wind, Regen)
• Switches & Remotes - Verarbeitet Schalter- und Fernbedienungssignale
• Debug Output - Verarbeitet RFDEBUG/RFUDEBUG Ausgaben

Eigene Plugins können durch Ableitung von PluginBase erstellt werden.
        """
        ttk.Label(info_frame, text=info_text, justify="left").pack(padx=10, pady=10)

        # === TAB 3: Protocol Reference ===
        ref_tab = ttk.Frame(self.notebook)
        self.notebook.add(ref_tab, text="Protokoll-Referenz")
        
        ref_text = tk.Text(ref_tab, wrap="word", font=("Consolas", 9))
        ref_scroll = ttk.Scrollbar(ref_tab, orient="vertical", command=ref_text.yview)
        ref_text.configure(yscrollcommand=ref_scroll.set)
        
        ref_text.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        ref_scroll.pack(side="right", fill="y")
        
        protocol_ref = """
=== RFLink Protokoll-Referenz ===

EMPFANG (von RFLink):
  20;SEQ;PROTOCOL;FIELD=VALUE;...
  
  Beispiele:
    20;03;Cresta;ID=8301;TEMP=00c3;HUM=50;BAT=OK;
    20;06;NewKaku;ID=008440e6;SWITCH=a;CMD=OFF;

SENDEN (an RFLink):
  10;PROTOCOL;ID;SWITCH;CMD;
  
  Beispiele:
    10;NewKaku;0cac142;3;ON;
    10;Kaku;00004d;1;OFF;

STEUERKOMMANDOS:
  10;PING;           → Antwort: 20;99;PONG;
  10;VERSION;        → Antwort: 20;99;RFLink Gateway...;
  10;REBOOT;         → Neustart des Gateways
  10;RFDEBUG=ON/OFF; → Debug-Modus für erkannte Pakete
  10;RFUDEBUG=ON/OFF;→ Debug für unerkannte Pakete
  10;QRFDEBUG=ON/OFF;→ Schneller Debug (Hex-Zeiten x30)
  10;RTSSHOW;        → Rolling-Code-Tabelle anzeigen
  10;RTSCLEAN;       → Rolling-Code-Tabelle löschen

DATENFELDER:
  ID        → Geräte-ID (Hex)
  SWITCH    → Schalter/Button
  CMD       → Befehl (ON/OFF/ALLON/ALLOFF)
  TEMP      → Temperatur (Hex, /10 für °C)
  HUM       → Luftfeuchtigkeit (%)
  BARO      → Luftdruck (Hex)
  RAIN      → Regen (Hex, /10 für mm)
  WINSP     → Windgeschwindigkeit (Hex, /10 km/h)
  WINDIR    → Windrichtung (0-15)
  BAT       → Batteriestatus (OK/LOW)
  
TEMPERATUR-DEKODIERUNG:
  Positiv: 0x00CF = 207 → 20.7°C
  Negativ: 0x80DC = High-Bit gesetzt → -(0xDC) → -22.0°C

WINDRICHTUNG:
  0=N, 1=NNE, 2=NE, 3=ENE, 4=E, 5=ESE, 6=SE, 7=SSE,
  8=S, 9=SSW, 10=SW, 11=WSW, 12=W, 13=WNW, 14=NW, 15=NNW
"""
        ref_text.insert("1.0", protocol_ref)
        ref_text.config(state="disabled")
        
        # Initial mode visibility
        self.update_mode_visibility()

    def confirm_reboot(self) -> None:
        """Confirm before sending REBOOT command."""
        if messagebox.askyesno("Bestätigung", "RFLink Gateway wirklich neu starten?"):
            self.sniffer.send_rflink_command("REBOOT")

    def update_plugin_list(self) -> None:
        """Update the plugin list display."""
        for item in self.plugin_tree.get_children():
            self.plugin_tree.delete(item)
        
        for name, plugin in self.sniffer.plugins.items():
            self.plugin_tree.insert("", "end", values=(
                plugin.name,
                plugin.version,
                plugin.description,
                "✓" if plugin.enabled else "✗"
            ))

    def update_device_tree(self) -> None:
        """Update the device tree display."""
        # Clear existing
        for item in self.device_tree.get_children():
            self.device_tree.delete(item)
        
        # Add devices
        for key, device in self.sniffer.rflink_devices.items():
            # Format last value
            last_val = ""
            if "TEMP" in device.values:
                temp = device.values["TEMP"]
                if temp & 0x8000:
                    temp = -(temp & 0x7FFF)
                last_val += f"T:{temp/10:.1f}°C "
            if "HUM" in device.values:
                last_val += f"H:{device.values['HUM']}% "
            if "CMD" in device.values:
                last_val += f"CMD:{device.values['CMD']} "
            if "BAT" in device.values:
                last_val += f"[{device.values['BAT']}]"
            
            self.device_tree.insert("", "end", values=(
                device.protocol,
                f"0x{int(device.device_id):X}" if device.device_id.isdigit() else device.device_id,
                device.switch or "-",
                last_val.strip() or device.last_cmd,
                device.message_count
            ))

    def reset_stats(self) -> None:
        if self.sniffer.stats:
            self.sniffer.stats.reset()
            self.queue_msg("Statistiken zurückgesetzt")
        self.sniffer.rflink_devices.clear()
        self.update_device_tree()

    def clear_text(self) -> None:
        self.text.delete("1.0", tk.END)

    def update_statistics_display(self) -> None:
        if not self.sniffer.stats:
            return
        
        stats = self.sniffer.stats
        
        load = stats.current_load
        self.load_label.config(text=f"{load:.1f}%")
        self.load_progress['value'] = min(load, 100)
        
        if load < 50:
            color = "green"
        elif load < 80:
            color = "orange"
        else:
            color = "red"
        self.load_label.config(foreground=color)
        
        self.bytes_sec_label.config(text=f"Bytes/s: {stats.current_bytes_per_sec}")
        bits_per_sec = stats.current_bytes_per_sec * stats.bits_per_byte
        self.bits_sec_label.config(text=f"Bits/s: {bits_per_sec:.0f}")
        
        self.total_bytes_label.config(text=f"Bytes: {stats.total_bytes:,}")
        self.total_frames_label.config(text=f"Frames: {stats.total_frames:,}")
        
        runtime = stats.get_runtime()
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)
        self.runtime_label.config(text=f"Laufzeit: {hours}:{minutes:02d}:{seconds:02d}")
        
        self.device_count_label.config(text=f"Geräte: {len(self.sniffer.rflink_devices)}")

    def poll_queues(self) -> None:
        updated = False
        
        # RX Queue
        try:
            for _ in range(100):
                line = self.sniffer.rx_queue.get_nowait()
                tag = None
                if "[ERROR]" in line:
                    tag = "error"
                elif "◀" in line:
                    tag = "rflink_rx"
                    if "DEBUG" in line:
                        tag = "debug"
                    elif any(w in line for w in ["TEMP", "HUM", "RAIN", "WIND"]):
                        tag = "weather"
                    elif "CMD" in line:
                        tag = "switch"
                elif "▶" in line:
                    tag = "rflink_tx"
                self.text.insert(tk.END, line + "\n", tag)
                updated = True
        except queue.Empty:
            pass
        
        # Message Queue
        try:
            for _ in range(20):
                msg = self.msg_queue.get_nowait()
                tag = "info"
                if "TX" in msg or "▶" in msg:
                    tag = "tx"
                elif "ERROR" in msg or "Fehler" in msg:
                    tag = "error"
                self.text.insert(tk.END, msg + "\n", tag)
                self.status_var.set(msg)
                updated = True
        except queue.Empty:
            pass
        
        if updated and self.autoscroll_var.get():
            self.text.see(tk.END)
        
        # Update statistics and device display
        if self.sniffer.running:
            if self.sniffer.stats:
                self.update_statistics_display()
            if self.mode_var.get() == RS485Sniffer.MODE_RFLINK:
                self.update_device_tree()
        
        self.root.after(100, self.poll_queues)

    def set_running(self, running: bool) -> None:
        self.start_btn.config(state="disabled" if running else "normal")
        self.stop_btn.config(state="normal" if running else "disabled")
        self.status_var.set("Läuft..." if running else "Gestoppt")

    def run(self) -> None:
        self.root.mainloop()


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    print(f"RS485 Sniffer v{__version__} - RFLink Edition")
    print("Features: RFLink Protocol, Plugin System, Device Tracking")
    print("-" * 70)
    SnifferGUI().run()
