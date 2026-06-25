#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
configure=0

usage() {
  cat <<'EOF'
Usage: install-dingtalk-alerting.sh [--configure]

Options:
  --configure  Prompt for DingTalk webhook and optional signature secret.

Environment overrides:
  DINGTALK_WEBHOOK  DingTalk robot webhook URL.
  DINGTALK_SECRET   Optional DingTalk robot signature secret.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --configure)
      configure=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
  shift
done

install -d -m 0755 /usr/local/sbin
install -m 0755 "${repo_root}/monitoring/scripts/ctm-dingtalk-relay.py" \
  /usr/local/sbin/ctm-dingtalk-relay.py

install -d -m 0750 /etc/ctm-monitoring
if [ ! -f /etc/ctm-monitoring/dingtalk-relay.env ]; then
  install -m 0600 "${repo_root}/monitoring/examples/dingtalk-relay.env.example" \
    /etc/ctm-monitoring/dingtalk-relay.env
fi
grep -q '^DINGTALK_WEBHOOK=' /etc/ctm-monitoring/dingtalk-relay.env || \
  printf '\nDINGTALK_WEBHOOK=\n' >> /etc/ctm-monitoring/dingtalk-relay.env
grep -q '^DINGTALK_SECRET=' /etc/ctm-monitoring/dingtalk-relay.env || \
  printf 'DINGTALK_SECRET=\n' >> /etc/ctm-monitoring/dingtalk-relay.env
sed -i 's#^DINGTALK_WEBHOOK=.*replace-with-token.*#DINGTALK_WEBHOOK=#' \
  /etc/ctm-monitoring/dingtalk-relay.env
chmod 0600 /etc/ctm-monitoring/dingtalk-relay.env

if [ "$configure" -eq 1 ]; then
  read -r -p "DingTalk webhook URL: " DINGTALK_WEBHOOK
  read -r -s -p "DingTalk signature secret (optional): " DINGTALK_SECRET
  printf '\n'
fi

if [ -n "${DINGTALK_WEBHOOK:-}" ] || [ -n "${DINGTALK_SECRET:-}" ]; then
  tmp_env="$(mktemp)"
  awk -F= -v webhook="${DINGTALK_WEBHOOK:-}" -v secret="${DINGTALK_SECRET:-}" '
    BEGIN { wrote_webhook = 0; wrote_secret = 0 }
    /^DINGTALK_WEBHOOK=/ {
      if (webhook != "") {
        print "DINGTALK_WEBHOOK=" webhook
        wrote_webhook = 1
        next
      }
    }
    /^DINGTALK_SECRET=/ {
      print "DINGTALK_SECRET=" secret
      wrote_secret = 1
      next
    }
    { print }
    END {
      if (webhook != "" && wrote_webhook == 0) print "DINGTALK_WEBHOOK=" webhook
      if (wrote_secret == 0) print "DINGTALK_SECRET=" secret
    }
  ' /etc/ctm-monitoring/dingtalk-relay.env > "${tmp_env}"
  install -m 0600 "${tmp_env}" /etc/ctm-monitoring/dingtalk-relay.env
  rm -f "${tmp_env}"
fi

install -m 0644 "${repo_root}/monitoring/systemd/ctm-dingtalk-relay.service" \
  /etc/systemd/system/ctm-dingtalk-relay.service

systemctl daemon-reload

cat <<'EOF'
Installed CTM DingTalk relay files.

Next:
  1. Edit /etc/ctm-monitoring/dingtalk-relay.env, or rerun with --configure.
  2. Set DINGTALK_WEBHOOK and optionally DINGTALK_SECRET.
  3. Run:
       systemctl enable --now ctm-dingtalk-relay
       systemctl status ctm-dingtalk-relay
EOF
