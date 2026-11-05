"""Start indexing in a detached session; never stop or restart a job."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]

def detached(command, log, cwd):
    # nohup ignores SIGHUP; setsid via start_new_session removes the SSH tty.
    return subprocess.Popen(
        ["nohup", *command], cwd=cwd, stdin=subprocess.DEVNULL,
        stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        close_fds=True,
    )

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=["smoke", "full"], required=True)
    args = parser.parse_args()
    os.umask(0o077)
    root = ROOT if args.scope == "full" else ROOT / "smoke"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    with (root / ".detached-launch.lock").open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "Another launcher is active; no job started.\n")
        with (root / ".index.lock").open("a") as check:
            try:
                fcntl.flock(check, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                parser.exit(1, "Indexing is already running; no job started.\n")
            fcntl.flock(check, fcntl.LOCK_UN)
            stamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d-%H%M%S-%f")
            log_path = logs / f"{args.scope}-index-detached-{stamp}.log"
            with log_path.open("xb") as log:
                proc = detached(["bash", "scripts/index.sh", args.scope], log, ROOT)
            # Keep the launch guard until the actual index lock is held.
            acquired = False
            for _ in range(100):
                if proc.poll() is not None:
                    parser.exit(1, f"Job exited during startup ({proc.returncode}); inspect {log_path}\n")
                try:
                    fcntl.flock(check, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    acquired = True
                    break
                else:
                    fcntl.flock(check, fcntl.LOCK_UN)
                time.sleep(0.1)
            manifest = {
                "pid": proc.pid, "session_id": proc.pid, "scope": args.scope,
                "log_file": str(log_path), "started_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                "index_lock_observed": acquired, "mode": "nohup + new session + file stdio",
            }
            pointer = logs / f"detached-{args.scope}-run.json"
            temp = pointer.with_suffix(".json.tmp")
            temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            temp.replace(pointer)
            (logs / f"{args.scope}-index.pid").write_text(str(proc.pid) + "\n")
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("Terminal closure will not stop this job. No automatic restart on errors or reboot.")
            if not acquired:
                print("Startup is taking longer than expected; inspect the log before launching again.")

if __name__ == "__main__":
    main()
