# Use Python 3.10 as the base
FROM python:3.10-slim

# Install system dependencies for QR scanning and Postgres
RUN apt-get update && apt-get install -y \
    libzbar0 \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Run the bot
CMD ["python", "controller.py"]
