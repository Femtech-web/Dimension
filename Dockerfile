# Everything CI checks, from a clean machine, in one command:
#
#   docker build -t dimension . && docker run --rm dimension
#
# Ubuntu 24.04, as CI runs: Fe 26.6.0's Linux build needs its glibc (2.39).
# Built for x86-64 and arm64. Fe's native backend runs on x86-64 Linux, so there
# every check runs as in CI; on arm64 Linux, such as Docker on Apple silicon,
# the native-backend checks are skipped and reported as skipped.
FROM ubuntu:24.04

# Ubuntu 24.04's python3 is Python 3.12; Fe's native backend links with cc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gcc git libc6-dev make python3 \
    && rm -rf /var/lib/apt/lists/*

# Foundry at the version CI pins, checksum-verified.
ARG TARGETARCH
ARG FOUNDRY=v1.4.4
ARG FOUNDRY_SHA256_amd64=22ba110a40e4de7791b007b08284e7b038c6bd4ce141b7ac34b5accec04f71a4
ARG FOUNDRY_SHA256_arm64=f7cb873a296f08a61349b9a9114c3a0c171a1d33e4018f64ac21b7fa7c3ee9d7
RUN case "$TARGETARCH" in \
        amd64) sha256=$FOUNDRY_SHA256_amd64 ;; \
        arm64) sha256=$FOUNDRY_SHA256_arm64 ;; \
        *) echo "unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL --retry 3 -o /tmp/foundry.tar.gz \
        "https://github.com/foundry-rs/foundry/releases/download/${FOUNDRY}/foundry_${FOUNDRY}_linux_${TARGETARCH}.tar.gz" \
    && echo "${sha256}  /tmp/foundry.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/foundry.tar.gz -C /usr/local/bin forge cast anvil \
    && rm /tmp/foundry.tar.gz

WORKDIR /dimension
# The repository with its git history: `make consumer` takes Dimension from it.
COPY . .

# The pinned Fe compiler and Solidity dependencies, and the solc releases the
# reference project compiles with, so the run itself needs no network.
RUN make toolchain reference-deps && cd contracts/reference && forge build

CMD ["make", "ci"]
