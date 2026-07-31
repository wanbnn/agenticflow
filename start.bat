@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if /I "%~1"=="--help" goto :help
if /I "%~1"=="--check-python" goto :check_python
if /I "%~1"=="--check-gpu" goto :check_gpu
set "INSTALL_ONLY=0"
if /I "%~1"=="--install-only" set "INSTALL_ONLY=1"

title Agentic Flow
echo.
echo  ========================================
echo          AGENTIC FLOW - START
echo  ========================================
echo.

set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
set "VENV_BACKUP="

if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
    if not errorlevel 1 goto :venv_ready
    goto :migrate_venv
)

call :find_python
if defined PYTHON_EXE goto :create_venv

:install_python
echo [INFO] Python 3.12 nao foi encontrado.
where winget >nul 2>nul
if errorlevel 1 goto :python_missing

echo [INFO] Instalando Python 3.12 com winget...
winget install --id Python.Python.3.12 -e --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :python_install_failed

call :find_python
if not defined PYTHON_EXE (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYTHON_EXE goto :python_restart_required
goto :create_venv

:migrate_venv
set "VENV_BACKUP=%CD%\.venv-python-backup-%RANDOM%"
echo [INFO] A .venv existente nao usa Python 3.12.
echo [INFO] Movendo o ambiente antigo para %VENV_BACKUP%...
move "%CD%\.venv" "%VENV_BACKUP%" >nul
if errorlevel 1 goto :venv_failed
call :find_python
if defined PYTHON_EXE goto :create_venv
goto :install_python

:create_venv
echo [INFO] Criando ambiente virtual em .venv...
"%PYTHON_EXE%" -m venv "%CD%\.venv"
if errorlevel 1 goto :venv_failed

:venv_ready
if not exist "%VENV_PYTHON%" goto :venv_failed

set "AMD_GFX=none"
if /I not "%AGENTIC_FLOW_DISABLE_ROCM%"=="1" (
    for /f "delims=" %%G in ('call "%VENV_PYTHON%" -m agentic_flow.amd 2^>nul') do set "AMD_GFX=%%G"
)
if /I not "%AMD_GFX%"=="none" set "AGENTIC_FLOW_USE_ROCM=1"

set "INSTALL_MARKER=%CD%\.venv\.agentic-flow-installed"
if /I "%AGENTIC_FLOW_USE_ROCM%"=="1" set "INSTALL_MARKER=%CD%\.venv\.agentic-flow-rocm-%AMD_GFX%-installed"

if exist "%INSTALL_MARKER%" (
    powershell -NoProfile -Command "if ((Get-Item -LiteralPath 'pyproject.toml').LastWriteTimeUtc -le (Get-Item -LiteralPath '%INSTALL_MARKER%').LastWriteTimeUtc) { exit 0 } else { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto :dependencies_ready
    echo [INFO] pyproject.toml foi atualizado; sincronizando dependencias...
)

echo [INFO] Preparando pip e ferramentas de build...
"%VENV_PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :dependency_failed

if /I "%AGENTIC_FLOW_USE_ROCM%"=="1" goto :install_rocm

echo [INFO] Instalando Agentic Flow e runtime self-hosted...
echo [INFO] O primeiro download pode demorar por incluir PyTorch e Transformers.
"%VENV_PYTHON%" -m pip install -e ".[self-hosted]"
if errorlevel 1 goto :dependency_failed
goto :mark_installed

:install_rocm
echo [INFO] Instalando Agentic Flow com AMD ROCm 7.14...
echo [INFO] Arquitetura detectada: %AMD_GFX%
echo [INFO] Indice AMD: https://repo.amd.com/rocm/whl-multi-arch/
"%VENV_PYTHON%" -m pip install -e ".[self-hosted-runtime]"
if errorlevel 1 goto :dependency_failed
"%VENV_PYTHON%" -m pip uninstall -y torch torchvision torchaudio >nul 2>nul

set "ROCM_DEVICE_EXTRAS=device-%AMD_GFX:,=,device-%"
"%VENV_PYTHON%" -m pip install --extra-index-url https://repo.amd.com/rocm/whl-multi-arch/ "rocm[libraries,%ROCM_DEVICE_EXTRAS%]==7.14.0" "torch[%ROCM_DEVICE_EXTRAS%]==2.12.0+rocm7.14.0" "torchvision[%ROCM_DEVICE_EXTRAS%]==0.27.0+rocm7.14.0" "torchaudio==2.11.0+rocm7.14.0"
if errorlevel 1 goto :dependency_failed

"%VENV_PYTHON%" -c "import sys, torch; print('[OK] PyTorch:', torch.__version__); print('[OK] HIP:', torch.version.hip); print('[OK] GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'indisponivel'); sys.exit(0 if torch.version.hip and torch.cuda.is_available() else 1)"
if errorlevel 1 goto :rocm_verification_failed

:mark_installed
type nul > "%INSTALL_MARKER%"
if defined VENV_BACKUP (
    echo [INFO] Nova .venv validada; removendo o backup incompatível...
    powershell -NoProfile -Command "$root=(Resolve-Path -LiteralPath '%CD%').Path; $target=(Resolve-Path -LiteralPath '%VENV_BACKUP%').Path; if ((Split-Path -Parent $target) -ne $root -or (Split-Path -Leaf $target) -notlike '.venv-python-backup-*') { exit 1 }; Remove-Item -LiteralPath $target -Recurse -Force" >nul 2>nul
)

:dependencies_ready
if /I "%AGENTIC_FLOW_USE_ROCM%"=="1" (
    "%VENV_PYTHON%" -c "import sys, torch; sys.exit(0 if torch.version.hip and torch.cuda.is_available() else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [AVISO] O marcador ROCm existe, mas a GPU nao esta operacional. Reinstalando...
        if exist "%INSTALL_MARKER%" del /q "%INSTALL_MARKER%"
        goto :install_rocm
    )
)
if not defined AGENTIC_FLOW_DATA_DIR set "AGENTIC_FLOW_DATA_DIR=%CD%\data"
if not defined AGENTIC_FLOW_MODEL_DIR set "AGENTIC_FLOW_MODEL_DIR=%AGENTIC_FLOW_DATA_DIR%\models"
if not defined HF_HOME set "HF_HOME=%AGENTIC_FLOW_DATA_DIR%\huggingface"
if not exist "%AGENTIC_FLOW_DATA_DIR%" mkdir "%AGENTIC_FLOW_DATA_DIR%"

