#!/bin/sh
# GoDaddy DNS helper for sphero.clegg.dev (or $SPHERO_HOST).
#
#   godaddy-dns.sh present FQDN VALUE   add the ACME TXT record   (lego's exec DNS provider)
#   godaddy-dns.sh cleanup FQDN VALUE   remove it
#   godaddy-dns.sh point-here           point the A record at this computer's LAN address
#
# The name points at a home-network address on purpose: only devices at home can
# reach it, and the certificate comes from a DNS-01 check, which doesn't need the
# server to be reachable from the internet.
#
# Reads GD_PAT from $GD_ENV (default ~/.config/godaddy/api.env), the same token
# minecraft.clegg.dev's DDNS uses (scopes domains.domain:read, domains.dns:update).
set -eu

if [ -z "${GD_PAT:-}" ]; then
  # shellcheck disable=SC1090
  . "${GD_ENV:-$HOME/.config/godaddy/api.env}"
fi
: "${GD_PAT:?set GD_PAT or GD_ENV}"
HOST=${SPHERO_HOST:-sphero.clegg.dev}
DOMAIN=${GD_DOMAIN:-clegg.dev}
API="https://api.godaddy.com/v1/domains/$DOMAIN/records"

# The token goes to curl on stdin so it never shows up in the process list.
api() {
  printf 'header = "Authorization: Bearer %s"\n' "$GD_PAT" |
    curl -fsS --max-time 20 -K - -H 'Content-Type: application/json' "$@"
}

# "_acme-challenge.sphero.clegg.dev." -> "_acme-challenge.sphero"
relative() {
  name=${1%.}
  echo "${name%."$DOMAIN"}"
}

case ${1:-} in
  present)
    api -X PUT --data "[{\"data\":\"$3\",\"ttl\":600}]" "$API/TXT/$(relative "$2")" >/dev/null
    ;;
  cleanup)
    api -X DELETE "$API/TXT/$(relative "$2")" >/dev/null || true
    ;;
  point-here)
    ip=$(ip -4 route get 192.0.2.1 | sed -n 's/.* src \([0-9.]*\).*/\1/p')
    [ -n "$ip" ] || { echo "couldn't find this computer's LAN address" >&2; exit 1; }
    name=$(relative "$HOST")
    current=$(api "$API/A/$name")
    case $current in *"\"$ip\""*) exit 0 ;; esac
    api -X PUT --data "[{\"data\":\"$ip\",\"ttl\":600}]" "$API/A/$name" >/dev/null
    echo "$HOST -> $ip (was $current)"
    ;;
  *)
    echo "usage: $0 present|cleanup FQDN VALUE | point-here" >&2
    exit 2
    ;;
esac
