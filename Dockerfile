FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/packages

# System deps kept minimal. (No OCR engine installed in this skeleton.)
RUN python -m pip install --no-cache-dir --upgrade pip

# Copy the app
COPY . /app

# Install Python dependencies (mirrors pyproject.toml)
RUN pip install --no-cache-dir \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.30" \
    "streamlit>=1.35" \
    "pandas>=2.0" \
    "numpy>=1.26" \
    "pydantic>=2.7" \
    "pyyaml>=6.0" \
    "python-multipart>=0.0.9" \
    "pypdf>=4.0"

EXPOSE 8000 8501
