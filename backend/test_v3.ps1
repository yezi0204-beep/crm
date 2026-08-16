# test_v3.ps1 - PowerShell 完整测试
$ErrorActionPreference = "Continue"

# Step 1: Login
Write-Output "=== Step 1: Login ==="
$loginBody = '{"username":"yewei","password":"yewei123"}'
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json" -TimeoutSec 10 -UseBasicParsing
    $token = ($r.Content | ConvertFrom-Json).data.token
    Write-Output "Login OK, token=$token"
} catch {
    Write-Output "Login FAILED: $($_.Exception.Message)"
    exit 1
}

$headers = @{Authorization="Bearer $token"}

# Step 2: Upload Excel
Write-Output "`n=== Step 2: Parse Excel ==="
$filePath = "c:\Program Files\python\crm\backend\vague.xlsx"
$fileName = [System.IO.Path]::GetFileName($filePath)
$fileBytes = [System.IO.File]::ReadAllBytes($filePath)

# Build multipart form data manually
$boundary = [System.Guid]::NewGuid().ToString()
$LF = "`r`n"
$ms = New-Object System.IO.MemoryStream
$sw = New-Object System.IO.StreamWriter($ms, [System.Text.Encoding]::UTF8)
$sw.Write("--$boundary$LF")
$sw.Write("Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"$LF")
$sw.Write("Content-Type: application/octet-stream$LF")
$sw.Write("$LF")
$sw.Flush()
$sw.Write($fileBytes, 0, $fileBytes.Length)
$sw.Write("$LF--$boundary--$LF")
$sw.Flush()
$bodyBytes = $ms.ToArray()
$sw.Close()
$ms.Close()

try {
    $r2 = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/smart-import/parse" -Method POST -Headers $headers -ContentType "multipart/form-data; boundary=$boundary" -Body $bodyBytes -TimeoutSec 30 -UseBasicParsing
    $result = $r2.Content | ConvertFrom-Json
    Write-Output "Parse result code: $($result.code)"
    
    $sheet = $result.data.sheets[0]
    Write-Output "detected_module: $($sheet.detected_module)"
    Write-Output "module_scores count: $($sheet.module_scores.Count)"
    
    if ($sheet.module_scores.Count -gt 0) {
        Write-Output "Modules available:"
        foreach ($ms2 in $sheet.module_scores) {
            Write-Output "  $($ms2.name) score=$($ms2.score)"
        }
        Write-Output "`n[OK] Manual selection works! All $($sheet.module_scores.Count) modules available."
    } else {
        Write-Output "[FAIL] module_scores is empty!"
    }
} catch {
    Write-Output "Parse FAILED: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Output $sr.ReadToEnd()
    }
}
