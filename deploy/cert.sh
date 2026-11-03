#!/bin/sh
# Get or renew the Let's Encrypt certificate for sphero.clegg.dev (or $SPHERO_HOST)
# with lego, using a DNS-01 check through GoDaddy, then make sure the name still
# points at this computer. `sphero-dev serve` reloads the certificate by itself.
#
#   deploy/cert.sh              # first time, and whenever (renews only when due)
#
# Needs `lego` on PATH (https://go-acme.github.io/lego/). Optional:
# SPHERO_CERT_EMAIL for Let's Encrypt's expiry notices.
# Files: ~/.local/share/sphero-dev/lego/certificates/$SPHERO_HOST.{crt,key}
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
HOST=${SPHERO_HOST:-sphero.clegg.dev}
DIR=${SPHERO_CERT_DIR:-$HOME/.local/share/sphero-dev/lego}
export SPHERO_HOST="$HOST" EXEC_PATH="$HERE/godaddy-dns.sh"
export EXEC_PROPAGATION_TIMEOUT=600 EXEC_POLLING_INTERVAL=15

"$HERE/godaddy-dns.sh" point-here

set -- --accept-tos --dns exec --dns.resolvers 1.1.1.1:53 --domains "$HOST" --path "$DIR"
[ -n "${SPHERO_CERT_EMAIL:-}" ] && set -- "$@" --email "$SPHERO_CERT_EMAIL"

if [ -f "$DIR/certificates/$HOST.crt" ]; then
  lego "$@" renew --days 30
else
  mkdir -p "$DIR"
  chmod 700 "$DIR"
  lego "$@" run
fi
echo "Certificate: $DIR/certificates/$HOST.crt"
echo "Key:         $DIR/certificates/$HOST.key"
