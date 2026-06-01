import { Visualizer } from './visualizer.js';
import { UIUpdater } from './uiUpdater.js';
import { DataLoader } from './dataLoader.js';

// ── Algorithm metadata (verified against C source) ──────────────────────────
// SJF  (sch=0): non-preemptive — only switches when running==NULL or rem_time==0
// HPF  (sch=1): preemptive     — SIGSTOP issued when higher-priority process arrives
// RR   (sch=2): preemptive     — quantum-based time-slicing
// MLQ  (sch=3): preemptive     — quantum-based with priority demotion
const ALGO_INFO = {
    sjf:        { preemptive: false, note: 'Non-preemptive — once selected, a process runs to completion' },
    hpf:        { preemptive: true,  note: 'Preemptive — a higher-priority arrival immediately takes the CPU' },
    rr:         { preemptive: true,  note: 'Preemptive — each process gets a fixed quantum before being rotated out' },
    multiqueue: { preemptive: true,  note: 'Preemptive — multi-level feedback queues with quantum-based demotion' },
};

// Whether to show the priority column per algorithm
const SHOWS_PRIORITY = { sjf: false, hpf: true, rr: false, multiqueue: true };

class SchedulerApp {
    constructor() {
        this.sequence     = null;
        this.stats        = null;
        this.visualizer   = null;
        this.uiUpdater    = null;
        this.dataLoader   = new DataLoader();
        this.algoKey      = 'rr';

        // Animation state
        this.currentStep   = -1;
        this.isPlaying     = false;
        this.playInterval  = null;
        this.animationSpeed = 1;

        this.init();
        this.setupEventListeners();
    }

    init() {
        this.dataLoader.loadFromUrl('./data/processes.json', (data) => {
            this.initializeWithData(data);
        });
    }

    initializeWithData(data) {
        this.applyAlgorithmDisplay(data.algorithm, data.quantum);

        this.sequence = data.sequence || [];

        const totalTime = this.sequence.length > 0
            ? this.sequence[this.sequence.length - 1].end
            : 0;

        this.stats = {
            avgWait:         data.stats?.avgWait         ?? '—',
            avgTurnaround:   data.stats?.avgTurnaround   ?? '—',
            contextSwitches: this.sequence.length,
            totalTime,
        };

        // Show/hide priority column
        const showPri = SHOWS_PRIORITY[this.algoKey] ?? false;
        document.getElementById('thPriority').style.display = showPri ? '' : 'none';

        this.visualizer = new Visualizer('chart', data.processes, this.sequence, totalTime);
        this.uiUpdater  = new UIUpdater(data.processes, this.sequence, this.stats, this.algoKey);

        // Update step counter total
        this._updateProgress(-1);

        this.currentStep = -1;
        this.animateToStep(-1);
    }

    applyAlgorithmDisplay(algorithm, quantum) {
        const algo    = algorithm || { key: 'rr', name: 'Round Robin', shortName: 'RR' };
        this.algoKey  = (algo.key || 'rr').toLowerCase();

        document.body.dataset.algorithm = this.algoKey;

        document.getElementById('algoTitle').textContent    = `${algo.name} Scheduling · Gantt Chart View`;
        document.getElementById('algoBadge').textContent    = algo.shortName || algo.name;
        document.getElementById('ganttTitle').textContent   = `${algo.shortName || algo.name} Execution Timeline`;
        document.title = `${algo.shortName || algo.name} Scheduler Visualizer`;

        // Algorithm subtitle (preemption note, verified from C source)
        const info = ALGO_INFO[this.algoKey];
        document.getElementById('algoSubtitle').textContent = info ? info.note : '';

        // Quantum badge
        const usesQuantum = this.algoKey === 'rr' || this.algoKey === 'multiqueue';
        document.getElementById('quantumBadge').style.display = usesQuantum ? 'inline-flex' : 'none';
        if (usesQuantum) document.getElementById('quantumValue').textContent = quantum;
    }

