#!.venv/bin/python
"""
Analyze blacklisted IPs, group by network ranges, perform reverse DNS lookups,
whois lookups, and generate a threat actor report. Only analyzes NEW IPs not in existing report.
"""
import socket
import csv
import signal
import sys
import os
import requests
from collections import defaultdict
from ipaddress import IPv4Address, IPv4Network, ip_address
from pathlib import Path
from ipwhois import IPWhois
from ipwhois.exceptions import IPDefinedError
from dotenv import load_dotenv

# Ensure dotenv variables take precedence over existing environment variables
load_dotenv(override=True)

BLACKLIST_FILE = "/etc/opensnitchd/blacklists/blacklist-outbound-ips.txt"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
OUTPUT_CSV = REPORTS_DIR / "potential_threat_actors.csv"
ABUSEIPDB_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")

# Global flag for cancellation
_cancelled = False


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully"""
    global _cancelled
    _cancelled = True
    print("\n\n❌ Analysis cancelled by user")
    sys.exit(130)


def read_blacklist():
    """Read IPs from blacklist file"""
    ips = []
    try:
        with open(BLACKLIST_FILE, "r") as f:
            for line in f:
                ip = line.strip()
                if ip and not ip.startswith("#"):
                    ips.append(IPv4Address(ip))
    except FileNotFoundError:
        print(f"❌ Blacklist file not found: {BLACKLIST_FILE}")
        exit(1)
    return sorted(ips)


def read_existing_report():
    """Read existing report and return set of already-analyzed IPs"""
    analyzed_ips = set()
    existing_rows = []

    if not OUTPUT_CSV.exists():
        return analyzed_ips, existing_rows

    try:
        with open(OUTPUT_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_rows.append(row)
                network_str = row["network"]

                # Parse network field to extract IPs
                # Format: "1.2.3.4" or "1.2.3.0/24 (5 IPs)"
                if " (" in network_str:
                    network_str = network_str.split(" (")[0]

                try:
                    if "/" in network_str:
                        # It's a network range
                        network = IPv4Network(network_str)
                        analyzed_ips.update(network.hosts())
                        analyzed_ips.add(network.network_address)
                        analyzed_ips.add(network.broadcast_address)
                    else:
                        # Single IP
                        analyzed_ips.add(IPv4Address(network_str))
                except ValueError:
                    pass

        print(f"📋 Found existing report with {len(analyzed_ips)} already-analyzed IPs")
    except Exception as e:
        print(f"⚠️  Could not read existing report: {e}")

    return analyzed_ips, existing_rows


def group_by_ranges(ips):
    """
    Group IPs by network ranges. If multiple IPs from same /24 or /16, group them.
    Returns: {network: [ips]} where network is IPv4Network or single IP
    """
    # Count IPs per /24 and /16
    net24_count = defaultdict(list)
    net16_count = defaultdict(list)

    for ip in ips:
        net24 = IPv4Network(f"{ip}/24", strict=False)
        net16 = IPv4Network(f"{ip}/16", strict=False)
        net24_count[net24].append(ip)
        net16_count[net16].append(ip)

    # Determine grouping strategy
    grouped = {}
    processed = set()

    # First pass: group /16 ranges with 3+ IPs
    for net16, ip_list in net16_count.items():
        if len(ip_list) >= 3:
            grouped[net16] = ip_list
            processed.update(ip_list)

    # Second pass: group /24 ranges with 2+ IPs (not already in /16)
    for net24, ip_list in net24_count.items():
        if len(ip_list) >= 2:
            remaining = [ip for ip in ip_list if ip not in processed]
            if len(remaining) >= 2:
                grouped[net24] = remaining
                processed.update(remaining)

    # Third pass: individual IPs
    for ip in ips:
        if ip not in processed:
            grouped[ip] = [ip]

    return grouped


def reverse_dns_lookup(ip):
    """Perform reverse DNS lookup for IP with timeout"""
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(3)  # 3 second timeout
        hostname = socket.gethostbyaddr(str(ip))[0]
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout):
        return None
    except KeyboardInterrupt:
        raise  # Allow cancellation
    finally:
        socket.setdefaulttimeout(old_timeout)


def whois_lookup(ip):
    """
    Perform whois lookup for IP and extract relevant information.
    Returns: dict with org_name, country, emails, phone, description
    """
    try:
        obj = IPWhois(str(ip), timeout=5)
        result = obj.lookup_rdap(depth=1)

        # Extract organization/owner info (handle both dict and string returns)
        network = result.get('network', {})
        if isinstance(network, dict):
            org_name = network.get('name', '') or result.get('asn_description', '')
            country = network.get('country', '')
        else:
            org_name = str(network) if network else result.get('asn_description', '')
            country = ''

        # Extract contact emails (try multiple locations)
        emails = set()

        # Check top-level entities
        for entity in result.get('entities', []):
            if isinstance(entity, str):
                emails.add(entity)

        # Check objects
        for obj_item in result.get('objects', {}).values():
            contact = obj_item.get('contact', {})
            # Try email field
            if contact.get('email'):
                email = contact['email']
                if isinstance(email, list):
                    emails.update([e.get('value', str(e)) if isinstance(e, dict) else str(e)
                                   for e in email if e])
                elif isinstance(email, (str, int)):
                    emails.add(str(email))

            # Try roles with email
            if 'roles' in contact:
                for role in contact.get('roles', []):
                    if '@' in str(role):
                        emails.add(str(role))

        # Extract phone numbers
        phones = set()
        for obj_item in result.get('objects', {}).values():
            contact = obj_item.get('contact', {})
            if contact.get('phone'):
                phone = contact['phone']
                if isinstance(phone, list):
                    phones.update([p.get('value', str(p)) if isinstance(p, dict) else str(p)
                                   for p in phone if p])
                elif isinstance(phone, (str, int)):
                    phones.add(str(phone))

        # Get network description/remarks
        description = ''
        network_data = result.get('network', {})
        if isinstance(network_data, dict):
            remarks = network_data.get('remarks', [])
            if remarks and isinstance(remarks, list) and len(remarks) > 0:
                first_remark = remarks[0]
                if isinstance(first_remark, dict):
                    description = first_remark.get('description', '')
                elif isinstance(first_remark, str):
                    description = first_remark

        return {
            'org_name': org_name,
            'country': country,
            'emails': ', '.join(sorted(emails)) if emails else '',
            'phone': ', '.join(sorted(phones)) if phones else '',
            'description': description if isinstance(description, str) else ''
        }
    except IPDefinedError:
        return {
            'org_name': 'Private/Reserved IP',
            'country': '',
            'emails': '',
            'phone': '',
            'description': ''
        }
    except KeyboardInterrupt:
        raise  # Re-raise to allow cancellation
    except Exception as e:
        # Log more detailed error for debugging
        error_msg = str(e)[:80]
        return {
            'org_name': f'Whois error: {error_msg}',
            'country': '',
            'emails': '',
            'phone': '',
            'description': ''
        }


def abuseipdb_lookup(ip):
    """
    Query AbuseIPDB for threat intelligence on IP.
    Returns: dict with abuse_score, total_reports, usage_type, is_tor, last_reported
    """
    if not ABUSEIPDB_API_KEY:
        return {
            'abuse_score': '',
            'total_reports': '',
            'usage_type': '',
            'is_tor': '',
            'last_reported': ''
        }

    try:
        url = 'https://api.abuseipdb.com/api/v2/check'
        headers = {
            'Accept': 'application/json',
            'Key': ABUSEIPDB_API_KEY
        }
        params = {
            'ipAddress': str(ip),
            'maxAgeInDays': '90',
            'verbose': ''
        }

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        data = response.json().get('data', {})

        return {
            'abuse_score': data.get('abuseConfidenceScore', 0),
            'total_reports': data.get('totalReports', 0),
            'usage_type': data.get('usageType', ''),
            'is_tor': 'Yes' if data.get('isTor', False) else '',
            'last_reported': data.get('lastReportedAt', '')
        }
    except KeyboardInterrupt:
        raise
    except Exception as e:
        return {
            'abuse_score': '',
            'total_reports': '',
            'usage_type': f'AbuseIPDB error: {str(e)[:40]}',
            'is_tor': '',
            'last_reported': ''
        }


def analyze_group(network, ip_list):
    """
    Analyze a group of IPs (range or single).
    Returns: dict with network_str, domain, ip_count, whois info
    """
    # Do reverse DNS on first IP and a sample
    sample_size = min(3, len(ip_list))
    sample_ips = ip_list[:sample_size]

    domains = []
    for ip in sample_ips:
        domain = reverse_dns_lookup(ip)
        if domain:
            domains.append(domain)

    # Determine network string
    if isinstance(network, IPv4Network):
        network_str = str(network)
    else:
        network_str = str(network)

    # Determine domain string
    if not domains:
        domain_str = "(no reverse DNS)"
    elif len(set(domains)) == 1:
        # All domains are the same
        domain_str = domains[0]
    else:
        # Multiple different domains
        domain_str = ", ".join(set(domains))

    # Do whois lookup on first IP
    whois_info = whois_lookup(ip_list[0])

    # Do AbuseIPDB lookup on first IP
    abuse_info = abuseipdb_lookup(ip_list[0])

    return {
        'network_str': network_str,
        'domain': domain_str,
        'ip_count': len(ip_list),
        'org_name': whois_info['org_name'],
        'country': whois_info['country'],
        'emails': whois_info['emails'],
        'phone': whois_info['phone'],
        'description': whois_info['description'],
        'abuse_score': abuse_info['abuse_score'],
        'total_reports': abuse_info['total_reports'],
        'usage_type': abuse_info['usage_type'],
        'is_tor': abuse_info['is_tor'],
        'last_reported': abuse_info['last_reported']
    }


def generate_report(grouped, existing_rows):
    """Generate CSV report with new entries only"""
    REPORTS_DIR.mkdir(exist_ok=True)

    new_rows = []

    if grouped:
        print(f"🔍 Analyzing {sum(len(ips) for ips in grouped.values())} NEW IPs in {len(grouped)} groups...")

        for network, ip_list in sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True):
            # Check if cancelled
            if _cancelled:
                print("\n⚠️  Saving partial results before exit...")
                break

            analysis = analyze_group(network, ip_list)

            # Format output
            if isinstance(network, IPv4Network):
                ip_display = f"{analysis['network_str']} ({analysis['ip_count']} IPs)"
            else:
                ip_display = str(network)

            new_rows.append({
                "network": ip_display,
                "domain": analysis['domain'],
                "org_name": analysis['org_name'],
                "country": analysis['country'],
                "abuse_score": analysis['abuse_score'],
                "total_reports": analysis['total_reports'],
                "usage_type": analysis['usage_type'],
                "is_tor": analysis['is_tor'],
                "last_reported": analysis['last_reported'],
                "emails": analysis['emails'],
                "phone": analysis['phone'],
                "description": analysis['description'],
                "ip_count": analysis['ip_count']
            })

            # Print progress
            abuse_display = f"[Abuse: {analysis['abuse_score']}%]" if analysis['abuse_score'] else ""
            if isinstance(network, IPv4Network):
                print(f"  📦 {analysis['network_str']}: {analysis['ip_count']} IPs → {analysis['domain']} ({analysis['org_name']}) {abuse_display}")
            else:
                print(f"  🔍 {network}: {analysis['domain']} ({analysis['org_name']}) {abuse_display}")
    else:
        print("✅ No new IPs to analyze")

    # Combine existing and new rows, ensuring all rows have all fields
    fieldnames = ["network", "domain", "org_name", "country", "abuse_score", "total_reports",
                  "usage_type", "is_tor", "last_reported", "emails", "phone", "description", "ip_count"]

    # Pad existing rows with empty values for new fields if they don't exist
    for row in existing_rows:
        for field in fieldnames:
            if field not in row:
                row[field] = ''

    all_rows = existing_rows + new_rows

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ Report updated: {OUTPUT_CSV}")
    print(f"📊 New entries: {len(new_rows)}")
    print(f"📊 Total entries: {len(all_rows)}")
    if new_rows:
        print(f"📊 New IPs analyzed: {sum(row['ip_count'] for row in new_rows)}")


def main():
    # Register signal handler for Ctrl-C
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("🔍 Analyzing blacklisted IPs for threat actor patterns...\n")

    # Read existing report
    analyzed_ips, existing_rows = read_existing_report()

    # Read blacklist
    all_ips = read_blacklist()
    print(f"📋 Found {len(all_ips)} total blacklisted IPs")

    # Filter out already-analyzed IPs
    new_ips = [ip for ip in all_ips if ip not in analyzed_ips]
    print(f"🆕 Found {len(new_ips)} NEW IPs to analyze\n")

    if not new_ips:
        print("✅ All IPs already analyzed. Report is up to date.")
        return

    # Group by ranges
    grouped = group_by_ranges(new_ips)
    print(f"📦 Grouped into {len(grouped)} entries (ranges + individual IPs)\n")

    # Generate report
    generate_report(grouped, existing_rows)


if __name__ == "__main__":
    main()
