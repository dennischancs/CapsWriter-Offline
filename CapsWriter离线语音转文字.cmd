@echo off
REM ��ʹ��start_client.exe�Դ��� �����������ܣ����е�������ʹ��cmd��ʽ������ȫ���ص���
REM ���start /b ��ɴ�������
if "%1" == "h" goto begin
mshta vbscript:createobject("wscript.shell").run("""%~nx0"" h",0)(window.close)&&exit
:begin

REM ��ȡ��ǰcmd�ļ�����Ŀ¼��·��
set "currentDir=%~dp0"
echo Current directory: %currentDir%

REM �����򣬺�̨��ִ������������̨����ִ��
set clientProgram=start_client.exe

REM ��鲢�����ͻ��˳���
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