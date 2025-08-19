# Fast single-stage frontend build with security hardening
FROM node:18-alpine

# Install curl for health checks, bash for entrypoint, and set environment
RUN apk add --no-cache curl bash

# Set environment defaults
ENV NODE_ENV=development
ENV ARCHON_UI_HOST=0.0.0.0
ENV ARCHON_UI_PORT=5173

WORKDIR /app

# Copy package files first for better layer caching
COPY package*.json ./

# Install dependencies and clean cache in one layer
RUN npm ci && npm cache clean --force

# Copy source code
COPY . .

# Create health endpoint file
RUN mkdir -p public && \
    echo '<!DOCTYPE html><html><head><title>Health</title><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="X-Content-Type-Options" content="nosniff"><meta http-equiv="X-Frame-Options" content="DENY"></head><body><h1>OK</h1><p>Frontend Service is Healthy</p></body></html>' > public/health.html

# Create non-root user for security (works standalone + Kubernetes can override)
RUN addgroup -g 1001 archon && \
    adduser -D -s /bin/sh -u 1001 -G archon archon && \
    chown -R archon:archon /app

USER 1001

# Expose the port configured in package.json (3737) but allow override
EXPOSE ${ARCHON_UI_PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${ARCHON_UI_PORT}/health.html || exit 1

# Start Vite dev server with configurable host/port but fallback to package.json defaults
CMD ["sh", "-c", "npm run dev -- --host ${ARCHON_UI_HOST} --port ${ARCHON_UI_PORT}"]
