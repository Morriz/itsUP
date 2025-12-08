#!/usr/bin/env bash
set -euo pipefail
LOG=/var/log/pi-healthcheck.log
STAMP=/run/pi-healthcheck.fail
NOW=$(date -Is)
HOUR=$(date +%H%M)  # HHMM for maintenance window checks

# thresholds
MIN_MEM_KB=500000      # ~500MB available
MAX_LOAD1=8.0
MAX_CONN_PCT=80        # percent of nf_conntrack_max
MAX_ROOT_PCT=90        # percent disk use on /
EMERG_MEM_KB=100000    # ~100MB for daytime break-glass
EMERG_SWAP_KB=262144   # 256MB swap use
EMERG_LOAD1=12.0
EMERG_CONN_PCT=95
STRIKES_FILE=/run/pi-healthcheck.strikes

ok=1
reasons=()

mem_avail_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
load1=$(awk '{print $1}' /proc/loadavg)
conn=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo 0)
conn_max=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || echo 1)
root_pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')

# tests
if (( mem_avail_kb < MIN_MEM_KB )); then ok=0; reasons+=("low_mem:${mem_avail_kb}kb"); fi
# high load if load1 > MAX_LOAD1
if awk -v l="$load1" -v max="$MAX_LOAD1" 'BEGIN{exit(l>max?0:1)}'; then ok=0; reasons+=("high_load:${load1}"); fi
if (( conn * 100 / conn_max > MAX_CONN_PCT )); then ok=0; reasons+=("conntrack:${conn}/${conn_max}"); fi
if (( root_pct > MAX_ROOT_PCT )); then ok=0; reasons+=("disk:${root_pct}%"); fi
if ! docker ps >/dev/null 2>&1; then ok=0; reasons+=("docker_down"); fi

log() { echo "$NOW $*" | tee -a "$LOG"; }

if (( ok )); then
  rm -f "$STAMP"
  log "OK mem=${mem_avail_kb}kb load1=${load1} conn=${conn}/${conn_max} disk=${root_pct}%"
  exit 0
fi

# Only take actions during maintenance window (02:30–03:30 local); otherwise log-only.
if ! [[ "$HOUR" > "0230" && "$HOUR" < "0330" ]]; then
  # Daytime: only act on break-glass thresholds with strike counting.
  swap_used_kb=$(awk '/SwapTotal/ {t=$2} /SwapFree/ {f=$2} END {print (t-f)}' /proc/meminfo)
  emerg=1
  # Emergencies: really low RAM with swap in use, or conntrack near max, or docker unresponsive + very high load
  if (( mem_avail_kb < EMERG_MEM_KB && swap_used_kb > EMERG_SWAP_KB )); then emerg=0; reasons+=("emerg_low_mem:${mem_avail_kb}kb_swap:${swap_used_kb}kb"); fi
  if (( conn * 100 / conn_max > EMERG_CONN_PCT )); then emerg=0; reasons+=("emerg_conntrack:${conn}/${conn_max}"); fi
  if ! docker ps >/dev/null 2>&1 && awk -v l="$load1" -v max="$EMERG_LOAD1" 'BEGIN{exit(l>max?0:1)}'; then emerg=0; reasons+=("emerg_docker_down_highload:${load1}"); fi

  if (( emerg )); then
    log "INFO (day log-only) ${reasons[*]} mem=${mem_avail_kb}kb load1=${load1} conn=${conn}/${conn_max} swap_used=${swap_used_kb}kb disk=${root_pct}%"
    rm -f "$STRIKES_FILE"
    exit 0
  fi

  strikes=0
  if [[ -f "$STRIKES_FILE" ]]; then strikes=$(cat "$STRIKES_FILE" 2>/dev/null || echo 0); fi
  strikes=$((strikes + 1))
  echo "$strikes" > "$STRIKES_FILE"

  if (( strikes < 3 )); then
    log "WARN (day strike ${strikes}/3) ${reasons[*]} mem=${mem_avail_kb}kb load1=${load1} conn=${conn}/${conn_max} swap_used=${swap_used_kb}kb disk=${root_pct}%"
    exit 0
  fi

  # On 3rd consecutive strike: restart docker + stacks; next strike would reboot (still daytime).
  log "WARN (day strike ${strikes}/3) ${reasons[*]} -> restarting docker + itsup stacks"
  systemctl restart docker || log "ERROR failed to restart docker"
  su -l morriz -c 'cd /home/morriz/srv && source env.sh && itsup dns up && itsup proxy up' || log "ERROR itsup bringup failed"
  exit 0
fi

# first strike: restart docker and stacks, set stamp
if [[ ! -f "$STAMP" ]]; then
  echo "$NOW ${reasons[*]}" > "$STAMP"
  log "WARN ${reasons[*]} -> restarting docker + itsup stacks"
  systemctl restart docker || log "ERROR failed to restart docker"
  # bring stacks back
  su -l morriz -c 'cd /home/morriz/srv && source env.sh && itsup dns up && itsup proxy up' || log "ERROR itsup bringup failed"
  exit 0
fi

# second strike: reboot
log "CRIT ${reasons[*]} -> rebooting host"
rm -f "$STAMP"
systemctl reboot
