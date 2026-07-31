$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host ""
Write-Host "  AGENTICFLOW - INSTALADOR" -ForegroundColor Cyan
Write-Host ""

function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe"
    )
    foreach ($command in @("py", "python")) {
        $found = Get-Command $command -ErrorAction SilentlyContinue
        if ($found) {
            try {
                $path = & $found.Source -c "import sys; print(sys.executable) if sys.version_info[:2] == (3, 12) else sys.exit(1)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $path) { return $path.Trim() }
            } catch {}
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

$python = Find-Python
if (-not $python) {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "Python 3.12 e winget não foram encontrados. Instale Python 3.12 e tente novamente."
    }
    Write-Host "[INFO] Instalando Python 3.12..." -ForegroundColor Yellow
    & $winget.Source install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar Python 3.12." }
    $python = Find-Python
    if (-not $python) { throw "Python foi instalado, mas não foi localizado nesta sessão." }
}

Write-Host "[INFO] Python: $python"
& $python -m pip install --user --upgrade pip pipx
if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar o pipx." }

& $python -m pipx ensurepath
& $python -m pipx install --force agenticflow-studio
if ($LASTEXITCODE -ne 0) { throw "Não foi possível instalar agenticflow-studio do PyPI." }

$binDir = (& $python -m pipx environment --value PIPX_BIN_DIR).Trim()
$agenticflow = Join-Path $binDir "agenticflow.exe"
if (-not (Test-Path -LiteralPath $agenticflow)) {
    $agenticflow = Join-Path $binDir "agenticflow.cmd"
}
if (-not (Test-Path -LiteralPath $agenticflow)) {
    throw "O pacote foi instalado, mas o comando agenticflow não foi localizado."
}

Write-Host "[INFO] Detectando GPU e preparando CUDA/ROCm/CPU..." -ForegroundColor Yellow
& $agenticflow install
if ($LASTEXITCODE -ne 0) { throw "A preparação do runtime local falhou." }

Write-Host ""
Write-Host "[OK] AgenticFlow instalado com sucesso." -ForegroundColor Green
Write-Host "Abra um novo terminal e execute: agenticflow"
