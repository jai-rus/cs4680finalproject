FROM python:3.11-slim

WORKDIR /app

# Install Python packages first.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app files into the image.
COPY . .

# Cloud Run gives the app a PORT value.
ENV PORT=8080

# Uvicorn must listen on 0.0.0.0 for Cloud Run.
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port $PORT"]
