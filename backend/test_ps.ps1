# 创建测试 Excel
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$wb = $excel.Workbooks.Add()
$ws = $wb.Worksheets.Item(1)
$ws.Name = "数据表"
$ws.Cells.Item(1,1) = "名称"
$ws.Cells.Item(1,2) = "金额"
$ws.Cells.Item(1,3) = "日期"
$ws.Cells.Item(1,4) = "备注"
$ws.Cells.Item(2,1) = "测试A"
$ws.Cells.Item(2,2) = "100"
$ws.Cells.Item(2,3) = "2026-08-01"
$ws.Cells.Item(2,4) = "测试"
$wb.SaveAs("c:\Program Files\python\crm\backend\vague.xlsx")
$wb.Close($false)
$excel.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null

# 登录
$body = '{"username":"yewei","password":"yewei123"}'
$r = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/auth/login" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 10 -UseBasicParsing
$token = ($r.Content | ConvertFrom-Json).data.token
$headers = @{Authorization="Bearer $token"}

# 上传解析
$filePath = "c:\Program Files\python\crm\backend\vague.xlsx"
$boundary = [System.Guid]::NewGuid().ToString()
$fileBytes = [System.IO.File]::ReadAllBytes($filePath)
$fileContent = [System.Text.Encoding]::UTF8.GetString($fileBytes)

$bodyLines = @(
    "--$boundary",
    'Content-Disposition: form-data; name="file"; filename="vague.xlsx"',
    "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "",
    [System.Text.Encoding]::UTF8.GetString($fileBytes),
    "--$boundary--"
) -join "`r`n"

try {
    $r2 = Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/smart-import/parse" -Method POST -Headers $headers -ContentType "multipart/form-data; boundary=$boundary" -Body ([System.Text.Encoding]::UTF8.GetBytes($bodyLines)) -TimeoutSec 30 -UseBasicParsing
    $result = $r2.Content | ConvertFrom-Json
    $sheet = $result.data.sheets[0]
    Write-Output "detected_module: $($sheet.detected_module)"
    Write-Output "module_scores count: $($sheet.module_scores.Count)"
    Write-Output "module_scores:"
    $sheet.module_scores | ForEach-Object { Write-Output "  $($_.name) (score=$($_.score))" }
    Write-Output "all_field_maps keys: $($sheet.all_field_maps.PSObject.Properties.Name -join ', ')"
    if ($sheet.module_scores.Count -eq 6) {
        Write-Output "[OK] 6个模块都在，手动选择有数据！"
    } else {
        Write-Output "[FAIL] 只有 $($sheet.module_scores.Count) 个模块"
    }
} catch {
    Write-Output "Error: $($_.Exception.Message)"
    if ($_.Exception.Response) {
        $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        Write-Output $sr.ReadToEnd()
    }
}
