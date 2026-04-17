export class UIUpdater {
    constructor(processes, sequence, stats) {
        this.processes = processes;
        this.sequence = sequence;
        this.stats = stats;   // plain {avgWait, avgTurnaround, contextSwitches, totalTime}
    }
    
    updateUI(step, currentStep) {
        if (step < 0) {
            this.resetUI();
            return;
        }
        
        const currentSegment = this.sequence[step];
        const currentTime = currentSegment.start;
        
        // Update process statuses based on scheduler state
        this.updateProcessStatuses(step, currentSegment);
        
        // Update ready queue
        this.updateQueue(currentSegment, currentTime);
        
        // Update table and stats
        this.updateTable();
        this.updateStats(step);
    }
    
    updateProcessStatuses(step, currentSegment) {
        const currentTime = currentSegment.start;
        
        this.processes.forEach(p => {
            if (p.id === currentSegment.id) {
                p.status = 'executing';
            } else if (p.remaining > 0 && p.arrival <= currentTime) {
                p.status = 'waiting';
                // Update wait time
                if (step > 0) {
                    const prevSegment = this.sequence[step - 1];
                    if (p.arrival <= prevSegment.end) {
                        p.wait += (prevSegment.end - prevSegment.start);
                    }
                }
            } else if (p.remaining <= 0) {
                p.status = 'completed';
            }
        });
    }
    
    updateQueue(currentSegment, currentTime) {
        const queueContainer = document.getElementById('queueContainer');
        queueContainer.innerHTML = '';
        
        // Get ready processes
        const readyProcesses = this.processes.filter(p => 
            p.id !== currentSegment.id && 
            p.remaining > 0 && 
            p.arrival <= currentTime
        );
        
        // Add executing process
        const executingProcess = this.processes.find(p => p.id === currentSegment.id);
        if (executingProcess && executingProcess.remaining > 0) {
            const chip = this.createQueueChip(executingProcess, true);
            queueContainer.appendChild(chip);
        }
        
        // Add ready processes
        readyProcesses.forEach(p => {
            const chip = this.createQueueChip(p, false);
            queueContainer.appendChild(chip);
        });
    }
    
    createQueueChip(process, isExecuting) {
        const chip = document.createElement('div');
        chip.className = `queue-chip ${isExecuting ? 'executing' : ''}`;
        chip.innerHTML = `
            <span style="width: 10px; height: 10px; border-radius: 50%; background: ${process.color};"></span>
            ${process.id}
            <span class="chip-remaining">${process.remaining}</span>
        `;
        return chip;
    }
    
    updateTable() {
        const tbody = document.getElementById('processTable');
        tbody.innerHTML = '';
        
        this.processes.forEach(p => {
            const row = tbody.insertRow();
            
            let statusClass = 'status-wait';
            let statusText = 'Waiting';
            
            if (p.status === 'executing') {
                statusClass = 'status-exec';
                statusText = 'Executing';
            } else if (p.status === 'completed' || p.remaining <= 0) {
                statusClass = 'status-done';
                statusText = 'Completed';
            }
            
            row.innerHTML = `
                <td><span class="color-dot" style="background: ${p.color};"></span>${p.id}</td>
                <td>${p.arrival}</td>
                <td>${p.burst}</td>
                <td>${p.remaining > 0 ? p.remaining : '✓'}</td>
                <td>${p.wait}</td>
                <td>${p.turnaround > 0 ? p.turnaround : '—'}</td>
                <td><span class="${statusClass}">${statusText}</span></td>
            `;
        });
    }
    
    updateStats(step) {
        const stats = this.stats;
        const currentTime = step >= 0 ? this.sequence[step].start : 0;
        const utilization = stats.totalTime > 0 ? Math.round((currentTime / stats.totalTime) * 100) : 0;
        
        document.getElementById('avgWait').textContent = stats.avgWait;
        document.getElementById('avgTurnaround').textContent = stats.avgTurnaround;
        document.getElementById('contextSwitches').textContent = stats.contextSwitches;
        document.getElementById('cpuUtil').textContent = utilization;
    }
    
    resetUI() {
        document.getElementById('queueContainer').innerHTML = 
            '<div style="color: #9aa9b9; padding: 20px; text-align: center;">Ready queue will appear here</div>';
        
        // Reset process data
        this.processes.forEach(p => {
            p.remaining = p.burst;
            p.wait = 0;
            p.turnaround = 0;
            p.status = 'waiting';
        });
        
        this.updateTable();
        this.updateStats(-1);
    }
}