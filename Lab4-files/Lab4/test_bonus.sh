#!/bin/bash

# High-throughput bonus verification harness.
# - Spawns isolated sandboxes for every file/loss combo so runs can execute in parallel.
# - Mirrors the autograder (same command, same outputs, compares against README baselines).
# - Requires only the default macOS bash (3.2) plus python3 and mktemp.

set -u
set +e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
RESULT_DIR="${ROOT_DIR}/bonus_results"
TMP_ROOT="${ROOT_DIR}/.bonus_tmp"
rm -rf "${RESULT_DIR}" "${TMP_ROOT}"
mkdir -p "${RESULT_DIR}" "${TMP_ROOT}"

# Detect sensible level of parallelism (override with BONUS_JOBS=N)
if [[ -n "${BONUS_JOBS:-}" ]]; then
  CONCURRENCY=${BONUS_JOBS}
else
  if command -v sysctl >/dev/null 2>&1; then
    CONCURRENCY=$(sysctl -n hw.ncpu 2>/dev/null || echo 4)
  else
    CONCURRENCY=4
  fi
fi
[[ "${CONCURRENCY}" -lt 1 ]] && CONCURRENCY=1

FILES=(file1 file2 file3 file4 file5)
LOSSES=(10 30 50 70 90)

build_test_matrix() {
  local combos=()
  local base_time
  for f in "${FILES[@]}"; do
    for loss in "${LOSSES[@]}"; do
      base_time=$(get_baseline "$f" "$loss" "time")
      [[ -z "$base_time" ]] && continue
      combos+=("${base_time}:${f}:${loss}")
    done
  done
  if [[ ${#combos[@]} -gt 0 ]]; then
    printf "%s\n" "${combos[@]}" | sort -n -t':' -k1,1
  fi
}

get_baseline() {
  local target_file=$1
  local target_loss=$2
  local target_field=$3
  
  case "${target_file},${target_loss}" in
    file1,10)
      [[ "$target_field" == "time" ]] && echo "15.221" || echo "468"
      ;;
    file1,30)
      [[ "$target_field" == "time" ]] && echo "25.134" || echo "722"
      ;;
    file1,50)
      [[ "$target_field" == "time" ]] && echo "35.146" || echo "1242"
      ;;
    file1,70)
      [[ "$target_field" == "time" ]] && echo "40.174" || echo "2428"
      ;;
    file1,90)
      [[ "$target_field" == "time" ]] && echo "160.247" || echo "12556"
      ;;
    file2,10)
      [[ "$target_field" == "time" ]] && echo "25.234" || echo "10044"
      ;;
    file2,30)
      [[ "$target_field" == "time" ]] && echo "40.266" || echo "11398"
      ;;
    file2,50)
      [[ "$target_field" == "time" ]] && echo "45.163" || echo "26198"
      ;;
    file2,70)
      [[ "$target_field" == "time" ]] && echo "70.203" || echo "41418"
      ;;
    file2,90)
      [[ "$target_field" == "time" ]] && echo "230.370" || echo "272704"
      ;;
    file3,10)
      [[ "$target_field" == "time" ]] && echo "50.280" || echo "57328"
      ;;
    file3,30)
      [[ "$target_field" == "time" ]] && echo "85.255" || echo "93008"
      ;;
    file3,50)
      [[ "$target_field" == "time" ]] && echo "135.330" || echo "155538"
      ;;
    file3,70)
      [[ "$target_field" == "time" ]] && echo "250.362" || echo "322406"
      ;;
    file3,90)
      [[ "$target_field" == "time" ]] && echo "935.948" || echo "1272066"
      ;;
    file4,10)
      [[ "$target_field" == "time" ]] && echo "110.278" || echo "149020"
      ;;
    file4,30)
      [[ "$target_field" == "time" ]] && echo "170.207" || echo "225914"
      ;;
    file4,50)
      [[ "$target_field" == "time" ]] && echo "295.361" || echo "382792"
      ;;
    file4,70)
      [[ "$target_field" == "time" ]] && echo "650.668" || echo "834342"
      ;;
    file4,90)
      [[ "$target_field" == "time" ]] && echo "2356.981" || echo "2992544"
      ;;
    file5,10)
      [[ "$target_field" == "time" ]] && echo "295.413" || echo "431617"
      ;;
    file5,30)
      [[ "$target_field" == "time" ]] && echo "455.601" || echo "651087"
      ;;
    file5,50)
      [[ "$target_field" == "time" ]] && echo "780.829" || echo "1107376"
      ;;
    file5,70)
      [[ "$target_field" == "time" ]] && echo "1656.525" || echo "2335082"
      ;;
    file5,90)
      [[ "$target_field" == "time" ]] && echo "6770.910" || echo "9365338"
      ;;
    *)
      echo ""
      return 1
      ;;
  esac
}

