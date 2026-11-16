# XamKids Profile: online demo image (web platform, agent and the three MCP servers in one container).
FROM node:22-bookworm-slim AS node

FROM python:3.12-slim

# Node.js (Filesystem MCP server) and Deno (Run Python MCP server)
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

# Voice for the learner space (Linux text-to-speech)
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the MCP servers' dependencies at build time, so the first analysis does not wait for them
RUN mkdir -p /tmp/warm && (timeout 60 npx -y @modelcontextprotocol/server-filesystem /tmp/warm < /dev/null || true) \
 && (timeout 180 python -m mcp_run_python example || true)

COPY . .
RUN mkdir -p data uploads

ENV HOST=0.0.0.0 \
    XAMKIDS_LANG=en \
    PYTHONUNBUFFERED=1

# The hosting service provides PORT. The demo class is created at first start.
CMD ["python", "app.py"]
