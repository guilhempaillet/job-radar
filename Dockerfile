FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 jobradar \
    && mkdir -p /data \
    && chown jobradar:jobradar /data
USER jobradar
RUN job-radar init-demo --db /data/job-radar.db
VOLUME ["/data"]
EXPOSE 8876
CMD ["job-radar", "serve", "--db", "/data/job-radar.db", "--host", "0.0.0.0", "--port", "8876"]
