#!/usr/bin/env python3
import subprocess
import re
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# -------------------------------------------------------------------
#  Baseline numbers from the handout (previous-year baselines)
#  Key: (filename, loss_percent) -> {"time": seconds, "bytes": int}
# -------------------------------------------------------------------
BASELINES = {
    ("file1.txt", 10):  {"time": 15.221,  "bytes": 468},
    ("file1.txt", 30):  {"time": 25.134,  "bytes": 722},
    ("file1.txt", 50):  {"time": 35.146,  "bytes": 1242},
    ("file1.txt", 70):  {"time": 40.174,  "bytes": 2428},
    ("file1.txt", 90):  {"time": 160.247, "bytes": 12556},

    ("file2.txt", 10):  {"time": 25.234,  "bytes": 10044},
    ("file2.txt", 30):  {"time": 40.266,  "bytes": 11398},
    ("file2.txt", 50):  {"time": 45.163,  "bytes": 26198},
    ("file2.txt", 70):  {"time": 70.203,  "bytes": 41418},
    ("file2.txt", 90):  {"time": 230.37,  "bytes": 272704},

    ("file3.txt", 10):  {"time": 50.28,   "bytes": 57328},
    ("file3.txt", 30):  {"time": 85.255,  "bytes": 93008},
    ("file3.txt", 50):  {"time": 135.33,  "bytes": 155538},
    ("file3.txt", 70):  {"time": 250.362, "bytes": 322406},
    ("file3.txt", 90):  {"time": 935.948, "bytes": 1272066},

    ("file4.txt", 10):  {"time": 110.278, "bytes": 149020},
    ("file4.txt", 30):  {"time": 170.207, "bytes": 225914},
    ("file4.txt", 50):  {"time": 295.361, "bytes": 382792},
    ("file4.txt", 70):  {"time": 650.668, "bytes": 834342},
    ("file4.txt", 90):  {"time": 2356.981,"bytes": 2992544},

    ("file5.txt", 10):  {"time": 295.413, "bytes": 431617},
    ("file5.txt", 30):  {"time": 455.601, "bytes": 651087},
    ("file5.txt", 50):  {"time": 780.829, "bytes": 1107376},
    ("file5.txt", 70):  {"time": 1656.525,"bytes": 2335082},
    ("file5.txt", 90):  {"time": 6770.91, "bytes": 9365338},
}

# Which test cases to run
FILES = ["file1.txt", "file2.txt", "file3.txt", "file4.txt", "file5.txt"]
LOSSES = [10, 30, 50, 70, 90]

NETWORK_CMD = ["python3", "network.py"]  # you can change to ["python", ...] if needed
JSON_CONFIG = "01.json"

MAX_WORKERS = 4  # how many runs in parallel (tune as you like)


def parse_stats(output: str):
    """
    Parse stdout from network.py to get:
    - total time (float, seconds)
    - total bytes sent (int)
    - success (True if 'SUCCESS' in output)
    Adjust regexes if your network.py uses slightly different wording.
    """
    # Try to find something like "Total time = 123.456" or "Total time of transfer = 123.456"
    time_match = re.search(r"Total.*time.*?=\s*([0-9]*\.?[0-9]+)", output)
    # Try to find "Total bytes sent = 12345"
    bytes_match = re.search(r"Total bytes sent\s*=\s*([0-9]+)", output)

    if not time_match or not bytes_match:
        raise ValueError("Could not parse time/bytes from output. "
                         "Check the regexes in parse_stats().")

    total_time = float(time_match.group(1))
    total_bytes = int(bytes_match.group(1))
    success = "SUCCESS" in output

    return total_time, total_bytes, success


def performance_credit(byte_ratio: float, time_ratio: float) -> int:
    """
    Return extra performance credit percentage for one test case.
    - 15% if bytes <= 1.5x and time <= 2x
    - 10% if bytes <= 1.75x and time <= 3x
    -  5% if bytes <= 2x and time <= 4x
    -  0 otherwise
    """
    if byte_ratio <= 1.5 and time_ratio <= 2.0:
        return 15
    elif byte_ratio <= 1.75 and time_ratio <= 3.0:
        return 10
    elif byte_ratio <= 2.0 and time_ratio <= 4.0:
        return 5
    else:
        return 0


