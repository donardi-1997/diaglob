$ErrorActionPreference = "Stop"

Write-Host "Diaglob /brag setup" -ForegroundColor Cyan

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is required. Install Node.js 22+ and run this script again."
}

$nodeMajor = [int]((node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 22) {
    throw "Node.js 22+ is required. Current version: $(node --version)"
}

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "npx was not found. Reinstall Node.js/npm and run this script again."
}

Write-Host ""
Write-Host "Installing /brag project-scoped from latent-spaces/brag..."
npx skills add https://github.com/latent-spaces/brag --skill brag
if ($LASTEXITCODE -ne 0) {
    throw "/brag installation failed."
}

Write-Host ""
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Host "FFmpeg: OK" -ForegroundColor Green
} else {
    Write-Warning "FFmpeg is not on PATH. Install FFmpeg before rendering the final video."
}

Write-Host ""
Write-Host "Checking Hyperframes..."
npx hyperframes doctor
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Hyperframes doctor reported an issue. Resolve it before rendering."
}

Write-Host ""
Write-Host "/brag is ready for the Diaglob project." -ForegroundColor Green
Write-Host "See docs/marketing/BRAG.md for the first vertical-video prompt."
