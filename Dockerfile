FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY lambda/handler.py /app/lambda/handler.py
COPY local_server.py local_requirements.txt /app/
RUN touch /app/lambda/__init__.py \
    && pip install --no-cache-dir -r /app/local_requirements.txt

ENV PYTHONUNBUFFERED=1 \
    DOWNLOAD_DIR=/downloads \
    PORT=8080
EXPOSE 8080
VOLUME ["/downloads"]
CMD ["python", "/app/local_server.py"]
