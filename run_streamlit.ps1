# Get the process using port 8501
$portProcessID = (Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue).OwningProcess
# powershell -ExecutionPolicy Bypass -File run_streamlit.ps1

# If a process is using port 8501, kill it
if ($portProcessID) {
    Write-Host "🚨 Port 8501 is in use. Killing process $portProcessID..."
    Stop-Process -Id $portProcessID -Force
    Write-Host "✅ Process $portProcessID has been terminated."
    Start-Sleep -Seconds 2  # Wait 2 seconds to ensure the port is freed
}

# Run Streamlit on port 8501
Write-Host "🚀 Starting Streamlit on port 8501..."
streamlit run app.py
