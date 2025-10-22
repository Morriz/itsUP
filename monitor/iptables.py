"""
iptables management for Container Security Monitor.

This module handles all iptables operations for monitoring and blocking
container network traffic.
"""
import subprocess
from typing import Callable

from .constants import (
    IPTABLES_CHAIN,
    IPTABLES_LOG_PREFIX,
    DOCKER_NETWORK_CIDR,
)


class IptablesManager:
    """Manages iptables rules for container traffic monitoring and blocking."""

    def __init__(self, log_callback: Callable[[str, str], None]):
        """
        Initialize iptables manager.

        Args:
            log_callback: Function to call for logging (signature: log(message, level="INFO"))
        """
        self.log = log_callback
        self.rule_added = False

    def _run_command(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """
        Run iptables command.

        Args:
            cmd: Command and arguments to run
            check: Whether to raise exception on non-zero return code

        Returns:
            CompletedProcess instance
        """
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def ensure_log_rule_exists(self) -> bool:
        """
        Check and add LOG rule if needed (idempotent).

        Returns:
            True if rule exists or was added successfully
        """
        if self._check_log_rule_exists():
            self.log("✅ iptables LOG rule already exists (persistent across restarts)", "INFO")
            self.rule_added = True
            return True

        try:
            cmd = [
                "iptables",
                "-I",
                IPTABLES_CHAIN,
                "1",
                "-s",
                DOCKER_NETWORK_CIDR,
                "-p",
                "tcp",
                "-m",
                "conntrack",
                "--ctstate",
                "NEW",
                "-j",
                "LOG",
                "--log-prefix",
                IPTABLES_LOG_PREFIX,
                "--log-level",
                "4",
            ]
            self._run_command(cmd)
            self.rule_added = True
            self.log("✅ Added iptables LOG rule for NEW outbound container TCP connections", "INFO")
            return True
        except Exception as e:
            self.log(f"❌ Failed to add iptables LOG rule: {e}", "INFO")
            return False

    def _check_log_rule_exists(self) -> bool:
        """Check if the LOG rule already exists in iptables."""
        try:
            cmd = [
                "iptables",
                "-C",
                IPTABLES_CHAIN,
                "-s",
                DOCKER_NETWORK_CIDR,
                "-p",
                "tcp",
                "-m",
                "conntrack",
                "--ctstate",
                "NEW",
                "-j",
                "LOG",
                "--log-prefix",
                IPTABLES_LOG_PREFIX,
                "--log-level",
                "4",
            ]
            result = self._run_command(cmd, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def add_drop_rule(self, ip: str, log: bool = True) -> None:
        """
        Add iptables DROP rule for IP (idempotent).

        Args:
            ip: IP address to block
            log: Whether to log the action
        """
        if self.is_ip_blocked(ip):
            if log:
                self.log(f"✅ {ip} already blocked in iptables", "DEBUG")
            return

        try:
            cmd = ["iptables", "-I", IPTABLES_CHAIN, "1", "-s", DOCKER_NETWORK_CIDR, "-d", ip, "-j", "DROP"]
            self._run_command(cmd)
            if log:
                self.log(f"🚫 Blocked {ip} in iptables", "INFO")
        except Exception as e:
            self.log(f"❌ Failed to block {ip} in iptables: {e}", "INFO")

    def remove_drop_rule(self, ip: str) -> None:
        """
        Remove iptables DROP rule for IP.

        Args:
            ip: IP address to unblock
        """
        try:
            cmd = ["iptables", "-D", IPTABLES_CHAIN, "-s", DOCKER_NETWORK_CIDR, "-d", ip, "-j", "DROP"]
            self._run_command(cmd, check=False)
            self.log(f"✅ Unblocked {ip} in iptables", "INFO")
        except Exception as e:
            self.log(f"⚠️ Failed to unblock {ip} in iptables: {e}", "INFO")

    def is_ip_blocked(self, ip: str) -> bool:
        """
        Check if IP already has a DROP rule.

        Args:
            ip: IP address to check

        Returns:
            True if IP is blocked
        """
        try:
            cmd = ["iptables", "-C", IPTABLES_CHAIN, "-s", DOCKER_NETWORK_CIDR, "-d", ip, "-j", "DROP"]
            result = self._run_command(cmd, check=False)
            return result.returncode == 0
        except Exception:
            return False

    def remove_log_rule(self) -> None:
        """Remove the iptables LOG rule."""
        if not self.rule_added:
            return

        try:
            cmd = [
                "iptables",
                "-D",
                IPTABLES_CHAIN,
                "-s",
                DOCKER_NETWORK_CIDR,
                "-p",
                "tcp",
                "-m",
                "conntrack",
                "--ctstate",
                "NEW",
                "-j",
                "LOG",
                "--log-prefix",
                IPTABLES_LOG_PREFIX,
                "--log-level",
                "4",
            ]
            self._run_command(cmd, check=False)
            self.log("✅ Removed iptables LOG rule", "INFO")
        except Exception as e:
            self.log(f"⚠ Failed to remove iptables LOG rule: {e}", "INFO")

    def clear_monitor_rules(self) -> None:
        """Remove all rules added by monitor (LOG rule and all DROP rules)."""
        # Remove LOG rule
        try:
            cmd = [
                "iptables",
                "-D",
                IPTABLES_CHAIN,
                "-s",
                DOCKER_NETWORK_CIDR,
                "-p",
                "tcp",
                "-m",
                "conntrack",
                "--ctstate",
                "NEW",
                "-j",
                "LOG",
                "--log-prefix",
                IPTABLES_LOG_PREFIX,
                "--log-level",
                "4",
            ]
            self._run_command(cmd, check=False)
            print("✅ Removed LOG rule")
        except Exception as e:
            print(f"⚠ Failed to remove LOG rule: {e}")

        # List all DROP rules with source 172.0.0.0/8 and remove them
        try:
            result = self._run_command(
                ["iptables", "-L", IPTABLES_CHAIN, "-n", "--line-numbers"],
                check=False
            )

            # Parse output and find DROP rules with source DOCKER_NETWORK_CIDR
            lines = result.stdout.strip().split("\n")
            drop_rules = []

            for line in lines:
                if "DROP" in line and DOCKER_NETWORK_CIDR in line:
                    parts = line.split()
                    if parts:
                        line_num = parts[0]
                        drop_rules.append(int(line_num))

            # Remove rules in reverse order (highest line number first)
            for line_num in sorted(drop_rules, reverse=True):
                cmd = ["iptables", "-D", IPTABLES_CHAIN, str(line_num)]
                self._run_command(cmd, check=False)

            if drop_rules:
                print(f"✅ Removed {len(drop_rules)} DROP rules")
            else:
                print("ℹ️  No DROP rules found")

        except Exception as e:
            print(f"⚠ Error clearing DROP rules: {e}")
