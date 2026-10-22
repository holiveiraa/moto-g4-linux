FROM debian:stretch@sha256:c5c5200ff1e9c73ffbf188b4a67eb1c91531b644856b4aefe86a58d2f0cb05be

# Historical compiler inside an isolated build container, not on the host.
RUN printf 'deb http://archive.debian.org/debian stretch main\ndeb http://archive.debian.org/debian-security stretch/updates main\n' > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends \
       gcc-aarch64-linux-gnu gcc g++ make bc bison flex patch python \
       libssl-dev libelf-dev device-tree-compiler cpio gzip xz-utils \
       ca-certificates curl file git \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends libfdt-dev python3 libc6-dev-arm64-cross \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
