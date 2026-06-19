FROM apache/airflow:2.7.1-python3.11

# Switch to root to install system packages
USER root

# Install system dependencies (including fonts for matplotlib PDF generation)
# Add OCR stack: tesseract + ghostscript + qpdf (ocrmypdf runtime deps)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    fontconfig \
    fonts-dejavu \
    tesseract-ocr \
    tesseract-ocr-eng \
    ghostscript \
    qpdf \
    && rm -rf /var/lib/apt/lists/*

# Switch back to airflow user
USER airflow

# Install/upgrade email-validator FIRST (before pydantic)
# The base Airflow image may have an older version that needs upgrading
RUN pip install --no-cache-dir --upgrade "email-validator>=2.0"

# Install Python dependencies for PrimeData
# Fix NumPy compatibility by downgrading to 1.x
RUN pip install --no-cache-dir \
    "numpy<2.0" \
    sqlalchemy==1.4.53 \
    psycopg2-binary \
    minio \
    qdrant-client==1.16.2 \
    sentence-transformers \
    openai>=1.0.0 \
    pydantic \
    pydantic-settings \
    fastapi \
    uvicorn \
    alembic \
    requests \
    python-multipart \
    python-jose[cryptography] \
    passlib[bcrypt] \
    PyJWT \
    cryptography \
    loguru \
    pypdf \
    matplotlib>=3.7.0 \
    ocrmypdf

# Set the working directory
WORKDIR /opt/airflow

# The source code will be mounted as a volume
