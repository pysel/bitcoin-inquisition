#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/home/bitcoin/.bitcoin}"
CONF_FILE="${DATA_DIR}/bitcoin.conf"
CHAIN="${CHAIN:-regtest}"
RPC_USER="${RPC_USER:-student}"
RPC_PASSWORD="${RPC_PASSWORD:-student}"

# If running as root (first boot, fresh volume, or bind-mount), reconcile
# ownership of the data dir and re-exec ourselves as the bitcoin user.
if [[ "$(id -u)" == "0" ]]; then
    mkdir -p "${DATA_DIR}"
    chown -R bitcoin:bitcoin "${DATA_DIR}"
    exec gosu bitcoin "$0" "$@"
fi

if [[ ! -f "${CONF_FILE}" ]]; then
    cat > "${CONF_FILE}" <<EOF
chain=${CHAIN}
server=1
txindex=1
fallbackfee=0.0002
rpcuser=${RPC_USER}
rpcpassword=${RPC_PASSWORD}

[${CHAIN}]
rpcbind=0.0.0.0
rpcallowip=0.0.0.0/0
bind=0.0.0.0
EOF
fi

if [[ "$1" == "bitcoin-cli" || "$1" == "bitcoind" ]]; then
    exec "$@" -datadir="${DATA_DIR}"
fi

exec "$@"
