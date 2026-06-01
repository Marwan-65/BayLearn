# Scheduler Animation - Dockerized Run

This project uses Linux-specific behavior (fork, signals, SysV IPC), so running it directly on Windows is inconvenient.

This Docker setup runs the scheduler in a Linux container while keeping all generated logs and JSON files in your local folder.

## Prerequisites

- Docker Desktop installed and running
- Run commands from this folder: `Visualizer/Scheduler Animation`

## Why processes.txt was getting deleted

`make all` runs `clean`, and `clean` previously removed `scheduler/processes.txt`.

This setup now uses `make build` for normal runs, and `clean` no longer deletes `processes.txt`.

## Practical workflow (start once, run many times)

1. Start the container once:

```powershell
docker compose up -d --build scheduler
```

2. Run a simulation whenever you want (no `down` needed):

```powershell
docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh 2 3 processes.txt"
```

3. Change algorithm/quantum/input file by changing arguments only:

```powershell
docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh 3 4 processes_alt.txt"
```

4. Stop container only when done for the day:

```powershell
docker compose down
```

## One-command helper (Windows PowerShell)

Use the helper script from this folder:

```powershell
./run_scheduler.ps1 -SCH 2 -Q 3 -ProcessFile processes.txt
./run_scheduler.ps1 -SCH 3 -Q 4 -ProcessFile processes_alt.txt
```

Algorithm mapping:

- `SCH=0` SJF
- `SCH=1` HPF
- `SCH=2` RR
- `SCH=3` MLQ

Note: an `Interrupt` line can still appear in terminal output because of the scheduler's process-group cleanup behavior, but the wrapper script continues and still generates `visualizer/data/processes.json`.

## Outputs generated on your machine

- `scheduler/Scheduler_log.txt`
- `scheduler/reason_log.txt`
- `scheduler/Memory_log.txt`
- `scheduler/Scheduler_perf.txt`
- `visualizer/data/processes.json`

Because the project is bind-mounted into the container, results are written directly to your local files.

## Run without docker compose

```powershell
docker build -t scheduler-sim .
docker run --rm -it -e SCH=2 -e Q=3 -v "${PWD}:/workspace" -w /workspace scheduler-sim
```

## Open the visualizer

After successful run, open:

- `visualizer/index.html`

## Notes

- This approach gives consistent Linux behavior across Windows/macOS/Linux hosts.
- If an old run left IPC resources, the container lifecycle isolates them from your host.
