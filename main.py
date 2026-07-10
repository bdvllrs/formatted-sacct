import argparse
import json
import shlex
import subprocess
from collections.abc import Iterable
from datetime import datetime, time
from functools import partial
from os import environ, getlogin
from typing import Any

from rich import print as rprint
from rich.console import Console
from rich.table import Table

COLORS = {
    "running": environ.get("RS_COLOR_RUNNING", "deep_sky_blue1"),
    "error": environ.get("RS_COLOR_ERROR", "bright_red"),
    "completed": environ.get("RS_COLOR_COMPLETED", "green3"),
    "pending": environ.get("RS_COLOR_PENDING", "medium_purple1"),
}
DEFAULT_ARGS = {
    "Id": "job_id",
    "User": "user",
    "Name": "name",
    "State": "state.current",
    "Submit": "time.submission",
    "Start": "time.start",
    "Limit": "time.limit",
    "Elapsed": "time.elapsed",
    "Nodes": "nodes",
    "Mem": "tres.mem",
    "CPUs": "tres.cpu",
    "GPUs": "tres.gres/gpu",
    "Exit": "exit_code",
}

STATE_TO_COLOR = {
    "RUNNING": "running",
    "PENDING": "pending",
    "COMPLETED": "completed",
    "BOOT_FAIL": "error",
    "DEADLINE": "error",
    "FAILED": "error",
    "NODE_FAIL": "error",
    "OUT_OF_MEMORY": "error",
    "TIMEOUT": "error",
}


_callbacks: dict[str, Any] = {}


def extract(*names: str):
    def aux(func):
        for name in names:
            _callbacks[name] = partial(func, name)
        return func

    return aux


def display_mem(val: int) -> str:
    return f"{val // 1024}G"


def display_time(t: time) -> str:
    out = []
    if t.hour > 0:
        out.append(f"{t.hour}h")
    if t.minute > 0:
        out.append(f"{t.minute}min")
    if t.second > 0:
        out.append(f"{t.second}s")
    return " ".join(out)


def display_duration(seconds: int | float) -> str:
    days = seconds // 86400
    prefix = ""
    if days > 0:
        prefix = f"{days}d "
    return prefix + display_time(datetime.fromtimestamp(seconds).time())


@extract(
    "job_id",
    "name",
    "nodes",
    "partition",
    "qos",
    "user",
    "stdout_expanded",
    "stderr_expanded",
    "submit_line",
    "working_directory",
)
def _(name: str, job: dict[str, Any]) -> str:
    return str(job[name])


@extract("time.end", "time.start", "time.submission")
def _(name: str, job: dict[str, Any]) -> str:
    seconds = job["time"][name[5:]]
    if seconds == 0:
        return "-"
    return datetime.fromtimestamp(seconds).strftime("%Y-%m-%d %H:%M:%S")


@extract("time.elapsed")
def _(name: str, job: dict[str, Any]) -> str:
    return display_duration(job["time"][name[5:]])


@extract("time.limit")
def _(_name: str, job: dict[str, Any]) -> str:
    return display_duration(job["time"]["limit"]["number"] * 60)


@extract("time.left")
def _(_name: str, job: dict[str, Any]) -> str:
    limit = datetime.fromtimestamp(job["time"]["limit"]["number"] * 60)
    elapsed = datetime.fromtimestamp(job["time"]["elapsed"])
    return display_duration((limit - elapsed).total_seconds())


@extract("exit_code")
def _(_name: str, job: dict[str, Any]) -> str:
    return_code = job["exit_code"]["return_code"]["number"]
    signal = job["exit_code"]["signal"]["id"]["number"]
    return f"{return_code}:{signal}"


@extract("state.current")
def _(_name: str, job: dict[str, Any]) -> str:
    return job["state"]["current"][0]


@extract("state.reason")
def _(_name: str, job: dict[str, Any]) -> str:
    return job["state"]["reason"]


