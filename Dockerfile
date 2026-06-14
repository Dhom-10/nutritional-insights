# Use a lightweight Python image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy everything from the current folder into the container
COPY . /app

# Install the required Python libraries
RUN pip install -r requirements.txt

# Run the analysis script when the container starts 
CMD ["python", "data_analysis.py"]