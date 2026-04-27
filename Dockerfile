FROM python:3.11-slim

WORKDIR /app

# Install build dependencies if needed
# RUN apt-get update && apt-get install -y gcc ...

# Copy project configuration
COPY pyproject.toml ./

# Copy the application source code
COPY src/ ./src/

# Install the application and its dependencies
RUN pip install --no-cache-dir .

# Command to run the application
CMD ["python", "-m", "kairos.scheduler"]
