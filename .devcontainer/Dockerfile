FROM verilator/verilator:latest

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        python3-pip \
        python3-dev \
        build-essential \
        pkg-config \
        git \
        curl \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install uv globally so both VS Code and terminals can use it
RUN curl -LsSf https://astral.sh/uv/install.sh | sh -s -- --install-dir /usr/local/bin && \
    uv --version
