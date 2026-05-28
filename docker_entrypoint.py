"""Docker entrypoint: ждёт БД, прогоняет миграции, запускает CMD.

Используется как ENTRYPOINT в Dockerfile. На вход получает CMD (gunicorn или
manage.py runserver), который и запускается после подготовки.
"""
import os
import socket
import subprocess
import sys
import time


def wait_for_db(host, port, timeout=60):
    print(f"[entrypoint] Waiting for database at {host}:{port} ...", flush=True)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                print("[entrypoint] Database is reachable.", flush=True)
                return
        except OSError:
            time.sleep(1)
    print(f"[entrypoint] Timed out after {timeout}s waiting for {host}:{port}",
          file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd):
    print(f"[entrypoint] $ {' '.join(cmd)}", flush=True)
    subprocess.check_call(cmd)


def main():
    if os.environ.get('USE_SQLITE', 'False').lower() != 'true':
        wait_for_db(
            os.environ.get('DB_HOST', 'db'),
            os.environ.get('DB_PORT', '3306'),
        )

    run([sys.executable, 'manage.py', 'migrate', '--noinput'])

    # collectstatic не критичен (если STATIC_ROOT не настроен — пропускаем).
    try:
        run([sys.executable, 'manage.py', 'collectstatic', '--noinput'])
    except subprocess.CalledProcessError as exc:
        print(f"[entrypoint] collectstatic failed ({exc}); continuing.",
              file=sys.stderr, flush=True)

    args = sys.argv[1:]
    if not args:
        args = [
            'gunicorn', 'rental_project.wsgi:application',
            '--bind', '0.0.0.0:8000', '--workers', '3',
        ]
    os.execvp(args[0], args)


if __name__ == '__main__':
    main()
