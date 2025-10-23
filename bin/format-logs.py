#!/usr/bin/env python3
"""Format Traefik JSON access logs into human-readable flat format."""

import json
import sys
from datetime import datetime


def format_size(bytes_val):
    """Convert bytes to human-readable format."""
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f}KB"
    else:
        return f"{bytes_val / (1024 * 1024):.1f}MB"


def format_duration(ns):
    """Convert nanoseconds to milliseconds."""
    return ns / 1_000_000


def format_log_line(log_entry):
    """Format a single JSON log entry into flat format.

    Format: TIME LEVEL CLIENT_IP "METHOD HOST/PATH" → SERVICE STATUS DURATION (origin:X +overhead) SIZE [retries:N] [TLS:X]
    """
    try:
        # Extract fields
        timestamp = log_entry.get("time", log_entry.get("StartUTC", ""))
        level = log_entry.get("level", "INFO").upper()

        # Client IP (strip port)
        client_addr = log_entry.get("ClientAddr", "-")
        client_ip = client_addr.split(":")[0] if client_addr != "-" else "-"

        # Request
        method = log_entry.get("RequestMethod", "-")
        host = log_entry.get("RequestHost", "-")
        path = log_entry.get("RequestPath", "-")
        request = f"{method} {host}{path}"

        # Service name (strip @docker suffix for brevity)
        service = log_entry.get("ServiceName", "-")
        service = service.replace("@docker", "")

        # Status
        status = log_entry.get("DownstreamStatus", log_entry.get("OriginStatus", "-"))

        # Durations (convert ns to ms)
        duration_ns = log_entry.get("Duration", 0)
        origin_ns = log_entry.get("OriginDuration", 0)
        overhead_ns = log_entry.get("Overhead", 0)

        duration_ms = format_duration(duration_ns)
        origin_ms = format_duration(origin_ns)
        overhead_ms = format_duration(overhead_ns)

        # Size
        size_bytes = log_entry.get("DownstreamContentSize", log_entry.get("OriginContentSize", 0))
        size = format_size(size_bytes)

        # Optional fields
        retries = log_entry.get("RetryAttempts", 0)
        tls_version = log_entry.get("TLSVersion", "")

        # Build output
        parts = [
            timestamp,
            level,
            client_ip,
            f'"{request}"',
            "→",
            service,
            str(status),
            f"{duration_ms:.1f}ms",
        ]

        # Add origin/overhead breakdown if meaningful
        if overhead_ms > 0.5:  # Show overhead if >0.5ms
            parts.append(f"(origin:{origin_ms:.1f}ms +{overhead_ms:.1f}ms)")

        parts.append(size)

        # Add retries if any
        if retries > 0:
            parts.append(f"retries:{retries}")

        # Add TLS version if present
        if tls_version:
            parts.append(f"TLS:{tls_version.replace('TLS_', '').replace('_', '.')}")

        return " ".join(parts)

    except Exception as e:
        # If parsing fails, return original line
        return f"[PARSE ERROR: {e}] {json.dumps(log_entry)}"


def main():
    """Read JSON log lines from stdin and output formatted versions."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            log_entry = json.loads(line)
            print(format_log_line(log_entry), flush=True)
        except json.JSONDecodeError:
            # Not JSON, pass through as-is (might be non-Traefik logs)
            print(line, flush=True)


if __name__ == "__main__":
    main()
