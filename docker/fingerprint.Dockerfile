# Reuse the pinned bring-up toolchain image; this adds only a 32-bit compiler
# for the handset's original vendor ABI, not an Android runtime or container.
FROM moto-g4-kernel:gcc6
RUN apt-get -o Acquire::Check-Valid-Until=false update \
    && apt-get install -y --no-install-recommends gcc-arm-linux-gnueabihf \
    && rm -rf /var/lib/apt/lists/*
