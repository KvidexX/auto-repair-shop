$ErrorActionPreference = 'Stop'
$originalPath = $env:PATH
$originalCache = $env:PYINSTALLER_CONFIG_DIR
Push-Location -LiteralPath $PSScriptRoot
try {
    # Не захватываем одноимённые DLL из Qt SDK, Poppler и других программ.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot '.tmp\pyinstaller-cache'
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Создайте .venv и установите requirements-build.txt перед сборкой.'
    }
    & $python -c "import struct, sys; sys.exit(0 if sys.platform == 'win32' and struct.calcsize('P') == 8 and sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Для сборки нужен Python 3.10+ x64 под Windows; рекомендуется 3.12.' }
    & $python -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Обнаружен конфликт зависимостей. Проверьте requirements-build.txt.' }
    & $python -m PyInstaller --clean --noconfirm AutoService.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller завершился с ошибкой.' }

    $application = Join-Path $PSScriptRoot 'dist\AutoService'
    if (-not (Test-Path -LiteralPath (Join-Path $application 'AutoService.exe') -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $application '_internal') -PathType Container)) {
        throw 'Не найдена полная папка приложения PyInstaller.'
    }
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
