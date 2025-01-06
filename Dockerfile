# Use debian:11-slim as the base image
FROM debian:11-slim

# Set the URL for downloading the Nezha Agent
ARG TARGETARCH
ENV AGENT_URL=https://github.com/nezhahq/agent/releases/latest/download/nezha-agent_linux_${TARGETARCH}.zip

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    unzip \
    ca-certificates --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Create a directory and install the Nezha Agent in one layer
RUN mkdir -p /usr/local/bin/nezha && \
    wget $AGENT_URL -O nezha-agent.zip && \
    unzip nezha-agent.zip -d /usr/local/bin/nezha && \
    chmod +x /usr/local/bin/nezha/nezha-agent && \
    rm -f nezha-agent.zip

# Copy the setup-config script from your context into the image
COPY setup-config.sh /usr/local/bin/nezha/setup-config.sh

# Ensure the script and agent are executable
RUN chmod +x /usr/local/bin/nezha/setup-config.sh

# Set the working directory
WORKDIR /usr/local/bin/nezha

# Set default command to first run the setup script and then start Nezha Agent
CMD ["/bin/sh", "-c", "./setup-config.sh && ./nezha-agent -c config.yml"]
