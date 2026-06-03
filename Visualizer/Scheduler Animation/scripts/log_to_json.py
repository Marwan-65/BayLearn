#!/usr/bin/env python3
'''
This file translated the scheduler outputs into the json format needed by the visualizer

run command: python3 log_to_json.py -q "quantam number, default 3" -o "whataver path, default/required visualizer/data/processes.json"

it is called after the scheduler is done and all output logs are ready.
'''

import sys
import json
import os

# process colors in the visualizer and will loop if more than 8
COLORS = [
    '#4285F4', '#0F9D58', '#F4B400', '#DB4437', 
    '#AA46BB', '#FF6D00', '#00ACC1', '#E91E63',
]
# mapping sch_flag values to their info that will be visualized
ALGORITHM_BY_FLAG = {
    0: { 'key': 'sjf',        'name': 'Shortest Job First',      'shortName': 'SJF' },
    1: { 'key': 'hpf',        'name': 'Highest Priority First',  'shortName': 'HPF' }, 
    2: { 'key': 'rr',         'name': 'Round Robin',             'shortName': 'RR' },
    3: { 'key': 'multiqueue', 'name': 'Multilevel Queue',        'shortName': 'MLQ' }, 
}

#parse processes.txt to list where each element is id,arrival,burst,priority
def parse_processes(path):
    processes =[] 
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): #ignore empty lines and the header
                continue
            parts = line.split()
            # columns: id  arrival  runtime  priority  memsize
            processes.append({
                'id':      f'P{parts[0]}',
                'arrival': int(parts[1]),
                'burst':   int(parts[2]),
                'priority': int(parts[3]),
                # memsize is not needed by the visualizer
            })
    return processes

#parse scheduler_log.txt and output a list of (sequence, extra_stats)
# sequence is a list of {id, start, end} dicts 
#extra_stats is {avgTurnaround} derived from the TA fields on 'finished' lines 
#line format to be parsed: At  time  <t>  process  <pid>  <action>  arr  <a>  total  <b>  remain  <r>  wait  <w>
#"started" and "resumed" open a segment, "stopped" and "finished" close a segment.
def parse_log(path):
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

#parse reason_log.txt to dict mapping (pid, end_time) -> reason_code
#only closing events (stopped, finished) carry a reason.
# the reason code is the token before the em-dash in each reason string,
#example "QUANTUM_EXPIRE — consumed full quantum ..etc" -> "QUANTUM_EXPIRE".
def parse_reason_log(path):
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

#parse Scheduler_perf.txt to a stats dict
# the stats are key value pairs.
def parse_perf(path):
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
    quantum=3
    sch_flag= 2
    output_path='visualizer/data/processes.json'
    processes_file='scheduler/processes.txt'
    log_file = 'scheduler/Scheduler_log.txt'
    perf_file='scheduler/Scheduler_perf.txt'

#set default values and ovverride them if exist
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

    #assign colours to processes and propagate to sequence segments
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

    print(f'Wrote {len(processes)} processes, {len(sequence)} segments -> {output_path}')


if __name__ == '__main__':
    main()
