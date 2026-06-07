# Local OSS contract stub for the Reporium trust-score probes.
# Stdlib HTTP server + psycopg2 for reading the local Postgres seed.
FROM python:3.12-slim

WORKDIR /app

# Only dependency: psycopg2 to read the local Postgres graph-quality seed.
# The HTTP server itself is pure stdlib. $0/OSS.
RUN pip install --no-cache-dir psycopg2-binary==2.9.9

COPY app.py /app/app.py

EXPOSE 8080

CMD ["python", "-u", "/app/app.py"]
