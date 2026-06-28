# Dockerfile
# Containerizes the full analytics system.
# Build: docker build -t ecommerce-analytics .
# Run:   docker run -p 8501:8501 --env-file .env ecommerce-analytics

FROM python:3.11-slim

# Metadata
LABEL maintainer="your-email@example.com"
LABEL description="E-Commerce Analytics Platform"

# Prevent Python from writing .pyc files and enable real-time logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user (security best practice)
RUN useradd -m -u 1000 analytics
WORKDIR /app
RUN chown analytics:analytics /app
USER analytics

# Copy and install Python dependencies first (Docker layer caching)
COPY --chown=analytics requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
ENV PATH="/home/analytics/.local/bin:$PATH"

# Copy project files
COPY --chown=analytics . .

# Create required directories
RUN mkdir -p data/raw data/cleaned data/warehouse logs reports/output

# Health check — ensures container is healthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Expose Streamlit port
EXPOSE 8501

# Run the Streamlit dashboard
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
