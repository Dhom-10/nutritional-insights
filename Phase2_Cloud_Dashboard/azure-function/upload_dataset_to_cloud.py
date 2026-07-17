"""
One-time helper: uploads All_Diets.csv to a REAL Azure Blob Storage
container (not Azurite). This is the cloud equivalent of Phase 1's
upload_to_azurite.py.

Usage:
    python upload_dataset_to_cloud.py path/to/All_Diets.csv

Requires the AZURE_STORAGE_CONNECTION_STRING environment variable to be
set to your Azure Storage account's connection string (Azure Portal >
Storage Account > Access keys > Connection string).
"""

import os
import sys

from azure.storage.blob import BlobServiceClient

CONTAINER_NAME = os.environ.get("BLOB_CONTAINER_NAME", "datasets")
BLOB_NAME = os.environ.get("BLOB_NAME", "All_Diets.csv")


def main():
    if len(sys.argv) != 2:
        print("Usage: python upload_dataset_to_cloud.py path/to/All_Diets.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    connect_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    if not connect_str:
        print("ERROR: set AZURE_STORAGE_CONNECTION_STRING first.")
        sys.exit(1)

    blob_service_client = BlobServiceClient.from_connection_string(connect_str)

    try:
        blob_service_client.create_container(CONTAINER_NAME)
        print(f"Container '{CONTAINER_NAME}' created.")
    except Exception as e:
        print(f"Container may already exist: {e}")

    blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=BLOB_NAME)
    with open(csv_path, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)

    print(f"{BLOB_NAME} uploaded to Azure Blob Storage container '{CONTAINER_NAME}' successfully.")


if __name__ == "__main__":
    main()
