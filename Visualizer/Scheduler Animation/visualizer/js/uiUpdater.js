
function buildNarration(seg, prevSeg, processMap, processState, step, totalSteps) {
    const p        = processMap[seg.id];
    const duration = seg.end - seg.start;
    const isFinal  = step === totalSteps;

    if (isFinal) {
        return { text: 'All processes have completed — the schedule is finished.', color: '#34d399' };
    }

    const priInfo = (p?.priority != null) ? ` (priority ${p.priority})` : '';
    const remaining = processState[seg.id]?.remaining ?? '?';

    switch (seg.endReason) {
        case 'PREEMPTED_BY_HIGHER_PRIORITY': {
            return {
                text: `${seg.id}${priInfo} is preempted at t=${seg.end} by a higher-priority process — it returns to the ready queue with ${remaining} unit(s) remaining.`,
                color: p?.color ?? '#f59e0b',
            };
        }
        case 'QUANTUM_EXPIRE': {
            return {
                text: `${seg.id} consumed its full quantum of ${duration} unit(s) and is moved to the back of the ready queue — ${seg.end - seg.start} units used this slice.`,
                color: p?.color ?? '#38bdf8',
            };
        }
        case 'QUANTUM_EXPIRE+DEMOTED': {
            return {
                text: `${seg.id} quantum expired — demoted one priority level and re-queued. ${duration} unit(s) used this slice.`,
                color: p?.color ?? '#a78bfa',
            };
        }
        case 'QUANTUM_EXPIRE+STARVATION_RESET': {
            return {
                text: `${seg.id} quantum expired at the lowest level — anti-starvation reset triggered: all processes moved back to level 0.`,
                color: '#ef4444',
            };
        }
        case 'COMPLETED': {
            return {
                text: `${seg.id}${priInfo} completes at t=${seg.end} after ${p?.burst ?? duration} unit(s) of CPU time — turnaround = ${seg.end - (p?.arrival ?? 0)} unit(s).`,
                color: '#34d399',
            };
        }
        default: {
            return {
                text: `${seg.id} is executing from t=${seg.start} to t=${seg.end} (${duration} unit(s)).`,
                color: p?.color ?? '#91a4c2',
            };
        }
    }
}

