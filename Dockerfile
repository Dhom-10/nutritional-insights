# ---------- Stage 1: Builder ----------
# This stage installs dependencies into a separate layer
FROM python:3.9-slim AS builder

WORKDIR /app

# Copy only requirements first (better layer caching)
COPY requirements.txt .

# Install dependencies into a local folder
RUN pip install --user --no-cache-dir -r requirements.txt

# ---------- Stage 2: Final ----------
# This stage only takes what it needs, keeping the image small
FROM python:3.9-slim

WORKDIR /app

# Copy installed packages from the builder stage
COPY --from=builder /root/.local /root/.local

# Copy the application code and data
COPY . /app

# Make sure installed packages are on the PATH
ENV PATH=/root/.local/bin:$PATH

# Run the analysis script
CMD ["python", "data_analysis.py"]