calc_metrics() {
  python3 - "$@" <<'PY'
import sys
bytes_sent = float(sys.argv[1])
base_bytes = float(sys.argv[2])
time_val = float(sys.argv[3])
base_time = float(sys.argv[4])
bytes_ratio = bytes_sent / base_bytes if base_bytes else 0.0
time_ratio = time_val / base_time if base_time else 0.0
bonus = "BONUS" if (bytes_ratio <= 1.25 and time_ratio <= 1.5) else "NO_BONUS"
print(f"{bytes_ratio:.3f} {time_ratio:.3f} {bonus}")
PY
}

setup_case_dir() {
  local case_dir=$1
  mkdir -p "${case_dir}/logs" "${case_dir}/recvfiles"
  for f in network.py client.py router.py link.py packet.py myClient.py 01.json; do
    ln -sf "${ROOT_DIR}/${f}" "${case_dir}/${f}"
  done
  ln -sf "${ROOT_DIR}/sendfiles" "${case_dir}/sendfiles"
  cp "${ROOT_DIR}/clean.sh" "${case_dir}/clean.sh"
  chmod +x "${case_dir}/clean.sh"
}

run_case() {
  local file=$1
  local loss=$2
  local case_id="${file}_${loss}"
  local base_bytes base_time
  base_bytes=$(get_baseline "$file" "$loss" "bytes")
  base_time=$(get_baseline "$file" "$loss" "time")
  if [[ -z "$base_bytes" || -z "$base_time" ]]; then
    echo "Missing baseline for ${case_id}" >&2
    return 1
  fi

  local work_dir
  work_dir=$(mktemp -d "${TMP_ROOT}/${case_id}.XXXXXX")
  setup_case_dir "${work_dir}"

  local log_path="${RESULT_DIR}/${case_id}.log"
  local send_file="${file}.txt"
  (
    cd "${work_dir}"
    ./clean.sh > /dev/null 2>&1 || true
    python3 network.py 01.json "sendfiles/${send_file}" "recvfiles/${case_id}.txt" "${loss}"
  ) > "${log_path}" 2>&1
  local exit_code=$?

  local summary_line
  if [[ $exit_code -ne 0 ]]; then
    summary_line="${file},${loss},ERROR,0,0,0,0,FAILED"
  else
    local bytes_sent time_val verdict
    bytes_sent=$(grep -E "Total bytes" "${log_path}" | tail -1 | awk '{print $5}')
    time_val=$(grep -E "Total time" "${log_path}" | tail -1 | awk '{print $6}')
    verdict=$(grep -E "SUCCESS|FAILURE" "${log_path}" | tail -1 | tr -d '\r')
    if [[ -z "$bytes_sent" || -z "$time_val" ]]; then
      summary_line="${file},${loss},PARSE_ERR,0,0,0,0,FAILED"
    else
      local metrics_output
      metrics_output=$(calc_metrics "$bytes_sent" "$base_bytes" "$time_val" "$base_time")
      bytes_ratio=$(echo "$metrics_output" | awk '{print $1}')
      time_ratio=$(echo "$metrics_output" | awk '{print $2}')
      bonus_flag=$(echo "$metrics_output" | awk '{print $3}')
      summary_line="${file},${loss},${verdict},${bytes_sent},${time_val},${bytes_ratio},${time_ratio},${bonus_flag}"
    fi
  fi

  echo "${summary_line}" >> "${RESULT_DIR}/results.csv"
  rm -rf "${work_dir}"
}

echo "=== Parallel Bonus Verification ==="
echo "Working directory : ${ROOT_DIR}"
echo "Results directory : ${RESULT_DIR}"
echo "Parallel jobs     : ${CONCURRENCY}"
echo ""

touch "${RESULT_DIR}/results.csv"

IFS=$'\n' SORTED_COMBOS=($(build_test_matrix))
unset IFS

pids=()
for entry in "${SORTED_COMBOS[@]}"; do
  [[ -z "$entry" ]] && continue
  base_time=${entry%%:*}
  rest=${entry#*:}
  combo_file=${rest%%:*}
  combo_loss=${rest##*:}

  run_case "$combo_file" "$combo_loss" &
  pids+=($!)

  if (( ${#pids[@]} >= CONCURRENCY )); then
    wait "${pids[0]}"
    pids=("${pids[@]:1}")
  fi
done

for pid in "${pids[@]}"; do
  wait "$pid"
done

printf "\n%-8s %-6s %-10s %-12s %-12s %-12s %-10s\n" "File" "Loss" "Status" "Bytes" "Time(s)" "Bytes×" "Time×"
bonus_count=0
total_count=0
while IFS=',' read -r file loss verdict bytes time_val bytes_ratio time_ratio bonus_flag; do
  [[ -z "$file" ]] && continue
  printf "%-8s %-6s %-10s %-12s %-12s %-12s %-10s\n" \
    "$file" "$loss%" "$verdict" "$bytes" "$time_val" "$bytes_ratio"x "$time_ratio"x "$bonus_flag"
  total_count=$((total_count + 1))
  [[ "$bonus_flag" == "BONUS" ]] && bonus_count=$((bonus_count + 1))
done < <(sort -t',' -k1,1 -k2,2n "${RESULT_DIR}/results.csv")

echo ""
echo "Bonus-qualified cases: ${bonus_count}/${total_count}"
echo "Detailed logs: ${RESULT_DIR}/*.log"