if /I not "%AGENTIC_FLOW_DISABLE_LLAMA_CPP%"=="1" (
    echo [INFO] Verificando runtime GGUF llama.cpp para esta GPU...
    "%VENV_PYTHON%" -m agentic_flow.llama_cpp --install --data-dir "%AGENTIC_FLOW_DATA_DIR%"
    if errorlevel 1 echo [AVISO] llama.cpp nao foi instalado agora; os demais runtimes continuam disponiveis.
)
if "%INSTALL_ONLY%"=="1" (
    echo [OK] Instalacao concluida.
    exit /b 0
)
if not defined AGENTIC_FLOW_HOST set "AGENTIC_FLOW_HOST=127.0.0.1"
if not defined AGENTIC_FLOW_PORT set "AGENTIC_FLOW_PORT=16777"
if /I "%AGENTIC_FLOW_USE_ROCM%"=="1" (
    set "TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=0"
    set "AGENTIC_FLOW_ROCM_SAFE_MODE=1"
)

echo.
echo [OK] Ambiente pronto.
echo [OK] Agentic Flow: http://%AGENTIC_FLOW_HOST%:%AGENTIC_FLOW_PORT%
echo [INFO] Pressione Ctrl+C para encerrar.
echo.

:run_server
"%VENV_PYTHON%" -m agentic_flow.main
set "APP_EXIT=%ERRORLEVEL%"
if "%APP_EXIT%"=="0" exit /b 0

if not defined NATIVE_RESTARTS set "NATIVE_RESTARTS=0"
if "%APP_EXIT%"=="-1073741819" goto :recover_native_crash
if "%APP_EXIT%"=="3221225477" goto :recover_native_crash

echo.
echo [ERRO] O Agentic Flow encerrou com codigo %APP_EXIT%.
pause
exit /b %APP_EXIT%

:recover_native_crash
set /a NATIVE_RESTARTS+=1
echo.
echo [AVISO] O runtime nativo de IA foi interrompido pelo driver.
echo [INFO] O servidor sera recuperado automaticamente ^(%NATIVE_RESTARTS%/3^)...
if %NATIVE_RESTARTS% GEQ 3 goto :native_crash_limit
timeout /t 2 /nobreak >nul
goto :run_server

:native_crash_limit
echo [ERRO] O driver falhou repetidamente. O reinicio automatico foi interrompido.
echo [INFO] Reinicie o Windows antes de tentar outra inferencia local.
pause
exit /b %APP_EXIT%

:find_python
set "PYTHON_EXE="
for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYTHON_EXE=%%P"
if defined PYTHON_EXE call :try_python "%PYTHON_EXE%"
if defined PYTHON_EXE exit /b 0

for /f "delims=" %%P in ('py -3 -c "import sys; print(sys.executable) if sys.version_info.major == 3 and sys.version_info.minor in range(11, 100) else sys.exit(1)" 2^>nul') do set "PYTHON_EXE=%%P"
if defined PYTHON_EXE call :try_python "%PYTHON_EXE%"
if defined PYTHON_EXE exit /b 0