    setupEventListeners() {
        document.getElementById('playBtn').addEventListener('click', () => this.togglePlay());
        document.getElementById('stepBtn').addEventListener('click', () => this.stepForward());
        document.getElementById('stepBackBtn').addEventListener('click', () => this.stepBack());
        document.getElementById('resetBtn').addEventListener('click', () => this.reset());

        document.getElementById('speedSlider').addEventListener('input', (e) => {
            this.animationSpeed = parseFloat(e.target.value);
            if (this.isPlaying) {
                this.stopPlay();
                this.startPlay();
            }
        });

        document.getElementById('fileInput').addEventListener('change', (e) => {
            this.dataLoader.loadFromFile(e.target.files[0], (data) => {
                this.initializeWithData(data);
            });
        });

        // Scrub progress bar
        document.getElementById('progressTrack').addEventListener('click', (e) => {
            if (!this.sequence || this.sequence.length === 0) return;
            const rect  = e.currentTarget.getBoundingClientRect();
            const ratio = (e.clientX - rect.left) / rect.width;
            // +1 because valid steps are 0..sequence.length (final frame)
            const target = Math.round(ratio * this.sequence.length);
            this.jumpTo(target);
        });
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    animateToStep(step) {
        if (!this.visualizer) return;

        const isFinal = step === this.sequence.length;

        this.visualizer.animateToStep(step, this.animationSpeed);
        this.uiUpdater.updateUI(step, this.currentStep);

        // Time display
        if (isFinal) {
            const last = this.sequence[this.sequence.length - 1];
            document.getElementById('currentTimeLabel').textContent = `Time: ${last.end}`;
        } else if (step >= 0) {
            document.getElementById('currentTimeLabel').textContent = `Time: ${this.sequence[step].start}`;
        } else {
            document.getElementById('currentTimeLabel').textContent = 'Time: 0';
        }

        this._updateProgress(step);
    }

    stepForward() {
        if (!this.sequence) return;
        if (this.currentStep < this.sequence.length) {
            this.currentStep++;
            this.animateToStep(this.currentStep);
            if (this.currentStep === this.sequence.length && this.isPlaying) {
                this.stopPlay();
                this._setStatus('done');
            }
        }
    }

    stepBack() {
        if (!this.sequence) return;
        if (this.currentStep > -1) {
            this.currentStep--;
            this.animateToStep(this.currentStep);
        }
    }

    jumpTo(step) {
        if (!this.sequence) return;
        this.stopPlay();
        this.currentStep = Math.max(-1, Math.min(this.sequence.length, step));
        this.animateToStep(this.currentStep);
    }

    reset() {
        this.stopPlay();
        this.currentStep = -1;
        this.animateToStep(-1);
        document.getElementById('playBtn').textContent = 'Play';
        this._setStatus('idle');
    }

    togglePlay() {
        this.isPlaying ? this.stopPlay() : this.startPlay();
    }

    startPlay() {
        if (!this.sequence) return;
        if (this.currentStep >= this.sequence.length) this.reset();
        this.isPlaying = true;
        document.getElementById('playBtn').textContent = 'Pause';
        this._setStatus('playing');

        this.playInterval = setInterval(() => {
            this.stepForward();
        }, 1200 / this.animationSpeed);
    }

    stopPlay() {
        this.isPlaying = false;
        document.getElementById('playBtn').textContent = 'Play';
        clearInterval(this.playInterval);
        if (this.currentStep === this.sequence?.length) {
            this._setStatus('done');
        } else if (this.currentStep >= 0) {
            this._setStatus('paused');
        } else {
            this._setStatus('idle');
        }
    }

    // ── UI helpers ────────────────────────────────────────────────────────────

    _updateProgress(step) {
        const total = this.sequence ? this.sequence.length : 0;
        const pct   = total > 0 ? ((step + 1) / (total + 1)) * 100 : 0;
        document.getElementById('progressFill').style.width = `${Math.max(0, pct)}%`;
        document.getElementById('stepCounter').textContent  = `${Math.max(0, step + 1)} / ${total + 1}`;
    }

    _setStatus(status) {
        const dot  = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        dot.className  = `status-dot ${status}`;
        text.textContent = status;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new SchedulerApp();
});