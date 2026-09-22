@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cl /nologo /EHsc /std:c++17 /W4 tests\test_jog.cpp /Fe:tests\test_motion.exe /Fo:tests\test_motion.obj
if errorlevel 1 exit /b 1
tests\test_motion.exe
if errorlevel 1 exit /b 1
cl /nologo /EHsc /std:c++17 /W4 /Itests\stubs tests\test_firmware.cpp /Fe:tests\test_firmware.exe /Fo:tests\test_firmware.obj
if errorlevel 1 exit /b 1
tests\test_firmware.exe
