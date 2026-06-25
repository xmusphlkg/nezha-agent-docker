FROM node:20-alpine AS web-build
WORKDIR /src/web
ARG VITE_BASE_PATH=/
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/ctm/.local/bin:${PATH}"
WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin ctm
COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt
COPY api/app ./app
COPY --from=web-build /src/web/dist ./app/static
RUN chown -R ctm:ctm /app
USER ctm
EXPOSE 8088 3000
CMD ["sh", "-c", "uvicorn app.main:app --host ${CTM_CONSOLE_BIND:-0.0.0.0} --port ${CTM_CONSOLE_PORT:-8088} --proxy-headers"]
