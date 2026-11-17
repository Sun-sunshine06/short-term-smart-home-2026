@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Preview\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0.."
if not exist .build mkdir .build
cl /nologo /std:c++17 /EHsc /W4 /D_CRT_SECURE_NO_WARNINGS /Iverification\stubs verification\check_firmware.cpp /Fe:.build\check_firmware.exe /Fo:.build\check_firmware.obj
if errorlevel 1 exit /b 1
.build\check_firmware.exe
exit /b %errorlevel%
