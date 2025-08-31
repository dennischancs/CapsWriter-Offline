@echo off
REM 不使用start_client.exe自带的 开机自启功能（会有弹窗），使用cmd方式可以完全隐藏弹窗
REM 配合start /b 完成窗口隐藏
if "%1" == "h" goto begin
mshta vbscript:createobject("wscript.shell").run("""%~nx0"" h",0)(window.close)&&exit
:begin

REM 获取当前cmd文件所在目录的路径
set "currentDir=%~dp0"
echo Current directory: %currentDir%

REM 主程序，后台已执行则跳过，后台无则执行
set clientProgram=start_client.exe

REM 检查并启动客户端程序
if not exist "%currentDir%%clientProgram%" (
    echo ERROR: %clientProgram% not found in %currentDir%
    pause
    exit
)
tasklist | findstr /i "%clientProgram%" > nul
if ERRORLEVEL 1 (
    echo %clientProgram% is not running. Starting the program.
    echo Full path: "%currentDir%%clientProgram%"
    start /b "" "%currentDir%%clientProgram%"
) else (
    echo %clientProgram% is already running. Skipping execution.
)

echo.
echo Script completed.
pause