for /f "delims=" %%P in ('python -c "import sys; print(sys.executable) if sys.version_info.major == 3 and sys.version_info.minor in range(11, 100) else sys.exit(1)" 2^>nul') do set "PYTHON_EXE=%%P"
if defined PYTHON_EXE call :try_python "%PYTHON_EXE%"
if defined PYTHON_EXE exit /b 0

for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if not defined PYTHON_EXE call :try_python "%%~fD\python.exe"
if defined PYTHON_EXE exit /b 0
for /d %%D in ("%ProgramFiles%\Python3*") do if not defined PYTHON_EXE call :try_python "%%~fD\python.exe"
if defined PYTHON_EXE exit /b 0
for /f "tokens=2,*" %%A in ('reg query "HKCU\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /I "ExecutablePath"') do if not defined PYTHON_EXE call :try_python "%%B"
if defined PYTHON_EXE exit /b 0
for /f "tokens=2,*" %%A in ('reg query "HKLM\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul ^| findstr /I "ExecutablePath"') do if not defined PYTHON_EXE call :try_python "%%B"
exit /b 0

:try_python
set "PYTHON_CANDIDATE=%~1"
set "PYTHON_EXE="
if not exist "%PYTHON_CANDIDATE%" exit /b 0
"%PYTHON_CANDIDATE%" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=%PYTHON_CANDIDATE%"
exit /b 0

:python_missing
echo [ERRO] Python e winget nao estao disponiveis.
echo Instale Python 3.12 em https://www.python.org/downloads/windows/
pause
exit /b 1

:python_install_failed
echo [ERRO] Nao foi possivel instalar Python automaticamente com winget.
echo Instale Python 3.12 manualmente e execute start.bat novamente.
pause
exit /b 1

:python_restart_required
echo [ERRO] Python foi instalado, mas ainda nao esta visivel neste terminal.
echo Feche esta janela e execute start.bat novamente.
pause
exit /b 1

:venv_failed
echo [ERRO] Nao foi possivel criar ou abrir o ambiente virtual .venv.
pause
exit /b 1

:dependency_failed
echo.
echo [ERRO] A instalacao das dependencias falhou.
echo Verifique a conexao, o indice pip e o log acima.
echo Para tentar novamente, execute start.bat.
pause
exit /b 1

:rocm_verification_failed
echo.
echo [ERRO] Os wheels ROCm foram instalados, mas o PyTorch nao acessou a GPU.
echo Confirme o driver AMD, reinicie o Windows e execute start.bat novamente.
if exist "%INSTALL_MARKER%" del /q "%INSTALL_MARKER%"
pause
exit /b 1

:help
echo Uso: start.bat
echo.
echo Cria .venv, instala as dependencias quando necessario e inicia o servidor.
echo.
echo Variaveis opcionais:
echo   AGENTIC_FLOW_AMD_GFX      Forca gfx, por exemplo gfx1200.
echo   AGENTIC_FLOW_DISABLE_ROCM=1  Desativa deteccao automatica AMD.
echo   AGENTIC_FLOW_HOST         Host HTTP, padrao 127.0.0.1.
echo   AGENTIC_FLOW_PORT         Porta HTTP, padrao 16777.
echo   AGENTIC_FLOW_DATA_DIR     Diretorio de dados persistentes.
echo   AGENTIC_FLOW_LLAMA_CPP_BACKEND  Forca hip, cuda, vulkan ou cpu.
echo   AGENTIC_FLOW_DISABLE_LLAMA_CPP=1  Nao instala o runtime GGUF.
echo.
echo Opcoes:
echo   --install-only            Instala/verifica sem iniciar o servidor.
echo   --check-gpu               Exibe gfx detectado e estado do PyTorch/HIP.
exit /b 0

:check_python
call :find_python
if not defined PYTHON_EXE (
    echo Python 3.12 nao encontrado.
    exit /b 1
)
echo Python encontrado: %PYTHON_EXE%
"%PYTHON_EXE%" --version
exit /b %ERRORLEVEL%

:check_gpu
set "VENV_PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PYTHON%" (
    echo Ambiente .venv ainda nao existe. Execute start.bat primeiro.
    exit /b 1
)
for /f "delims=" %%G in ('call "%VENV_PYTHON%" -m agentic_flow.amd 2^>nul') do set "AMD_GFX=%%G"
echo GFX detectado: %AMD_GFX%
"%VENV_PYTHON%" -c "import torch; print('PyTorch:', torch.__version__); print('HIP:', torch.version.hip); print('GPU disponivel:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'nenhuma')"
exit /b %ERRORLEVEL%
