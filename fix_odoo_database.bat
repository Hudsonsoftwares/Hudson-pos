@echo off
chcp 65001 >nul
title Fix Odoo Multi-Database for POS Self Order

:: Self-elevation to Administrator if not already elevated
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process cmd -ArgumentList '/c `\"%~f0`\"' -Verb RunAs"
    exit /b
)

echo ====================================================
echo Setting Resto-cafe-testing_3 as Default Database...
echo ====================================================

powershell -NoProfile -ExecutionPolicy Bypass -Command "$conf = 'C:\Program Files\Odoo 20.0.20260928\server\odoo.conf'; $txt = Get-Content -LiteralPath $conf -Raw -Encoding UTF8; if ($txt -notmatch '(?m)^\s*dbfilter\s*=') { $txt = $txt -replace '(?m)^\[options\]', \"[options]`r`ndbfilter = ^Resto-cafe-testing_3$\"; Set-Content -LiteralPath $conf -Value $txt -Encoding UTF8 -Force; Write-Host 'Added dbfilter = ^Resto-cafe-testing_3$' } else { $txt = $txt -replace '(?m)^\s*dbfilter\s*=.*$', 'dbfilter = ^Resto-cafe-testing_3$'; Set-Content -LiteralPath $conf -Value $txt -Encoding UTF8 -Force; Write-Host 'Updated dbfilter to Resto-cafe-testing_3' }"

echo.
echo Restarting Odoo Server Service (odoo-server-20.0)...
net stop odoo-server-20.0
net start odoo-server-20.0

echo.
echo ====================================================
echo SUCCESS! Odoo is now locked to Resto-cafe-testing_3.
echo Any new phone scanning the QR code will open directly!
echo ====================================================
echo.
pause
