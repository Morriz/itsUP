"""
OpenSnitch integration for Container Security Monitor.

This module handles all OpenSnitch database queries and monitoring.
OpenSnitch is optional - the monitor can run standalone without it.
"""

import re
import sqlite3
import time
from typing import Callable, Optional

from instrukt_ai_logging import get_logger

from .constants import OPENSNITCH_DB

logger = get_logger(f"itsup.{__name__}")


class OpenSnitchIntegration:
    """Handles OpenSnitch database integration for threat detection."""

    def __init__(self) -> None:
        """Initialize OpenSnitch integration."""
        self.db_path = OPENSNITCH_DB

    @staticmethod
    def extract_ip_from_arpa(query: str) -> Optional[str]:
        """
        Extract IP address from ARPA reverse DNS query.

        Args:
            query: ARPA query string (e.g., "4.3.2.1.in-addr.arpa")

        Returns:
            IP address or None if not a valid ARPA query
        """
        pattern = r"(\d+)\.(\d+)\.(\d+)\.(\d+)\.in-addr\.arpa"
        match = re.match(pattern, query)
        if match:
            return f"{match.group(4)}.{match.group(3)}.{match.group(2)}.{match.group(1)}"
        return None

    def get_recent_block_count(self, hours: int = 24) -> int:
        """
        Get count of blocks from 0-deny-arpa-53 rule in last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Count of blocks
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT COUNT(*) FROM connections
                WHERE rule = '0-deny-arpa-53'
                AND time > strftime('%s', 'now', ?)
            """,
                (f"-{hours} hours",),
            )
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"⚠ Could not query OpenSnitch database: {e}")
            return 0

    def get_all_arpa_blocks(self) -> list[tuple[str, str]]:
        """
        Get all historical ARPA blocks from OpenSnitch.

        Returns:
            List of (dst_host, dst_ip) tuples
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT dst_host, dst_ip
                FROM connections
                WHERE rule = '0-deny-arpa-53'
            """)
            rows = cursor.fetchall()
            conn.close()
            return rows
        except Exception as e:
            logger.error(f"⚠ Error querying OpenSnitch blocks: {e}")
            return []

    def monitor_blocks(
        self,
        on_block_callback: Callable[[str, str, str], None],
        poll_interval: float = 0.5,
    ) -> None:
        """
        Continuously monitor OpenSnitch for new blocks.

        Args:
            on_block_callback: Called for each new block (timestamp, dst_host, ip)
            poll_interval: Seconds between polls
        """
        logger.info("📋 Monitoring OpenSnitch blocks...")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(time) FROM connections WHERE rule = '0-deny-arpa-53'")
            last_time = cursor.fetchone()[0] or ""
            conn.close()
            if last_time:
                logger.info(f"📋 OpenSnitch: Resuming from last block at {last_time}")
            else:
                logger.info(
                    "📋 OpenSnitch: No previous blocks found - will monitor for new ones (rule: 0-deny-arpa-53)"
                )
        except Exception as e:
            logger.error(f"⚠️  OpenSnitch: Could not read database - {e}")
            last_time = ""

        poll_count = 0

        while True:
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT time, dst_host
                    FROM connections
                    WHERE time > ?
                    AND rule = '0-deny-arpa-53'
                    ORDER BY time ASC
                """,
                    (last_time,),
                )

                rows = cursor.fetchall()
                conn.close()

                for timestamp, dst_host in rows:
                    last_time = timestamp

                    # ONLY process ARPA reverse DNS blocks
                    if dst_host and "in-addr.arpa" in dst_host:
                        ip = self.extract_ip_from_arpa(dst_host)
                        if ip:
                            on_block_callback(timestamp, dst_host, ip)

                poll_count += 1

            except Exception as e:
                logger.error(f"❌ OpenSnitch error: {e}")

            time.sleep(poll_interval)
