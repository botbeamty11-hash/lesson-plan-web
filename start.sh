#!/usr/bin/env bash
# เริ่มเว็บแอป (gunicorn) แบบเบื้องหลัง: ./start.sh | หยุด: ./start.sh stop | foreground: ./start.sh fg
cd "$(dirname "$0")"
mkdir -p data
PIDF=data/server.pid
if [ "$1" = "stop" ]; then [ -f $PIDF ] && kill "$(cat $PIDF)" && rm -f $PIDF && echo stopped; exit 0; fi
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; fi
if [ -f $PIDF ] && kill -0 "$(cat $PIDF)" 2>/dev/null; then echo "already running (pid $(cat $PIDF))"; exit 0; fi
[ -f .env ] && { set -a; . ./.env; set +a; }
PORT=${PORT:-8080}
CMD=(.venv/bin/gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120)
if [ "$1" = "fg" ]; then exec "${CMD[@]}"; fi
nohup "${CMD[@]}" >> data/server.log 2>&1 &
echo $! > $PIDF; sleep 1; echo "started pid $(cat $PIDF) on port $PORT, log: data/server.log"
