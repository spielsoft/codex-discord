import argparse
import json
import sys

from .diagnostics import run_doctor
from .publisher import DeliveryPolicy, publish_message, publish_notification


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m codex_discord")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for operation in ("publish", "send"):
        operation_parser = subcommands.add_parser(operation)
        operation_parser.add_argument("--endpoint", required=True)
        operation_parser.add_argument("--state-file", required=True)
        if operation == "publish":
            operation_parser.add_argument("--mention-user-id")
        operation_parser.add_argument(
            "--max-attempts",
            type=int,
            default=DeliveryPolicy.max_attempts,
        )
        operation_parser.add_argument(
            "--request-timeout-seconds",
            type=float,
            default=DeliveryPolicy.request_timeout_seconds,
        )
        operation_parser.add_argument(
            "--delivery-timeout-seconds",
            type=float,
            default=DeliveryPolicy.delivery_timeout_seconds,
        )
    doctor_parser = subcommands.add_parser(
        "doctor",
        description=(
            "Validate local Codex-to-Discord configuration. By default this "
            "does not contact Discord. Exit 0 means ready, exit 1 means local "
            "configuration is incomplete or invalid, and exit 2 means an "
            "explicit test delivery failed."
        ),
    )
    doctor_parser.add_argument(
        "--send-test",
        action="store_true",
        help="explicitly send one quiet Discord health-check message",
    )
    doctor_parser.add_argument(
        "--max-attempts",
        type=int,
        default=DeliveryPolicy.max_attempts,
    )
    doctor_parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=DeliveryPolicy.request_timeout_seconds,
    )
    doctor_parser.add_argument(
        "--delivery-timeout-seconds",
        type=float,
        default=DeliveryPolicy.delivery_timeout_seconds,
    )
    args = parser.parse_args()

    if args.command == "doctor":
        try:
            result, exit_code = run_doctor(
                send_test=args.send_test,
                delivery_policy=DeliveryPolicy(
                    max_attempts=args.max_attempts,
                    request_timeout_seconds=args.request_timeout_seconds,
                    delivery_timeout_seconds=args.delivery_timeout_seconds,
                ),
            )
        except ValueError as error:
            print(f"doctor failed: {error}", file=sys.stderr)
            return 1
        json.dump(result, sys.stdout)
        sys.stdout.write("\n")
        return exit_code

    try:
        notification = json.load(sys.stdin)
        if args.command == "send":
            result = publish_message(
                notification,
                args.endpoint,
                args.state_file,
                delivery_policy=DeliveryPolicy(
                    max_attempts=args.max_attempts,
                    request_timeout_seconds=args.request_timeout_seconds,
                    delivery_timeout_seconds=args.delivery_timeout_seconds,
                ),
            )
        else:
            result = publish_notification(
                notification,
                args.endpoint,
                args.state_file,
                mention_user_id=args.mention_user_id,
                delivery_policy=DeliveryPolicy(
                    max_attempts=args.max_attempts,
                    request_timeout_seconds=args.request_timeout_seconds,
                    delivery_timeout_seconds=args.delivery_timeout_seconds,
                ),
            )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        print(f"{args.command} failed: {error}", file=sys.stderr)
        return 1

    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    if args.command == "send" and result.get("status") == "delivery-failed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
