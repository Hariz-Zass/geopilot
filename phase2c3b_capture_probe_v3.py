import sys

print("CAPTURE_STDOUT_OK", flush=True)
print("CAPTURE_STDERR_OK", file=sys.stderr, flush=True)

raise SystemExit(7)
