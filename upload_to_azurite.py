from azure.storage.blob import BlobServiceClient

# Azurite shortcut connection string (handles account name, key, and endpoints automatically)
connect_str = "UseDevelopmentStorage=true"

blob_service_client = BlobServiceClient.from_connection_string(
    connect_str,
    api_version="2025-05-05"
)

container_name = "datasets"

# Create the container (ignore error if it already exists)
try:
    blob_service_client.create_container(container_name)
    print(f"Container '{container_name}' created.")
except Exception as e:
    print(f"Container may already exist: {e}")

# Upload the CSV file
blob_client = blob_service_client.get_blob_client(container=container_name, blob="All_Diets.csv")

with open("All_Diets.csv", "rb") as data:
    blob_client.upload_blob(data, overwrite=True)

print("All_Diets.csv uploaded to Azurite successfully.")