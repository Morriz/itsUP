"""
IP list management for Container Security Monitor.

This module provides the IPList class for managing blacklist and whitelist files.
Each instance manages one IP list (one file, one in-memory set).
"""
import os
import threading
from typing import Callable, Optional


class IPList:
    """Manages a single IP list (one file, one in-memory set)."""

    def __init__(
        self,
        filepath: str,
        log_callback: Callable[[str, str], None],
        file_lock: threading.Lock,
        header_comment: str = "# IP list - one IP per line"
    ):
        """
        Initialize IP list manager.

        Args:
            filepath: Path to the list file
            log_callback: Function to call for logging (signature: log(message, level="INFO"))
            file_lock: Lock for file write operations
            header_comment: Comment to write at the top of new files
        """
        self.filepath = filepath
        self.log = log_callback
        self.file_lock = file_lock
        self.header_comment = header_comment
        self.ips: set[str] = set()
        self.mtime: float = 0
        self.lock = threading.Lock()

    def load(self, skip_if_empty: bool = False) -> None:
        """
        Load IPs from file into memory.

        Args:
            skip_if_empty: If True, skip loading entirely (for --skip-sync mode)
        """
        if skip_if_empty:
            self.log(f"⏭️  Skipping {self._get_list_name()} load (--skip-sync) - memory-only mode", "INFO")
            return

        try:
            stat = os.stat(self.filepath)
            self.mtime = stat.st_mtime

            new_ips = self._read_file()

            with self.lock:
                self.ips = new_ips

            if new_ips:
                self.log(f"📋 Loaded {len(new_ips)} IPs from {self._get_list_name()}", "INFO")

        except FileNotFoundError:
            # Create empty file
            try:
                with open(self.filepath, "w") as f:
                    f.write(f"{self.header_comment}\n")
                self.log(f"✅ Created {self._get_list_name()} file: {self.filepath}", "INFO")
            except Exception as e:
                self.log(f"❌ Could not create {self._get_list_name()}: {e}", "INFO")
        except Exception as e:
            self.log(f"⚠️ Error loading {self._get_list_name()}: {e}", "INFO")

    def add(self, ip: str, persist: bool = True) -> bool:
        """
        Add IP to in-memory set, optionally write to file.

        Args:
            ip: IP address to add
            persist: Whether to persist to file (False for --skip-sync mode)

        Returns:
            True if IP was added (wasn't already present), False if already exists
        """
        # Check in-memory first (fast check)
        with self.lock:
            if ip in self.ips:
                return False  # Already tracked

        if persist:
            # Persist to file
            with self.file_lock:
                # Read current file contents
                existing_ips = self._read_file()

                if ip in existing_ips:
                    return False  # Already in file

                # Append to file atomically
                with open(self.filepath, "a") as f:
                    f.write(f"{ip}\n")

        # Update in-memory set
        with self.lock:
            self.ips.add(ip)

        return True

    def contains(self, ip: str) -> bool:
        """
        Check if IP is in list.

        Args:
            ip: IP address to check

        Returns:
            True if IP is in the list
        """
        with self.lock:
            return ip in self.ips

    def has_changed(self) -> bool:
        """
        Check if file mtime changed on disk.

        Returns:
            True if file was modified since last load
        """
        try:
            stat = os.stat(self.filepath)
            return stat.st_mtime > self.mtime
        except Exception:
            return False

    def reload(self) -> set[str]:
        """
        Reload from disk, return old set for delta detection.

        Returns:
            Set of IPs before reload (for detecting additions/removals)
        """
        with self.lock:
            old = self.ips.copy()

        self.load()

        return old

    def remove_ips(self, ips_to_remove: set[str]) -> int:
        """
        Remove IPs from both file and memory.

        Args:
            ips_to_remove: Set of IPs to remove

        Returns:
            Number of IPs actually removed
        """
        with self.file_lock:
            current_ips = self._read_file()
            updated_ips = current_ips - ips_to_remove

            if len(updated_ips) < len(current_ips):
                # Rewrite file without removed IPs
                with open(self.filepath, "w") as f:
                    f.write(f"{self.header_comment}\n")
                    for ip in sorted(updated_ips):
                        f.write(f"{ip}\n")

                removed_count = len(current_ips) - len(updated_ips)

                # Update in-memory set
                with self.lock:
                    self.ips = updated_ips

                return removed_count

        return 0

    def get_all(self) -> set[str]:
        """
        Get copy of all IPs in the list.

        Returns:
            Set of all IPs
        """
        with self.lock:
            return self.ips.copy()

    def _read_file(self) -> set[str]:
        """
        Read and parse file, return set of IPs.

        Returns:
            Set of IPs from file (excluding comments and empty lines)
        """
        try:
            with open(self.filepath, "r") as f:
                result = set()
                for line in f:
                    # Extract IP from line (ignore comments after IP)
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        ip_part = stripped.split("#")[0].strip()
                        if ip_part:
                            result.add(ip_part)
                return result
        except FileNotFoundError:
            return set()

    def _get_list_name(self) -> str:
        """Get human-readable name for this list based on filepath."""
        if "blacklist" in self.filepath.lower():
            return "blacklist"
        elif "whitelist" in self.filepath.lower():
            return "whitelist"
        else:
            return os.path.basename(self.filepath)
