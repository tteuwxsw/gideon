@echo off
echo.
echo ============================================
echo   INSTALADOR DE FFMPEG PARA GIDEON
echo ============================================
echo.
echo FFmpeg e necessario para aplicar os efeitos
echo de voz da Gideon (The Flash).
echo.
echo Baixando FFmpeg...
echo.

:: Baixa FFmpeg essentials do site oficial
set FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
set TEMP_ZIP=%TEMP%\ffmpeg.zip
set INSTALL_DIR=%USERPROFILE%\ffmpeg

:: Baixa com PowerShell
powershell -Command "& {Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%TEMP_ZIP%'}"

if not exist "%TEMP_ZIP%" (
    echo.
    echo [ERRO] Falha ao baixar FFmpeg.
    echo.
    echo ALTERNATIVA: Baixe manualmente de:
    echo https://www.gyan.dev/ffmpeg/builds/
    echo.
    echo E extraia para: %INSTALL_DIR%\bin\
    pause
    exit /b 1
)

echo.
echo Extraindo...
echo.

:: Extrai para pasta temporaria
powershell -Command "& {Expand-Archive -Path '%TEMP_ZIP%' -DestinationPath '%TEMP%\ffmpeg_extract' -Force}"

:: Move para destino final
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: Procura diretorio bin dentro do extraido
for /d %%i in ("%TEMP%\ffmpeg_extract\ffmpeg-*") do (
    xcopy "%%i\bin" "%INSTALL_DIR%\bin\" /E /I /Y >nul
)

:: Adiciona ao PATH do usuario
echo.
echo Adicionando ao PATH...
echo.

powershell -Command "& {$Path = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($Path -notlike '*%INSTALL_DIR%\bin*') { [Environment]::SetEnvironmentVariable('Path', $Path + ';%INSTALL_DIR%\bin', 'User') }}"

:: Limpa temporarios
del "%TEMP_ZIP%" >nul 2>&1
rmdir /S /Q "%TEMP%\ffmpeg_extract" >nul 2>&1

echo.
echo ============================================
echo   INSTALACAO CONCLUIDA!
echo ============================================
echo.
echo FFmpeg instalado em: %INSTALL_DIR%\bin\
echo.
echo IMPORTANTE: Reinicie o terminal ou CMD
echo            para usar o FFmpeg.
echo.
echo Teste com: ffmpeg -version
echo.
pause
