"""
Amethyst System Monitor — Proactive System Awareness
======================================================
Monitors CPU, RAM, disk usage, and battery in a background thread.
Triggers alerts via callbacks when thresholds are exceeded.
Gives the AI real-time system awareness.
"""

import asyncio
import logging
import platform
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger("amethyst.sysmon")


@dataclass
class SystemSnapshot:
    """A point-in-time snapshot of system health."""
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    disk_percent: float = 0.0
    disk_free_gb: float = 0.0
    battery_percent: Optional[float] = None
    battery_plugged: Optional[bool] = None
    os_name: str = ""
    hostname: str = ""

    def as_context_string(self) -> str:
        """Format for injection into AI prompts."""
        lines = [
            f"OS: {self.os_name}",
            f"Host: {self.hostname}",
            f"CPU Usage: {self.cpu_percent:.0f}%",
            f"RAM: {self.ram_used_gb:.1f} / {self.ram_total_gb:.1f} GB ({self.ram_percent:.0f}%)",
            f"Disk: {self.disk_free_gb:.1f} GB free ({self.disk_percent:.0f}% used)",
        ]
        if self.battery_percent is not None:
            status = "Charging" if self.battery_plugged else "On Battery"
            lines.append(f"Battery: {self.battery_percent:.0f}% ({status})")
        return "\n".join(lines)

    @property
    def has_critical_alert(self) -> Optional[str]:
        """Returns alert message if any metric is critical, else None."""
        alerts = []
        if self.cpu_percent > 95:
            alerts.append(f"🔴 CPU at {self.cpu_percent:.0f}%")
        if self.ram_percent > 92:
            alerts.append(f"🔴 RAM at {self.ram_percent:.0f}% ({self.ram_used_gb:.1f}/{self.ram_total_gb:.1f} GB)")
        if self.disk_percent > 95:
            alerts.append(f"🔴 Disk {self.disk_percent:.0f}% full (only {self.disk_free_gb:.1f} GB free)")
        if self.battery_percent is not None and self.battery_percent < 10 and not self.battery_plugged:
            alerts.append(f"🔴 Battery critically low: {self.battery_percent:.0f}%")
        return " | ".join(alerts) if alerts else None


class SystemMonitor:
    """
    Background system monitor that periodically checks system health
    and triggers callbacks on critical thresholds.
    """

    def __init__(self, interval: float = 30.0,
                 on_alert: Optional[Callable[[str], None]] = None):
        self._interval = interval
        self._on_alert = on_alert
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._last_snapshot: Optional[SystemSnapshot] = None
        self._last_alert_time = 0.0
        self._alert_cooldown = 120.0  # Don't spam alerts within 2 min
        self._psutil_ok = False

    def start(self):
        """Start the background monitoring thread."""
        if self._active:
            return
        self._active = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="sys-monitor")
        self._thread.start()
        log.info("System monitor started.")
        self._write_connection_log()

    def _write_connection_log(self):
        """Logs connection event to the pen drive for auditing."""
        import os
        from datetime import datetime
        if "AMETHYST_HOME" in os.environ:
            base_dir = os.environ["AMETHYST_HOME"]
        else:
            base_dir = os.path.join(os.path.expanduser("~"), ".amethyst")
            
        log_dir = os.path.join(base_dir, "system_logs")
        os.makedirs(log_dir, exist_ok=True)
        
        try:
            snap = self.get_snapshot()
            if not snap:
                return
                
            today = datetime.now().strftime("%Y-%m-%d")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file = os.path.join(log_dir, f"{today}_connections.txt")
            
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n--- ATTACHED TO HOST: {timestamp} ---\n")
                f.write(f"Hostname: {snap.hostname}\n")
                f.write(f"OS: {snap.os_name}\n")
                f.write(f"Initial Status: CPU {snap.cpu_percent:.0f}%, RAM {snap.ram_used_gb:.1f}GB / {snap.ram_total_gb:.1f}GB\n")
        except Exception as e:
            log.error(f"Failed to write connection log: {e}")

    def stop(self):
        self._active = False
        log.info("System monitor stopped.")

    def _monitor_loop(self):
        """Main monitoring loop — runs in background thread."""
        # Check if psutil is available
        try:
            import psutil
            self._psutil_ok = True
        except ImportError:
            log.warning("psutil not installed. System monitoring disabled. Run: pip install psutil")
            self._active = False
            return

        while self._active:
            try:
                snapshot = self._take_snapshot()
                self._last_snapshot = snapshot

                # Check for critical alerts
                alert = snapshot.has_critical_alert
                if alert and self._on_alert:
                    now = time.time()
                    if now - self._last_alert_time > self._alert_cooldown:
                        self._on_alert(alert)
                        self._last_alert_time = now
                        log.warning(f"System alert triggered: {alert}")

            except Exception as e:
                log.error(f"Monitor error: {e}")

            time.sleep(self._interval)

    def _take_snapshot(self) -> SystemSnapshot:
        """Capture current system metrics."""
        import psutil

        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        snapshot = SystemSnapshot(
            cpu_percent=cpu,
            ram_percent=mem.percent,
            ram_used_gb=mem.used / (1024 ** 3),
            ram_total_gb=mem.total / (1024 ** 3),
            disk_percent=disk.percent,
            disk_free_gb=disk.free / (1024 ** 3),
            os_name=f"{platform.system()} {platform.release()}",
            hostname=platform.node(),
        )

        # Battery (laptops only)
        try:
            battery = psutil.sensors_battery()
            if battery:
                snapshot.battery_percent = battery.percent
                snapshot.battery_plugged = battery.power_plugged
        except Exception:
            pass

        return snapshot

    def get_snapshot(self) -> Optional[SystemSnapshot]:
        """Get the latest system snapshot (non-blocking)."""
        if self._last_snapshot:
            return self._last_snapshot
        # If no snapshot yet, take one now
        if self._psutil_ok:
            try:
                self._last_snapshot = self._take_snapshot()
                return self._last_snapshot
            except Exception:
                pass
        return None

    @property
    def is_active(self) -> bool:
        return self._active
