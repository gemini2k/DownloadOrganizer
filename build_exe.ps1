# Build a standalone CLI executable (dist\download-organizer.exe) with PyInstaller.
#
#   .\build_exe.ps1            # build
#   .\build_exe.ps1 -Clean     # remove build artifacts first
#
# Note: this packages the CLI (analyze/apply/undo/init-config). The Streamlit web UI
# is a server app and is not packaged into the EXE — run it with `streamlit run`.
param([switch]$Clean)

$ErrorActionPreference = "Stop"

if ($Clean) {
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    Remove-Item -Force *.spec -ErrorAction SilentlyContinue
    Write-Host "Cleaned build/ dist/ *.spec"
}

python -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller failed" }

python -m PyInstaller `
    --onefile `
    --name download-organizer `
    --paths src `
    --collect-submodules download_organizer `
    --hidden-import openpyxl `
    pyinstaller_entry.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

Write-Host ""
Write-Host "Built: dist\download-organizer.exe"
Write-Host "Try:   .\dist\download-organizer.exe analyze --scan-root `"C:\Users\$env:USERNAME\Downloads`""
