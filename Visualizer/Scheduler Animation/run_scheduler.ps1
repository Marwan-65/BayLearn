param(
    [int]$SCH = 2,
    [int]$Q = 3,
    [string]$ProcessFile = "processes.txt"
)

$ErrorActionPreference = "Stop"

Write-Host "Ensuring scheduler container is running..."
docker compose up -d --build scheduler | Out-Null

Write-Host "Running simulation (SCH=$SCH, Q=$Q, INPUT=$ProcessFile)..."
docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh $SCH $Q '$ProcessFile'"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Simulation complete. Open visualizer/data/processes.json in your visualizer page."