@extract(
    "tres.allocated.mem",
    "tres.allocated.gres/gpu",
    "tres.allocated.cpu",
    "tres.allocated.node",
    "tres.requested.mem",
    "tres.requested.gres/gpu",
    "tres.requested.cpu",
    "tres.requested.node",
)
def _(name: str, job: dict[str, Any]) -> str:
    parts = name.split(".")
    type_, _, name = parts[-1].partition("/")
    for tres in job["tres"][parts[1]]:
        if tres["type"] == type_ and tres["name"] == name:
            if type_ == "mem":
                return display_mem(tres["count"])
            return str(tres["count"])
    return "0"


@extract(
    "tres.mem",
    "tres.gres/gpu",
    "tres.cpu",
    "tres.node",
)
def _(name: str, job: dict[str, Any]) -> str:
    if _callbacks["state.current"](job) == "PENDING":
        name = f"tres.requested.{name[5:]}"
    else:
        name = f"tres.allocated.{name[5:]}"
    return _callbacks[name](job)


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Display sacct info with rich formatting."
    )
    parser.add_argument(
        "--columns",
        type=str,
        required=False,
        default=None,
        help="The columns to display.",
    )

    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Sub-command help"
    )

    my_jobs_parser = subparsers.add_parser(
        "me", help="Display information about your jobs."
    )
    my_jobs_parser.set_defaults(command="me")

    job_parser = subparsers.add_parser(
        "job", help="Display information about a specific job ID."
    )
    job_parser.add_argument("job_id", type=str, help="The job ID to query.")
    job_parser.set_defaults(command="job")

    queue_parser = subparsers.add_parser(
        "queue", help="Display information about queued jobs."
    )
    queue_parser.add_argument(
        "--me", action="store_true", help="Whether to only show my queued jobs."
    )
    queue_parser.set_defaults(command="queue")

    columns_parser = subparsers.add_parser("columns", help="Display available columns.")
    columns_parser.set_defaults(command="columns")

    return parser.parse_known_args()


def get_row(job: dict[str, Any], cols: Iterable[str]) -> list[str]:
    row = []
    for col in cols:
        row.append(_callbacks[col](job))
    return row


def my_jobs(sacct_args: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        ("sacct", "-u", getlogin(), "--json", *sacct_args),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        text=True,
    )
    out = json.loads(result.stdout)
    return out["jobs"]


def specific_job(job_id: str, sacct_args: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        ("sacct", "-j", shlex.quote(job_id), "--json", *sacct_args),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        text=True,
    )
    out = json.loads(result.stdout)
    return out["jobs"]


def queued_jobs(me: str, sacct_args: list[str]) -> list[dict[str, Any]]:
    cmd = ["squeue", "--json"]
    if me:
        cmd.append("--me")
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        text=True,
    )
    out = json.loads(result.stdout)
    ids = [job["job_id"] for job in out["jobs"]]
    jobs = []
    for idx in ids:
        jobs.append(specific_job(str(idx), sacct_args)[0])
    return jobs


def print_columns():
    rprint("[green]" + "[/green], [green]".join(_callbacks.keys()) + "[/green]")


def main():
    args, extras = parse_args()
    if args.command == "me":
        jobs = my_jobs(extras)
    elif args.command == "job":
        jobs = specific_job(args.job_id, extras)
    elif args.command == "queue":
        jobs = queued_jobs(args.me, extras)
    elif args.command == "columns":
        print_columns()
        return
    else:
        ValueError(f"Subcommand {args.command} does not exist.")

    table = Table(show_header=True, show_footer=True)
    user_format = environ.get("RS_COLUMNS", None)
    if args.columns is not None:
        user_format = args.columns

    if user_format is not None:
        keys = user_format.split(",")
        args = {}
        for key in keys:
            name, _, val = key.partition(":")
            if not len(val):
                val = name
            name, val = name.strip(), val.strip()
            if name not in args:
                print(f"{name} is not a valid column, skipping. Valid columns: ")
                print_columns()
            else:
                args[name] = val
    else:
        args = DEFAULT_ARGS
    if not len(args):
        print("No column to show.")
        return
    header, cols = zip(*args.items())
    for col in header:
        table.add_column(col, col)
    for job in jobs:
        state = _callbacks["state.current"](job)
        table.add_row(*get_row(job, cols), style=COLORS[STATE_TO_COLOR[state]])
    console = Console()
    console.print(table)


if __name__ == "__main__":
    main()
