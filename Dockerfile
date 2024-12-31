# Use debian:11-slim as the base image
FROM debian:11-slim

# Set the URL for downloading the Nezha Agent
ENV AGENT_URL=https://github.com/nezhahq/agent/releases/latest/download/nezha-agent_linux_amd64.zip

# Install required packages
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    unzip \
    ca-certificates --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Download and install the latest version of the Nezha Agent for amd64
RUN wget $AGENT_URL -O nezha-agent.zip && \
    unzip nezha-agent.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/nezha-agent && \
    rm -f nezha-agent.zip

# Copy the setup-config script from your context into the image
COPY setup-config.sh /usr/local/bin/setup-config.sh

# Ensure the script is executable and run it to setup the config.yml
RUN chmod +x /usr/local/bin/setup-config.sh && /usr/local/bin/setup-config.sh

# Set the working directory
WORKDIR /usr/local/bin/nezha

# Start the Nezha Agent using the generated config file
CMD ["./nezha-agent", "-c", "config.yml"]