def bonus_point(byte_ratio: float, time_ratio: float) -> int:
    """
    Return bonus points (0 or 1) for this test case:
      +1 if bytes <= 1.25x and time <= 1.5x
    """
    return 1 if (byte_ratio <= 1.25 and time_ratio <= 1.5) else 0


def run_single_test(filename: str, loss: int):
    """
    Run one test case:
      python3 network.py 01.json sendfiles/FILE recvfiles/FILE_lossXX.txt loss
    Return a dict with all relevant stats.
    """
    send_path = Path("sendfiles") / filename
    recv_path = Path("recvfiles") / f"{filename}_loss{loss}.recv"

    cmd = NETWORK_CMD + [JSON_CONFIG, str(send_path), str(recv_path), str(loss)]

    result = subprocess.run(cmd, capture_output=True, text=True)

    stdout = result.stdout
    stderr = result.stderr

    try:
        total_time, total_bytes, success = parse_stats(stdout)
    except Exception as e:
        # On parse failure, report something obvious
        return {
            "file": filename,
            "loss": loss,
            "success": False,
            "parse_error": str(e),
            "stdout": stdout,
            "stderr": stderr,
        }

    base = BASELINES[(filename, loss)]
    base_time = base["time"]
    base_bytes = base["bytes"]

    time_ratio = total_time / base_time
    byte_ratio = total_bytes / base_bytes

    # 70% for correctness if SUCCESS, else 0
    correctness_points = 70 if success else 0

    perf_points = performance_credit(byte_ratio, time_ratio) if success else 0
    bonus = bonus_point(byte_ratio, time_ratio) if success else 0

    total_points = correctness_points + perf_points + bonus

    return {
        "file": filename,
        "loss": loss,
        "success": success,
        "total_time": total_time,
        "total_bytes": total_bytes,
        "base_time": base_time,
        "base_bytes": base_bytes,
        "time_ratio": time_ratio,
        "byte_ratio": byte_ratio,
        "perf_points": perf_points,
        "bonus": bonus,
        "total_points": total_points,
        "stdout": stdout,
        "stderr": stderr,
    }


def main():
    Path("recvfiles").mkdir(exist_ok=True)

    tests = [(f, p) for f in FILES for p in LOSSES]
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_test = {
            executor.submit(run_single_test, f, p): (f, p)
            for f, p in tests
        }

        for future in as_completed(future_to_test):
            f, p = future_to_test[future]
            try:
                res = future.result()
                results.append(res)
                status = "OK" if res.get("success") else "FAIL"
                print(f"[{status}] {f} @ {p}% loss")
            except Exception as e:
                print(f"[ERROR] {f} @ {p}% loss: {e}")

    # Dump to CSV
    with open("results.csv", "w", newline="") as csvfile:
        fieldnames = [
            "file", "loss", "success",
            "total_time", "base_time", "time_ratio",
            "total_bytes", "base_bytes", "byte_ratio",
            "perf_points", "bonus", "total_points"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in sorted(results, key=lambda x: (x["file"], x["loss"])):
            if "parse_error" in r:
                # If parsing failed, just mark as failure with NaNs
                writer.writerow({
                    "file": r["file"],
                    "loss": r["loss"],
                    "success": False,
                    "total_time": "PARSE_ERROR",
                    "base_time": "",
                    "time_ratio": "",
                    "total_bytes": "",
                    "base_bytes": "",
                    "byte_ratio": "",
                    "perf_points": 0,
                    "bonus": 0,
                    "total_points": 0,
                })
            else:
                writer.writerow({
                    "file": r["file"],
                    "loss": r["loss"],
                    "success": r["success"],
                    "total_time": f"{r['total_time']:.3f}",
                    "base_time": f"{r['base_time']:.3f}",
                    "time_ratio": f"{r['time_ratio']:.3f}",
                    "total_bytes": r["total_bytes"],
                    "base_bytes": r["base_bytes"],
                    "byte_ratio": f"{r['byte_ratio']:.3f}",
                    "perf_points": r["perf_points"],
                    "bonus": r["bonus"],
                    "total_points": r["total_points"],
                })

    print("\nWrote results to results.csv")
    print("Columns: file, loss, success, times/bytes, ratios, perf_points, bonus, total_points")


if __name__ == "__main__":
    main()
