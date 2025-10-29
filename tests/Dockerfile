FROM python:3.11-slim

# Install system dependencies (build tools needed for Python packages like netifaces)
RUN apt-get update && apt-get install -y \
    git \
    make \
    wget \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy entire project
WORKDIR /app
COPY . .

# Run our standard installation (installs sops, sops-diff, age, Python deps including test deps)
# Sets CONTAINER env var to skip Docker check
ENV CONTAINER=true
RUN make install

# Configure git for tests
RUN git config --global user.email "test@test.com" && \
    git config --global user.name "Test User"

# Run functional tests
CMD [".venv/bin/pytest", "tests/functional/", "-v", "--tb=short"]
