# Use multi-platform build to avoid QEMU simulation issues
FROM --platform=$TARGETPLATFORM debian:11-slim

# Set non-interactive mode to prevent prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Define architecture-based variables
ARG TARGETARCH
ARG VERSION
ENV AGENT_URL=https://github.com/nezhahq/agent/releases/download/${VERSION}/nezha-agent_linux_${TARGETARCH}.zip

# Update system and upgrade packages to prevent libc-bin issues
RUN apt-get update && apt-get upgrade -y

# Install necessary dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    unzip \
    uuid-runtime \
    ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Create the working directory for Nezha Agent
RUN mkdir -p /usr/local/bin/nezha && cd /usr/local/bin/nezha

# Download and extract the Nezha Agent binary
RUN wget $AGENT_URL -O nezha-agent.zip && \
    unzip nezha-agent.zip && \
    chmod +x nezha-agent && \
    rm -f nezha-agent.zip

# Copy the setup configuration script
COPY setup-config.sh /usr/local/bin/nezha/setup-config.sh
RUN chmod +x /usr/local/bin/nezha/setup-config.sh

# Set working directory
WORKDIR /usr/local/bin/nezha

# Set default command to execute the setup script and start the agent
CMD ["./setup-config.sh", "&&", "./nezha-agent", "-c", "config.yml"]
