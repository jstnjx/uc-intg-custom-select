FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache-dir -r requirements.txt

RUN mkdir -p /config
COPY driver.json .
COPY uc_intg_custom_select ./uc_intg_custom_select

ENV UC_DISABLE_MDNS_PUBLISH="false"
ENV UC_MDNS_LOCAL_HOSTNAME=""
ENV UC_INTEGRATION_INTERFACE="0.0.0.0"
ENV UC_INTEGRATION_HTTP_PORT="9090"
ENV UC_CONFIG_HOME="/config"

CMD ["python3", "-m", "uc_intg_custom_select"]
