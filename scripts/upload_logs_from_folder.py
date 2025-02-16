import os
import requests
import argparse
import concurrent.futures

def main():
    parser = argparse.ArgumentParser(description="Upload log files to an API endpoint.")
    parser.add_argument("logs_dir", help="Path to the directory containing log files")
    parser.add_argument("api_base_url", help="Base URL of the API (e.g., http://example.com)")
    args = parser.parse_args()

    LOGS_DIR = args.logs_dir
    API_URL = f"{args.api_base_url.rstrip('/')}/api/logs/import/"

    def upload_file(file_name):
        """Uploads a single file to the API endpoint."""
        file_path = os.path.join(LOGS_DIR, file_name)
        print(f"Uploading {file_name}")

        if os.path.isfile(file_path):
            params = {"file_path": file_path}
            try:
                response = requests.post(API_URL, params=params)
                if response.status_code == 200:
                    print(f"Successfully processed file: {file_name}")
                else:
                    print(f"Failed to process file: {file_name}. Status code: {response.status_code}")
                    if response.text:
                        print("Response:", response.text)
            except requests.exceptions.RequestException as e:
                print(f"Error sending request for file {file_name}: {e}")
        else:
            print(f"Skipping directory: {file_name}")

    try:
        files = os.listdir(LOGS_DIR)
    except FileNotFoundError:
        print(f"Directory not found: {LOGS_DIR}")
        exit(1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(upload_file, files)

if __name__ == "__main__":
    main()