function priorityColor(pri) {
    if (pri == null) return null;
    if (pri <= 2)  return { color: '#f87171', bg: 'rgba(239,68,68,0.12)' };
    if (pri <= 5)  return { color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' };
    if (pri <= 8)  return { color: '#34d399', bg: 'rgba(52,211,153,0.12)' };
    return             { color: '#91a4c2', bg: 'rgba(145,164,194,0.1)' };
}

export class UIUpdater {
    constructor(processes, sequence, stats, algoKey = 'rr') {
        this.processes = processes;
        this.sequence  = sequence;
        this.stats     = stats;
        this.algoKey   = algoKey;

        this.processMap = {};
        processes.forEach(p => { this.processMap[p.id] = p; });

        this.showPriority = (algoKey === 'hpf' || algoKey === 'multiqueue');
    }

    updateUI(step, currentStep) {
        if (step < 0) {
            this.resetUI();
            return;
        }

        const isFinal = step === this.sequence.length;

        const processState = isFinal
            ? this._computeFinalState()
            : this._computeStateAtStep(step, this.sequence[step].start);

        // Queue
        if (isFinal) {
            document.getElementById('queueContainer').innerHTML =
                '<div style="color: #9aa9b9; padding: 20px; text-align: center;">All processes completed</div>';
        } else {
            this.updateQueue(this.sequence[step], this.sequence[step].start, processState);
        }

        this.updateTable(processState);
        this.updateStats(step);
        this.updateNarration(step, isFinal, processState);
    }


    _computeStateAtStep(step, currentTime) {
        const currentSegment = this.sequence[step];

        const executedBefore = {};
        this.processes.forEach(p => { executedBefore[p.id] = 0; });
        for (let i = 0; i < step; i++) {
            const seg = this.sequence[i];
            executedBefore[seg.id] += (seg.end - seg.start);
        }

        const stateMap = {};
        this.processes.forEach(p => {
            const execBefore = executedBefore[p.id];
            const remaining  = Math.max(0, p.burst - execBefore);

            let status;
            if (p.id === currentSegment.id) {
                status = 'executing';
            } else if (remaining <= 0) {
                status = 'completed';
            } else if (p.arrival <= currentTime) {
                status = 'waiting';
            } else {
                status = 'not_arrived';
            }

            const wait = p.arrival <= currentTime
                ? Math.max(0, currentTime - p.arrival - execBefore)
                : 0;

            stateMap[p.id] = { remaining, status, wait };
        });

        return stateMap;
    }

    _computeFinalState() {
        const executedAll = {};
        const finishTime  = {};
        this.processes.forEach(p => { executedAll[p.id] = 0; });

        this.sequence.forEach(seg => {
            executedAll[seg.id] += (seg.end - seg.start);
            finishTime[seg.id]   = seg.end;
        });

        const stateMap = {};
        this.processes.forEach(p => {
            const ft   = finishTime[p.id] ?? 0;
            const wait = Math.max(0, ft - p.arrival - p.burst);
            stateMap[p.id] = { remaining: 0, status: 'completed', wait };
        });
        return stateMap;
    }


    updateNarration(step, isFinal, processState) {
        const textEl   = document.getElementById('narrationText');
        const timeEl   = document.getElementById('narrationTime');
        const accentEl = document.getElementById('narrationAccent');
        const strip    = document.getElementById('narrationStrip');

        if (step < 0) {
            textEl.textContent   = 'Step through the animation to see what is happening at each point.';
            timeEl.textContent   = '';
            accentEl.style.background = 'var(--muted)';
            strip.style.borderColor   = 'var(--border)';
            return;
        }

        const seg      = isFinal ? this.sequence[this.sequence.length - 1] : this.sequence[step];
        const prevSeg  = step > 0 ? this.sequence[step - 1] : null;
        const narration = buildNarration(seg, prevSeg, this.processMap, processState, step, this.sequence.length);

        textEl.textContent = narration.text;
        timeEl.textContent = isFinal
            ? `t = ${seg.end}`
            : `t = ${seg.start} → ${seg.end}`;

        accentEl.style.background = narration.color;
        strip.style.borderColor   = `${narration.color}55`;
    }


    updateQueue(currentSegment, currentTime, processState) {
        const queueContainer = document.getElementById('queueContainer');
        queueContainer.innerHTML = '';

        const executingProcess = this.processes.find(p => p.id === currentSegment.id);
        if (executingProcess) {
            const state = processState[executingProcess.id];
            queueContainer.appendChild(this.createQueueChip(executingProcess, state.remaining, true));
        }

        this.processes
            .filter(p => processState[p.id].status === 'waiting')
            .forEach(p => {
                const state = processState[p.id];
                queueContainer.appendChild(this.createQueueChip(p, state.remaining, false));
            });

        if (queueContainer.children.length === 0) {
            queueContainer.innerHTML =
                '<div style="color: #9aa9b9; padding: 20px; text-align: center;">Queue is empty</div>';
        }
    }

    createQueueChip(process, remaining, isExecuting) {
        const chip = document.createElement('div');
        chip.className = `queue-chip ${isExecuting ? 'executing' : ''}`;

        const priPart = (this.showPriority && process.priority != null)
            ? `<span class="chip-remaining" style="margin-left:4px;">pri ${process.priority}</span>`
            : '';

        chip.innerHTML = `
            <span style="width:10px;height:10px;border-radius:50%;background:${process.color};"></span>
            ${process.id}
            <span class="chip-remaining">${remaining}</span>
            ${priPart}
        `;
        return chip;
    }


    updateTable(processState) {
        const tbody = document.getElementById('processTable');
        tbody.innerHTML = '';

        this.processes.forEach(p => {
            const state = processState[p.id];
            const row   = tbody.insertRow();

            row.style.setProperty('--row-color', p.color);

            let statusClass = 'status-wait';
            let statusText  = 'Waiting';
            if (state.status === 'executing') {
                statusClass = 'status-exec';
                statusText  = 'Executing';
                row.classList.add('row-executing');
            } else if (state.status === 'completed') {
                statusClass = 'status-done';
                statusText  = 'Completed';
                row.classList.add('row-completed');
            } else if (state.status === 'not_arrived') {
                statusText = 'Not Arrived';
            }

            const remainingDisplay  = state.remaining <= 0 ? 0 : state.remaining;
            const turnaroundDisplay = state.status === 'completed'
                ? state.wait + p.burst
                : '—';

            const priCell = this.showPriority
                ? `<td>${this._priorityBadge(p.priority)}</td>`
                : '';

            row.innerHTML = `
                <td><span class="color-dot" style="background:${p.color};"></span>${p.id}</td>
                <td>${p.arrival}</td>
                <td>${p.burst}</td>
                ${priCell}
                <td>${remainingDisplay}</td>
                <td>${state.wait}</td>
                <td>${turnaroundDisplay}</td>
                <td><span class="${statusClass}">${statusText}</span></td>
            `;
        });
    }

    _priorityBadge(pri) {
        if (pri == null) return '—';
        const c = priorityColor(pri);
        return `<span class="priority-badge" style="color:${c.color};border-color:${c.color};background:${c.bg};">${pri}</span>`;
    }


    updateStats(step) {
        const stats = this.stats;
        const isFinal = step === this.sequence.length;

        let currentTime = 0;
        if (isFinal) {
            currentTime = stats.totalTime;
        } else if (step >= 0) {
            currentTime = this.sequence[step].end;  // up to end of current segment
        }
        const utilization = stats.totalTime > 0
            ? Math.round((currentTime / stats.totalTime) * 100)
            : 0;

        document.getElementById('avgWait').textContent         = stats.avgWait;
        document.getElementById('avgTurnaround').textContent   = stats.avgTurnaround;
        document.getElementById('contextSwitches').textContent = stats.contextSwitches;
        document.getElementById('cpuUtil').textContent         = utilization;
    }


    resetUI() {
        document.getElementById('queueContainer').innerHTML =
            '<div style="color: #9aa9b9; padding: 20px; text-align: center;">Ready queue will appear here</div>';

        document.getElementById('narrationText').textContent = 'Step through the animation to see what is happening at each point.';
        document.getElementById('narrationTime').textContent = '';
        document.getElementById('narrationAccent').style.background = 'var(--muted)';
        document.getElementById('narrationStrip').style.borderColor = 'var(--border)';

        const tbody = document.getElementById('processTable');
        tbody.innerHTML = '';
        this.processes.forEach(p => {
            const row = tbody.insertRow();
            const priCell = this.showPriority
                ? `<td>${this._priorityBadge(p.priority)}</td>`
                : '';
            row.innerHTML = `
                <td><span class="color-dot" style="background:${p.color};"></span>${p.id}</td>
                <td>${p.arrival}</td>
                <td>${p.burst}</td>
                ${priCell}
                <td>${p.burst}</td>
                <td>0</td>
                <td>—</td>
                <td><span class="status-wait">Waiting</span></td>
            `;
        });

        this.updateStats(-1);
    }
}