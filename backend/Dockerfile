FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (including fonts for matplotlib PDF generation)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    postgresql-client \
    fontconfig \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
# Fix NumPy compatibility
RUN pip install --no-cache-dir \
    "numpy<2.0" \
    -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY alembic.ini .
COPY alembic/ ./alembic/

# Set Python path
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "src.primedata.api.app:app", "--host", "0.0.0.0", "--port", "8000"]







