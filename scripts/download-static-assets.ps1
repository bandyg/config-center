<# .SYNOPSIS
  Download static assets (CodeMirror, diff-match-patch) for offline/PyInstaller builds.
#>

$TargetDir = Join-Path $PSScriptRoot "app\static"
$CodemirrorDir = Join-Path $TargetDir "codemirror"

# Create directories
@($TargetDir, $CodemirrorDir) | ForEach-Object {
  if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}

$files = @(
  # CodeMirror 5.65.18
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.js";         Path = "$CodemirrorDir\codemirror.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.css";        Path = "$CodemirrorDir\codemirror.min.css" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/mode/javascript/javascript.min.js"; Path = "$CodemirrorDir\javascript.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/edit/matchbrackets.min.js"; Path = "$CodemirrorDir\matchbrackets.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/fold/foldcode.min.js"; Path = "$CodemirrorDir\foldcode.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/fold/foldgutter.min.js"; Path = "$CodemirrorDir\foldgutter.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/fold/brace-fold.min.js"; Path = "$CodemirrorDir\brace-fold.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/search/search.min.js"; Path = "$CodemirrorDir\search.min.js" }
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/search/searchcursor.min.js"; Path = "$CodemirrorDir\searchcursor.min.js" }
  # diff-match-patch
  @{ Url = "https://cdnjs.cloudflare.com/ajax/libs/diff_match_patch/20121119/diff_match_patch.js"; Path = "$TargetDir\diff_match_patch.js" }
)

Write-Host "Downloading static assets..." -ForegroundColor Cyan
$client = New-Object System.Net.WebClient
$ok = 0; $fail = 0
foreach ($f in $files) {
  try {
    Write-Host "  → $($f.Url)" -NoNewline
    $client.DownloadFile($f.Url, $f.Path)
    Write-Host " ✓" -ForegroundColor Green
    $ok++
  } catch {
    Write-Host " ✗ $($_.Exception.Message)" -ForegroundColor Red
    $fail++
  }
}
Write-Host ""
Write-Host "Done: $ok downloaded, $fail failed" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
