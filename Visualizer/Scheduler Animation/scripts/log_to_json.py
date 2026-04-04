#!/usr/bin/env python3
"""
Translates C scheduler outputs into the JSON format expected by the visualizer.

Usage (from the scheduler root directory):
    python3 log_to_json.py -q <quantum> [-o <output_path>]

Defaults:
    -q   3                                   (match whatever -q you passed to make run)
    -o   visualizer/data/processes.json

Typical workflow:
    make run                                 # runs the C scheduler
    python3 log_to_json.py -q 3 -sch 2      # generates the visualizer JSON
    # then open visualizer/index.html in a browser
"""

import sys
import json
import os

# Colours assigned to processes in order (loops if > 8 processes)
COLORS = [
    '#4285F4', '#0F9D58', '#F4B400', '#DB4437',
    '#AA46BB', '#FF6D00', '#00ACC1', '#E91E63',
]

ALGORITHM_BY_FLAG = {
    0: { 'key': 'sjf',        'name': 'Shortest Job First',      'shortName': 'SJF' },
    1: { 'key': 'hpf',        'name': 'Highest Priority First',  'shortName': 'HPF' },
    2: { 'key': 'rr',         'name': 'Round Robin',             'shortName': 'RR' },
    3: { 'key': 'multiqueue', 'name': 'Multilevel Queue',        'shortName': 'MLQ' },
}


def parse_processes(path):
    """Parse processes.txt → list of {id, arrival, burst}."""
    processes = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split()
            # columns: id  arrival  runtime  priority  memsize
            processes.append({
                'id':      f'P{parts[0]}',
                'arrival': int(parts[1]),
                'burst':   int(parts[2]),
                # priority and memsize are not needed by the visualizer
            })
    return processes


def parse_log(path):
    """
    Parse Scheduler_log.txt → (sequence, extra_stats).

    Log line format (tab-separated):
        At  time  <t>  process  <pid>  <action>  arr  <a>  total  <b>  remain  <r>  wait  <w>
        (finished lines additionally have: TA <ta>  WTA <wta>)

    Actions that open a segment : started, resumed
    Actions that close a segment: stopped, finished

    Returns:
        sequence   – list of {id, start, end} dicts
        extra_stats – {avgTurnaround} derived from the TA fields on 'finished' lines
    """
    sequence   = []
    open_seg   = {}   # pid -> start_time for the currently-open segment
    ta_values  = []   # turnaround times collected from 'finished' lines

    with open(path) as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 6:
                continue
            # parts[0]='At'  [1]='time'  [2]=time  [3]='process'  [4]=pid  [5]=action
            try:
                t      = int(parts[2])
                pid    = f'P{parts[4]}'
                action = parts[5]
            except (ValueError, IndexError):
                continue

            if action in ('started', 'resumed'):
                open_seg[pid] = t
            elif action in ('stopped', 'finished'):
                if pid in open_seg:
                    sequence.append({
                        'id':    pid,
                        'start': open_seg.pop(pid),
                        'end':   t,
                    })
                # 'finished' lines carry: ... TA <ta>  WTA <wta>
                # layout: At time t process pid finished arr a total b remain r wait w TA ta WTA wta
                if action == 'finished':
                    try:
                        ta_idx = parts.index('TA')
                        ta_values.append(float(parts[ta_idx + 1]))
                    except (ValueError, IndexError):
                        pass

    extra_stats = {}
    if ta_values:
        extra_stats['avgTurnaround'] = round(sum(ta_values) / len(ta_values), 2)

    return sequence, extra_stats


def parse_reason_log(path):
    """
    Parse reason_log.txt → dict mapping (pid, end_time) → reason_code.

    Only closing events (stopped, finished) carry an end-of-bar reason.
    The reason code is the token before the em-dash in each reason string,
    e.g. "QUANTUM_EXPIRE — consumed full quantum..." → "QUANTUM_EXPIRE".
    """
    reason_map = {}
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) < 6:
                    continue
                try:
                    t      = int(parts[2])
                    pid    = f'P{parts[4]}'
                    action = parts[5]
                except (ValueError, IndexError):
                    continue
                if action not in ('stopped', 'finished'):
                    continue
                if 'reason: ' not in line:
                    continue
                reason_text = line.split('reason: ', 1)[1].strip()
                # reason_code is everything before the first ' — '
                code = reason_text.split(' \u2014')[0].strip()
                reason_map[(pid, t)] = code
    except FileNotFoundError:
        pass
    return reason_map


def parse_perf(path):
    """Parse Scheduler_perf.txt → stats dict."""
    stats = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if '=' not in line:
                continue
            key, _, val = line.partition('=')
            key = key.strip()
            try:
                val = float(val.strip())
            except ValueError:
                continue
            if 'CPU utilization' in key:
                stats['cpuUtilization'] = round(val, 2)
            elif 'Avg WTA' in key:
                stats['avgWTA'] = round(val, 2)
            elif 'Avg Waiting' in key:
                stats['avgWait'] = round(val, 2)
    return stats


def main():
    quantum         = 3
    sch_flag        = 2
    output_path     = 'visualizer/data/processes.json'
    processes_file  = 'scheduler/processes.txt'
    log_file        = 'scheduler/Scheduler_log.txt'
    perf_file       = 'scheduler/Scheduler_perf.txt'

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '-q' and i + 1 < len(sys.argv):
            quantum = int(sys.argv[i + 1])
            i += 2
        elif arg == '-sch' and i + 1 < len(sys.argv):
            sch_flag = int(sys.argv[i + 1])
            i += 2
        elif arg == '-o' and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    # --- parse ---------------------------------------------------------------
    processes             = parse_processes(processes_file)
    sequence, extra_stats = parse_log(log_file)
    stats                 = parse_perf(perf_file)
    stats.update(extra_stats)   # add avgTurnaround derived from TA fields
    reason_map            = parse_reason_log('scheduler/reason_log.txt')

    # Assign colours to processes and propagate to sequence segments
    color_map = {}
    for idx, p in enumerate(processes):
        p['color'] = COLORS[idx % len(COLORS)]
        color_map[p['id']] = p['color']

    for seg in sequence:
        seg['color']     = color_map.get(seg['id'], '#4285F4')
        seg['endReason'] = reason_map.get((seg['id'], seg['end']), None)

    algorithm = ALGORITHM_BY_FLAG.get(sch_flag, {
        'key': 'unknown',
        'name': f'Unknown Algorithm ({sch_flag})',
        'shortName': f'SCH {sch_flag}',
    })

    # --- assemble output -----------------------------------------------------
    data = {
        'quantum':   quantum,
        'algorithm': algorithm,
        'schFlag':   sch_flag,
        'processes': processes,
        'sequence':  sequence,
        'stats':     stats,
    }

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f'Wrote {len(processes)} processes, {len(sequence)} segments → {output_path}')


if __name__ == '__main__':
    main()
