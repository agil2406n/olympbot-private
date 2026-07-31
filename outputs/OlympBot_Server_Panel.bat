@echo off
setlocal
title OlympBot Server Baglantisi
start "OlympBot SSH Tunnel" /min ssh.exe -i "%USERPROFILE%\.ssh\olympbot_hetzner_ed25519" -N -o BatchMode=yes -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 15000:127.0.0.1:5000 -L 16080:127.0.0.1:6080 root@62.238.53.134
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:16080/vnc.html?autoconnect=1^&resize=scale^&path=websockify"
start "" "http://127.0.0.1:15000/"
endlocal
