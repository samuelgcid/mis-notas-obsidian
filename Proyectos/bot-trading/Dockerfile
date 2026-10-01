FROM python:3.11-slim
RUN useradd --create-home bot
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
USER bot
ENV PYTHONUNBUFFERED=1
# Sano si el latido tiene menos de 5 minutos.
HEALTHCHECK --interval=60s --timeout=5s --start-period=120s \
  CMD python -c "import os,sys,time; sys.exit(0 if time.time()-os.path.getmtime('data/heartbeat')<300 else 1)"
CMD ["python", "-m", "bot", "--config", "config.yaml", "run"]
