import argparse
import requests
import json
import csv
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Query log search API")
    parser.add_argument(
        "api_base_url", help="Base URL of the API (e.g., http://example.com)"
    )
    parser.add_argument("query", help="Search query string")
    parser.add_argument(
        "field",
        choices=["all", "domain", "email", "password"],
        help="Field to search in (all, domain, email, password)",
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        nargs="?",
        const="-",
        help="Output as JSON (optional filename, use - for stdout)",
    )
    output_group.add_argument(
        "--csv",
        nargs="?",
        const="-",
        help="Output as CSV (optional filename, use - for stdout)",
    )

    args = parser.parse_args()

    api_url = f"{args.api_base_url.rstrip('/')}/api/logs/search/"

    payload = {"query": args.query, "field": args.field, "bulk": False}

    try:
        response = requests.post(api_url, json=payload)
        response.raise_for_status()
        data = response.json()

        output_format = None
        output_file = None

        if args.json is not None:
            output_format = "json"
            output_file = args.json if args.json != "-" else None
        elif args.csv is not None:
            output_format = "csv"
            output_file = args.csv if args.csv != "-" else None
        else:
            output_format = "json"
            output_file = None

        if output_format == "json":
            if output_file:
                os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
                with open(output_file, "w") as f:
                    json.dump(data, f, indent=2)
                print(f"JSON results saved to {output_file}")
            else:
                print(json.dumps(data, indent=2))
        elif output_format == "csv":
            if not data:
                return

            fieldnames = ["domain", "uri", "email", "password"]
            if output_file:
                os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
                with open(output_file, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for item in data:
                        writer.writerow(item)
                print(f"CSV results saved to {output_file}")
            else:
                writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
                writer.writeheader()
                for item in data:
                    writer.writerow(item)
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Failed to parse API response", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Unexpected response format: Missing key {e}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"File operation failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
