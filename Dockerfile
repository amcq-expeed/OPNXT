# Simple Dockerfile to run the generated Streamlit app
FROM python:3.11-slim

WORKDIR /app

# System deps sometimes needed by WeasyPrint/Streamlit; keep minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpango1.0-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# Default command to run the generated app
CMD ["streamlit", "run", "generated_code/webapp/streamlit_app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
