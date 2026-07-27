import argparse
import json
import sys

from .publisher import PublishError, publish_completion


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m codex_discord")
    subcommands = parser.add_subparsers(dest="command", required=True)
    publish_parser = subcommands.add_parser("publish")
    publish_parser.add_argument("--endpoint", required=True)
    publish_parser.add_argument("--state-file", required=True)
    args = parser.parse_args()

    try:
        notification = json.load(sys.stdin)
        result = publish_completion(notification, args.endpoint, args.state_file)
    except (PublishError, json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"publish failed: {error}", file=sys.stderr)
        return 1

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
