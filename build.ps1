$ErrorActionPreference = 'Stop'
$originalPath = $env:PATH
$originalCache = $env:PYINSTALLER_CONFIG_DIR
Push-Location -LiteralPath $PSScriptRoot
try {
    # Не захватываем одноимённые DLL из Qt SDK, Poppler и других программ.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot '.tmp\pyinstaller-cache'
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $python -c "import struct, sys; sys.exit(0 if sys.platform == 'win32' and struct.calcsize('P') == 8 else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Для сборки нужен Python x64 под Windows.' }
    & $python -m PyInstaller --clean --noconfirm AutoService.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller завершился с ошибкой.' }

    $application = Join-Path $PSScriptRoot 'dist\AutoService'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README-Windows.txt') -Destination (Join-Path $application 'README.txt') -Force
    $release = Join-Path $PSScriptRoot 'release'
    New-Item -ItemType Directory -Path $release -Force | Out-Null
    $archive = Join-Path $release 'AutoService-Windows-x64.zip'
    Compress-Archive -LiteralPath $application -DestinationPath $archive -Force
    Get-Item -LiteralPath $archive | Select-Object FullName, Length
}
finally {
    $env:PATH = $originalPath
    $env:PYINSTALLER_CONFIG_DIR = $originalCache
    Pop-Location
}
