# syntax=docker/dockerfile:1.6
# Multi-stage Dockerfile for bitcoin-inquisition (Bitcoin Core 29.x + covenants BIPs).
# Default chain is regtest, which has CTV / OP_CAT / APO / CSFS / ConsensusCleanup /
# InternalKey active from genesis (see src/binana/*.json -> scriptverify: true).

# ---------- builder ----------
FROM debian:bookworm-slim AS builder

ARG JOBS=4
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        pkgconf \
        python3 \
        libevent-dev \
        libboost-dev \
        libsqlite3-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY . /src

RUN cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_GUI=OFF \
        -DBUILD_TESTS=OFF \
        -DBUILD_BENCH=OFF \
        -DBUILD_FUZZ_BINARY=OFF \
        -DWITH_ZMQ=OFF \
        -DENABLE_WALLET=ON \
 && cmake --build build -j ${JOBS} --target bitcoind bitcoin-cli \
 && strip build/bin/bitcoind build/bin/bitcoin-cli \
 && install -Dm755 build/bin/bitcoind   /out/usr/local/bin/bitcoind \
 && install -Dm755 build/bin/bitcoin-cli /out/usr/local/bin/bitcoin-cli

# ---------- runtime ----------
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/bitcoin

RUN apt-get update && apt-get install -y --no-install-recommends \
        libevent-core-2.1-7 \
        libevent-extra-2.1-7 \
        libevent-pthreads-2.1-7 \
        libsqlite3-0 \
        ca-certificates \
        gosu \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --home-dir /home/bitcoin --create-home --shell /usr/sbin/nologin bitcoin \
    && install -d -o bitcoin -g bitcoin -m 0750 /home/bitcoin/.bitcoin

COPY --from=builder /out/usr/local/bin/bitcoind   /usr/local/bin/bitcoind
COPY --from=builder /out/usr/local/bin/bitcoin-cli /usr/local/bin/bitcoin-cli
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /home/bitcoin
VOLUME ["/home/bitcoin/.bitcoin"]

# regtest: 18443 RPC, 18444 P2P
EXPOSE 18443 18444

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["bitcoind"]
