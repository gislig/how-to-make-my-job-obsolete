# Infra agent MCP server. Build in Azure with: az acr build -r <registry> -t infra-agent-mcp:1.0.0 mcp-server
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home mcp
USER 10001
EXPOSE 8000
CMD ["obsolete-mcp"]
