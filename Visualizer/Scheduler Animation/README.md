# Scheduler Animation - Dockerized Run

This project uses Linux-specific behavior (fork, signals, SysV IPC), so running it directly on Windows is not supported.
A Docker container provides the Linux environment while keeping all generated logs and JSON files in your local folder via a bind mount.

---

## Prerequisites

- Docker Desktop installed and running
- Run all commands from this folder: `Visualizer/Scheduler Animation`

---

## How It Works — Full File Flow

The animation pipeline has four layers: PowerShell → Docker → Bash → C binaries → Python → Frontend.

```
run_scheduler.ps1          (PowerShell, Windows host)
  │
  ├─ docker compose up -d --build scheduler
  │     └─ Dockerfile       builds the Linux image (gcc, make, python3)
  │     └─ docker-compose.yml  starts the container with `sleep infinity`
  │                            and bind-mounts the project folder to /workspace
  │
  └─ docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh $SCH $Q $ProcessFile"
        │
        └─ scripts/run_simulation.sh   (Bash, inside container)
              │
              ├─ make build            compiles all C source files in scheduler/
              │     ├─ scheduler/process_generator.c  →  process_generator.out
              │     ├─ scheduler/clk.c                →  clk.out
              │     ├─ scheduler/scheduler.c           →  scheduler.out
              │     ├─ scheduler/process.c             →  process.out
              │     └─ scheduler/test_generator.c      →  test_generator.out
              │
              ├─ make stop             kills leftover processes + cleans IPC resources
              │
              ├─ ./process_generator.out $INPUT -sch $SCH -q $Q
              │     runs the full multi-process scheduler simulation
              │     produces log files in scheduler/
              │
              └─ python3 scripts/log_to_json.py -sch $SCH -q $Q
                    reads the log files
                    writes  visualizer/data/processes.json
```

The bind mount (`- .:/workspace` in docker-compose.yml) means every file the container writes appears instantly on your local machine — no copying needed.

---

## Running the Simulation

### Option 1 — One-command helper (recommended)

```powershell
./run_scheduler.ps1 -SCH 2 -Q 3 -ProcessFile processes.txt
```

Parameters are optional; these are the defaults. Examples:

```powershell
./run_scheduler.ps1 -SCH 0                          # SJF, default Q and input
./run_scheduler.ps1 -SCH 3 -Q 4 -ProcessFile processes_alt.txt
```

### Option 2 — Manual steps

Start the container once:

```powershell
docker compose up -d --build scheduler
```

Run a simulation as many times as you want without restarting the container:

```powershell
docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh 2 3 processes.txt"
```

Change algorithm, quantum, or input file by changing the three arguments:

```powershell
docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh 3 4 processes_alt.txt"
```

Stop the container only when done for the day:

```powershell
docker compose down
```

---

## Algorithm Mapping

| SCH value | Algorithm |
|-----------|-----------|
| `0` | SJF — Shortest Job First |
| `1` | HPF — Highest Priority First |
| `2` | RR  — Round Robin |
| `3` | MLQ — Multi-Level Queue |

The `-Q` parameter (time quantum) is only meaningful for RR and MLQ.

---

## Output Files

All output is written directly to your local machine via the bind mount:

| File | Contents |
|------|----------|
| `scheduler/Scheduler_log.txt` | Per-tick scheduling decisions |
| `scheduler/reason_log.txt` | Why each process was scheduled/preempted |
| `scheduler/Memory_log.txt` | Memory allocation events |
| `scheduler/Scheduler_perf.txt` | Performance summary (turnaround, wait times) |
| `visualizer/data/processes.json` | JSON consumed by the frontend animation |

---

## Viewing the Animation

After a successful run, open the BayLearn frontend and navigate to the Scheduler Visualizer page. It reads `visualizer/data/processes.json` automatically.

You can also open the standalone visualizer directly:

```
visualizer/index.html
```

---

## Why `processes.txt` Is Never Deleted

`make clean` removes compiled binaries only. `make clean-all` additionally removes `processes.txt`. Normal simulation runs use `make build` (not `make all` / `make clean`), so your input file is always preserved between runs.

---

## The `Interrupt` Message in Terminal Output

The C scheduler terminates its child processes using SIGINT as part of process-group cleanup. `run_simulation.sh` traps and ignores SIGINT so the Python post-processing step always runs even after that signal. The `Interrupt` line you may see in the terminal is expected and harmless — `processes.json` is still generated correctly.

---

## IPC Resource Cleanup

The scheduler uses SysV shared memory and message queues for inter-process communication. `make stop` (called by `run_simulation.sh` before each run) clears any leftover IPC resources:

```bash
pkill -9 -f "process_generator.out|scheduler.out|clk.out|process.out"
ipcs -m | awk 'NR>3{print $2}' | xargs -r ipcrm -m   # shared memory
ipcs -q | awk 'NR>3{print $2}' | xargs -r ipcrm -q   # message queues
```

---

## Run Without docker compose

```powershell
docker build -t scheduler-sim .
docker run --rm -it -e SCH=2 -e Q=3 -v "${PWD}:/workspace" -w /workspace scheduler-sim
```

---

## Notes

- Consistent Linux behavior across Windows, macOS, and Linux hosts.
- The container is started with `sleep infinity` so it stays alive between runs — you only pay the startup cost once per session.
- The Docker image installs only what is needed: `build-essential` (gcc), `make`, and `python3`.
