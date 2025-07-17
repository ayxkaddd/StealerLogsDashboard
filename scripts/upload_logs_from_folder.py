import os
import requests
import argparse
import concurrent.futures
import time

def main():
    parser = argparse.ArgumentParser(description="Upload log files to an API endpoint.")
    parser.add_argument("logs_dir", help="Path to the directory containing log files")
    parser.add_argument("api_base_url", help="Base URL of the API (e.g., http://example.com)")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for import (default: 5000)")
    parser.add_argument("--use-upsert", action="store_true", help="Use upsert instead of insert")
    parser.add_argument("--max-workers", type=int, default=3, help="Maximum number of concurrent uploads (default: 3)")
    parser.add_argument("--poll-interval", type=int, default=5, help="Polling interval in seconds for task status (default: 5)")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds for task completion (default: 300)")
    args = parser.parse_args()

    LOGS_DIR = args.logs_dir
    API_BASE_URL = args.api_base_url.rstrip('/')
    IMPORT_URL = f"{API_BASE_URL}/api/logs/import/"
    STATUS_URL = f"{API_BASE_URL}/api/logs/import-status/"

    headers = {
        "Content-Type": "application/json"
    }

    def upload_file(file_name: str) -> bool:
        """Uploads a single file to the API endpoint and monitors its progress."""
        file_path = os.path.join(LOGS_DIR, file_name)
        print(f"Starting upload for {file_name}")

        if not os.path.isfile(file_path):
            print(f"Skipping directory or non-file: {file_name}")
            return False

        payload = {
            "file_path": file_path,
            "batch_size": args.batch_size,
            "use_upsert": args.use_upsert
        }

        try:
            response = requests.post(IMPORT_URL, json=payload, headers=headers)

            if response.status_code == 200:
                result = response.json()
                task_id = result.get("task_id")
                print(f"Import task started for {file_name}: {task_id}")

                if monitor_task(task_id, file_name, headers):
                    print(f"✓ Successfully processed file: {file_name}")
                    return True
                else:
                    print(f"✗ Failed to process file: {file_name}")
                    return False
            else:
                print(f"✗ Failed to start import for {file_name}. Status code: {response.status_code}")
                if response.text:
                    try:
                        error_detail = response.json()
                        print(f"Error details: {error_detail}")
                    except:
                        print(f"Response: {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"✗ Error sending request for file {file_name}: {e}")
            return False

    def monitor_task(task_id: str, file_name: str, headers: dict) -> bool:
        """Monitor the progress of an import task."""
        start_time = time.time()

        while True:
            try:
                status_response = requests.get(f"{STATUS_URL}{task_id}", headers=headers)

                if status_response.status_code == 200:
                    status_data = status_response.json()
                    task_status = status_data.get("status")

                    if task_status == "completed":
                        stats = status_data.get("stats", {})
                        print(f"✓ Task {task_id} completed for {file_name}")
                        if stats:
                            print(f"  Stats: {stats}")
                        return True
                    elif task_status == "failed":
                        error = status_data.get("error", "Unknown error")
                        print(f"✗ Task {task_id} failed for {file_name}: {error}")
                        return False
                    elif task_status in ["started", "processing"]:
                        progress = status_data.get("progress", 0)
                        print(f"⏳ Task {task_id} for {file_name}: {task_status} ({progress}%)")
                    else:
                        print(f"? Task {task_id} for {file_name}: unknown status '{task_status}'")

                elif status_response.status_code == 404:
                    print(f"✗ Task {task_id} not found for {file_name}")
                    return False
                else:
                    print(f"✗ Error checking status for {file_name}: {status_response.status_code}")
                    return False

            except requests.exceptions.RequestException as e:
                print(f"✗ Error checking task status for {file_name}: {e}")
                return False

            if time.time() - start_time > args.timeout:
                print(f"⏰ Timeout waiting for task {task_id} for {file_name}")
                return False

            time.sleep(args.poll_interval)

    try:
        files = [f for f in os.listdir(LOGS_DIR) if os.path.isfile(os.path.join(LOGS_DIR, f))]
        if not files:
            print(f"No files found in directory: {LOGS_DIR}")
            exit(1)
    except FileNotFoundError:
        print(f"Directory not found: {LOGS_DIR}")
        exit(1)

    print(f"Found {len(files)} files to upload")
    print(f"Configuration:")
    print(f"  - Batch size: {args.batch_size}")
    print(f"  - Use upsert: {args.use_upsert}")
    print(f"  - Max workers: {args.max_workers}")
    print(f"  - Poll interval: {args.poll_interval}s")
    print(f"  - Timeout: {args.timeout}s")
    print("-" * 50)

    successful_uploads = 0
    failed_uploads = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_file = {executor.submit(upload_file, file_name): file_name for file_name in files}

        for future in concurrent.futures.as_completed(future_to_file):
            file_name = future_to_file[future]
            try:
                success = future.result()
                if success:
                    successful_uploads += 1
                else:
                    failed_uploads += 1
            except Exception as e:
                print(f"✗ Exception processing {file_name}: {e}")
                failed_uploads += 1

    print("-" * 50)
    print(f"Upload Summary:")
    print(f"  ✓ Successful: {successful_uploads}")
    print(f"  ✗ Failed: {failed_uploads}")
    print(f"  📊 Total: {len(files)}")

    if failed_uploads > 0:
        exit(1)

if __name__ == "__main__":
    main()
