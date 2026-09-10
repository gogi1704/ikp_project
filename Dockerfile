FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/app/data/ikp.sqlite3
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY static ./static
COPY scripts ./scripts
COPY run.py .
RUN useradd --create-home --uid 1000 appuser && mkdir /app/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "run.py"]
