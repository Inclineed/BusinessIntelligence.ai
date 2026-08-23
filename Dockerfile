FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for psycopg2 and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501 8080

# Default command runs both FastAPI and Streamlit via a startup script
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8080 & streamlit run ui/app.py --server.port 8501 --server.address 0.0.0.0"]
