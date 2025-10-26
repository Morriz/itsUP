#!/usr/bin/env python3
"""
Analyze blacklisted IPs individually, track subnet membership, perform reverse DNS lookups,
whois lookups, and generate a threat actor report. Only analyzes NEW IPs not in existing report.
"""
import socket
import csv
import signal
import sys
import os
import requests
from datetime import datetime, timezone
from collections import defaultdict
from ipaddress import IPv4Address, IPv4Network, ip_address
from ipwhois import IPWhois
from ipwhois.exceptions import IPDefinedError
from dotenv import load_dotenv

# Ensure dotenv variables take precedence over existing environment variables
load_dotenv(override=True)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLACKLIST_FILE = os.path.join(PROJECT_ROOT, "data", "blacklist", "blacklist-outbound-ips.txt")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
OUTPUT_CSV = os.path.join(REPORTS_DIR, "potential_threat_actors.csv")
ABUSEIPDB_API_KEY = os.getenv("ABUSEIPDB_API_KEY", "")

# Global flag for cancellation
_cancelled = False


def signal_handler(sig, frame):
    """Handle Ctrl-C gracefully"""
    itsup _cancelled
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
    """Read existing report and return dict of IP -> row data"""
    analyzed_ips = {}

    if not os.path.exists(OUTPUT_CSV):
        return analyzed_ips

    # Define expected fields
    expected_fields = [
        "ip", "domain", "subnet",
        "org_name", "country", "abuse_score", "total_reports",
        "usage_type", "is_tor", "last_reported",
        "emails", "phone", "description",
        "first_seen", "last_updated", "reported_to_abuseipdb"
    ]

    try:
        with open(OUTPUT_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ip_str = row.get("ip", "")
                if ip_str:
                    try:
                        # Only keep fields that are in expected_fields
                        filtered_row = {k: row.get(k, '') for k in expected_fields}
                        analyzed_ips[IPv4Address(ip_str)] = filtered_row
                    except ValueError:
                        pass

        print(f"📋 Found existing report with {len(analyzed_ips)} already-analyzed IPs")
    except Exception as e:
        print(f"⚠️  Could not read existing report: {e}")

    return analyzed_ips


def identify_subnets(ips):
    """
    Get /16 subnet for each IP.
    Returns: dict mapping each IP to its /16 subnet (only if 2+ IPs share it)
    """
    # Count IPs per /16 subnet
    net16_count = defaultdict(list)
    for ip in ips:
        net16 = IPv4Network(f"{ip}/16", strict=False)
        net16_count[net16].append(ip)

    # Build subnet mapping - only show if 2+ IPs share it
    subnet_map = {}
    for ip in ips:
        net16 = IPv4Network(f"{ip}/16", strict=False)
        subnet_map[ip] = str(net16) if len(net16_count[net16]) > 1 else ''

    return subnet_map


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


def analyze_ip(ip, subnet):
    """
    Analyze a single IP.
    Returns: dict with IP info, domain, subnet info, whois data, abuse data
    """
    # Reverse DNS lookup
    domain = reverse_dns_lookup(ip)
    domain_str = domain if domain else "(no reverse DNS)"

    # Whois lookup
    whois_info = whois_lookup(ip)

    # AbuseIPDB lookup
    abuse_info = abuseipdb_lookup(ip)

    # Get current timestamp
    timestamp = datetime.now(timezone.utc).isoformat()

    return {
        'ip': str(ip),
        'domain': domain_str,
        'subnet': subnet,
        'org_name': whois_info['org_name'],
        'country': whois_info['country'],
        'emails': whois_info['emails'],
        'phone': whois_info['phone'],
        'description': whois_info['description'],
        'abuse_score': abuse_info['abuse_score'],
        'total_reports': abuse_info['total_reports'],
        'usage_type': abuse_info['usage_type'],
        'is_tor': abuse_info['is_tor'],
        'last_reported': abuse_info['last_reported'],
        'first_seen': timestamp,
        'last_updated': timestamp,
        'reported_to_abuseipdb': ''
    }


def generate_report(ip_analyses, existing_data):
    """Generate CSV report with individual IP records"""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    if ip_analyses:
        print(f"🔍 Analyzing {len(ip_analyses)} NEW IPs...")
    elif not existing_data:
        print("✅ No IPs to report")
        return

    # Define field order
    fieldnames = [
        "ip", "domain", "subnet",
        "org_name", "country", "abuse_score", "total_reports",
        "usage_type", "is_tor", "last_reported",
        "emails", "phone", "description",
        "first_seen", "last_updated", "reported_to_abuseipdb"
    ]

    # Merge existing data with new analyses
    all_data = {}

    # Add existing data
    for ip, row in existing_data.items():
        # Update last_updated timestamp
        row_copy = row.copy()
        row_copy['last_updated'] = datetime.now(timezone.utc).isoformat()
        all_data[ip] = row_copy

    # Add new analyses
    for ip, analysis in ip_analyses.items():
        all_data[ip] = analysis
        abuse_display = f"[Abuse: {analysis['abuse_score']}%]" if analysis['abuse_score'] else ""
        subnet_display = f" ({analysis['subnet']})" if analysis['subnet'] else ""
        print(f"  🔍 {ip}{subnet_display}: {analysis['domain']} ({analysis['org_name']}) {abuse_display}")

    # Convert to list sorted by IP
    all_rows = [all_data[ip] for ip in sorted(all_data.keys(), key=lambda x: IPv4Address(str(x)))]

    # Pad rows with empty values for any missing fields
    for row in all_rows:
        for field in fieldnames:
            if field not in row:
                row[field] = ''

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n✅ Report updated: {OUTPUT_CSV}")
    print(f"📊 New IPs analyzed: {len(ip_analyses)}")
    print(f"📊 Total IPs in report: {len(all_rows)}")


def main():
    # Register signal handler for Ctrl-C
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("🔍 Analyzing blacklisted IPs individually...\n")

    # Read existing report
    existing_data = read_existing_report()

    # Read blacklist
    all_ips = read_blacklist()
    print(f"📋 Found {len(all_ips)} total blacklisted IPs")

    # Sync existing data with blacklist - remove IPs no longer blacklisted
    all_ips_set = set(all_ips)
    removed_ips = [ip for ip in existing_data.keys() if ip not in all_ips_set]
    if removed_ips:
        print(f"🗑️  Removing {len(removed_ips)} IPs no longer in blacklist")
        for ip in removed_ips:
            del existing_data[ip]

    # Filter out already-analyzed IPs
    new_ips = [ip for ip in all_ips if ip not in existing_data]
    print(f"🆕 Found {len(new_ips)} NEW IPs to analyze\n")

    # Always recalculate subnets for ALL IPs (even if no new IPs)
    subnet_info = identify_subnets(all_ips)

    # Update existing rows with new subnet info (in case membership changed)
    updated_subnets = 0
    for ip in existing_data.keys():
        old_subnet = existing_data[ip].get('subnet', '')
        new_subnet = subnet_info.get(ip, '')
        if old_subnet != new_subnet:
            updated_subnets += 1
        existing_data[ip]['subnet'] = new_subnet

    if updated_subnets > 0:
        print(f"🔄 Updated subnet info for {updated_subnets} existing IPs")

    if not new_ips:
        print("✅ All IPs already analyzed.")
        # Regenerate report if subnets changed or to update timestamps
        if existing_data:
            if updated_subnets > 0:
                print("📝 Regenerating report with updated subnet info...")
            generate_report({}, existing_data)
        return

    # Analyze new IPs
    ip_analyses = {}
    for ip in new_ips:
        # Check if cancelled
        if _cancelled:
            print("\n⚠️  Saving partial results before exit...")
            break

        analysis = analyze_ip(ip, subnet_info[ip])
        ip_analyses[ip] = analysis

    # Generate report
    generate_report(ip_analyses, existing_data)


if __name__ == "__main__":
    main()
