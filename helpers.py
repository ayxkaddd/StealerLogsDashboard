import json
import config
import re
import subprocess

from models import LogCredential


def extract_logs_info(line: str) -> LogCredential:
    line = line.replace(" ", ":").replace("|", ":")
    if "https://" in line:
        line = line.split("https://")[-1]
    if "http://" in line:
        line = line.split("http://")[-1]

    parts = line.split(':')

    url = parts[0].split("/")
    domain = url[0]
    uri = '/'.join(url[1:]) if len(url) > 1 else ''
    email = parts[1] if len(parts) > 1 else ''
    password = parts[2] if len(parts) > 2 else ''

    return LogCredential(domain=domain.strip(), uri="/"+uri.strip(), email=email.strip(), password=password.strip())


def run_rg_query(query):
    target_directory = config.FOLDER_WITH_LOGS
    output_file = "/tmp/logs.txt"

    command = [
        "rg", "-i", re.escape(query), "-g", "*.txt",
        "--text", "--no-line-number", "--no-filename"
    ]

    try:
        with open(output_file, 'w') as outfile:
            subprocess.run(command, cwd=target_directory, stdout=outfile, check=True)
        print(f"Query results saved to {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error occurred: {e}")


def load_cache() -> dict:
    try:
        with open("file_stats_cache.json", 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}