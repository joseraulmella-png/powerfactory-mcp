$ErrorActionPreference = 'Stop'
$servidor = Join-Path $PSScriptRoot 'servidor.py'
$python = (Get-Command python.exe -ErrorAction Stop).Source
$codex = (Get-Command codex.exe -ErrorAction Stop).Source
if (-not (Test-Path -LiteralPath $servidor)) { throw 'No se encuentra servidor.py.' }
& $python -c 'import sys; assert sys.version_info >= (3,8), "Se requiere Python 3.8 o superior"'
if ($LASTEXITCODE -ne 0) { throw 'Python no es compatible.' }
& $codex mcp get powerfactory_contexto 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Ya existe powerfactory_contexto. Revise codex mcp get powerfactory_contexto antes de cambiarlo.'
    exit 1
}
& $codex mcp add powerfactory_contexto -- $python $servidor
if ($LASTEXITCODE -ne 0) { throw 'No se pudo registrar el servidor.' }
Write-Host 'Servidor registrado. Configure MCP Consulta Puntual en PowerFactory como se indica en LEEME.md.'
