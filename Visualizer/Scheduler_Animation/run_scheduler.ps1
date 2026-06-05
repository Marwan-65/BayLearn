# default values for the parameters, but can be overrridden when passing values when running the script
param(
    [int]$SCH =  2,
    [int]$Q = 3 ,
    [string]$ProcessFile = "processes.txt"
)

#Tell powershell to exit immediately if any error happens instead of continuing silently
$ErrorActionPreference = "Stop"

# Run the docker container itself first 
# -d detach mode, --build to build if doesnt exist or rebuild if changes
# | Out-Null supress docker verbose output to keep terminal clean
Write-Host "Ensuring scheduler container is running..."
docker compose up -d --build scheduler | Out-Null

# Then run the simulation imside the container that we just started using the run simulation script
#-lc opens a login shell (-l) and runs the quoted command (-c), ensuring environment variables (like PATH) are loaded
Write-Host "Running simulation (SCH=$SCH, Q=$Q, INPUT=$ProcessFile)..."
docker compose exec scheduler bash -lc "bash scripts/run_simulation.sh $SCH $Q '$ProcessFile'"

# if the simulation returns a non zero (failed), then propagate than code to calller
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Simulation complete. Open visualizer/data/processes.json in your visualizer page."
