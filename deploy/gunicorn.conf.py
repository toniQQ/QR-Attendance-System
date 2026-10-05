import multiprocessing

bind = "127.0.0.1:3998"
workers = 3
worker_class = "sync"
threads = 2
timeout = 120
keepalive = 5
max_requests = 1000
max_requests_jitter = 100

accesslog = "/home/quinto/QR-Attendance-System/logs/gunicorn-access.log"
errorlog = "/home/quinto/QR-Attendance-System/logs/gunicorn-error.log"
loglevel = "info"

capture_output = True
pidfile = "/home/quinto/QR-Attendance-System/logs/gunicorn.pid"
