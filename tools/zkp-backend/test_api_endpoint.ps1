# Test script for TX Hash Commitment API endpoint
# Step 3: Test the /zkp/commit-tx-hash endpoint

Write-Host "`n🧪 Testing TX Hash Commitment API Endpoint (Step 3)`n" -ForegroundColor Cyan

$url = "http://127.0.0.1:5010/zkp/commit-tx-hash"
$txHash = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"

$body = @{
    tx_hash = $txHash
} | ConvertTo-Json

Write-Host "Request: POST $url" -ForegroundColor Yellow
Write-Host "Payload: $body`n" -ForegroundColor Yellow

try {
    $response = Invoke-RestMethod -Uri $url -Method Post -Body $body -ContentType "application/json"
    
    Write-Host "✅ Response received:" -ForegroundColor Green
    Write-Host ($response | ConvertTo-Json -Depth 10)
    
    if ($response.verified -eq $true) {
        Write-Host "`n✅ Step 3 PASSED: API endpoint works correctly!" -ForegroundColor Green
        Write-Host "   Commitment: $($response.commitment)" -ForegroundColor Gray
        Write-Host "   Proof size: $($response.proof.Length / 2) bytes" -ForegroundColor Gray
    } else {
        Write-Host "`n❌ Verification failed!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "`n❌ Error: $_" -ForegroundColor Red
    Write-Host "`n⚠️  Make sure the server is running:" -ForegroundColor Yellow
    Write-Host "   cargo run --bin bulletproof-demo" -ForegroundColor Yellow
    exit 1
}

