from azure.storage.blob import BlobServiceClient
import pandas as pd
import io
import json
import os

def process_nutritional_data_from_azurite():
    # Connect to Azurite (local blob storage emulator)
    connect_str = "UseDevelopmentStorage=true"
    blob_service_client = BlobServiceClient.from_connection_string(
        connect_str,
        api_version="2025-05-05"
    )

    container_name = "datasets"
    blob_name = "All_Diets.csv"

    # Get the blob client and download the CSV content
    container_client = blob_service_client.get_container_client(container_name)
    blob_client = container_client.get_blob_client(blob_name)

    print("Downloading All_Diets.csv from Azurite...")
    stream = blob_client.download_blob().readall()
    df = pd.read_csv(io.BytesIO(stream))
    print(f"Loaded {len(df)} rows from blob storage.")

    # Clean data: fill missing values with column average
    for col in ['Protein(g)', 'Carbs(g)', 'Fat(g)']:
        df[col] = df[col].fillna(df[col].mean())

    # Calculate average macronutrients per diet type
    avg_macros = df.groupby('Diet_type')[['Protein(g)', 'Carbs(g)', 'Fat(g)']].mean()

    # Convert results to a list of records (NoSQL-style documents)
    result = avg_macros.reset_index().to_dict(orient='records')

    # Save results to a simulated NoSQL database (JSON file)
    os.makedirs('simulated_nosql', exist_ok=True)
    with open('simulated_nosql/results.json', 'w') as f:
        json.dump(result, f, indent=4)

    print("Results stored in simulated_nosql/results.json")
    print("\nProcessed results:")
    print(json.dumps(result, indent=4))

    return "Data processed and stored successfully."


if __name__ == "__main__":
    message = process_nutritional_data_from_azurite()
    print("\n" + message)