# Use Python base image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose the port
EXPOSE 8080

# Run app with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "visualizeResults:server"]
