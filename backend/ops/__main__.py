import argparse
import os

from ops.backup import create_backup, verify_backup
from ops.common import OpsError, notify_failure, report
from ops.monitor import check_services


def main():
    parser = argparse.ArgumentParser(
        description="Backup criptografado e monitoramento da apuracao."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup")
    commands.add_parser("monitor")
    verify = commands.add_parser("verify")
    verify.add_argument("directory")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == "backup":
            result = create_backup()
        elif args.command == "verify":
            result = verify_backup(args.directory)
        else:
            checks = check_services()
            failed = [name for name, ok in checks.items() if not ok]
            result = {"status": "failed" if failed else "ok", "checks": checks}
            if failed:
                result["alert_sent"] = notify_failure(
                    "Falha nas verificacoes: " + ", ".join(failed)
                )
        report(result)
        return 0 if result["status"] == "ok" else 1
    except Exception as exc:
        # Do not print exception messages: HTTP/DB errors can contain credentials.
        report(
            {
                "status": "failed",
                "operation": args.command,
                "error_type": type(exc).__name__,
                "reason": str(exc) if isinstance(exc, OpsError) else "Consulte a configuracao e a conectividade da operacao.",
                "alert_sent": notify_failure(
                    "Falha na operacao " + args.command + ". Consulte a execucao privada."
                ),
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
