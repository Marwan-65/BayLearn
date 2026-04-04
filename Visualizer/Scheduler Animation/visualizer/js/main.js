import { Visualizer } from './visualizer.js';
import { UIUpdater } from './uiUpdater.js';
import { DataLoader } from './dataLoader.js';

class SchedulerApp {
    constructor() {
        this.sequence = null;
        this.stats = null;
        this.visualizer = null;
        this.uiUpdater = null;
        this.dataLoader = new DataLoader();
        
        // Animation state
        this.currentStep = -1;
        this.isPlaying = false;
        this.playInterval = null;
        this.animationSpeed = 1;
        
        this.init();
        this.setupEventListeners();
    }
    
    init() {
        // Load the pre-computed output from the C scheduler.
        this.dataLoader.loadFromUrl('./data/processes.json', (data) => {
            this.initializeWithData(data);
        });
    }
    
    initializeWithData(data) {
        this.applyAlgorithmDisplay(data.algorithm, data.quantum);
        
        // Use the pre-computed sequence produced by log_to_json.py.
        this.sequence = data.sequence || [];
        
        // Build a flat stats object for UIUpdater.
        const totalTime = this.sequence.length > 0
            ? this.sequence[this.sequence.length - 1].end
            : 0;
        this.stats = {
            avgWait:         data.stats?.avgWait         ?? '—',
            avgTurnaround:   data.stats?.avgTurnaround   ?? '—',
            contextSwitches: this.sequence.length,
            totalTime,
        };
        
        // Initialize visualizer
        this.visualizer = new Visualizer('chart', data.processes, this.sequence, totalTime);
        
        // Initialize UI updater
        this.uiUpdater = new UIUpdater(data.processes, this.sequence, this.stats);
        
        // Reset state
        this.currentStep = -1;
        this.animateToStep(-1);
    }

    applyAlgorithmDisplay(algorithm, quantum) {
        const algo = algorithm || { key: 'rr', name: 'Round Robin', shortName: 'RR' };
        const algoKey = (algo.key || 'rr').toLowerCase();

        document.body.dataset.algorithm = algoKey;

        const titleEl = document.getElementById('algoTitle');
        const badgeEl = document.getElementById('algoBadge');
        const ganttTitleEl = document.getElementById('ganttTitle');
        const quantumBadgeEl = document.getElementById('quantumBadge');
        const quantumValueEl = document.getElementById('quantumValue');

        titleEl.textContent = `${algo.name} Scheduling · Gantt Chart View`;
        badgeEl.textContent = algo.shortName || algo.name;
        if (ganttTitleEl) {
            ganttTitleEl.textContent = `📊 ${algo.shortName || algo.name} Execution Timeline`;
        }

        document.title = `${algo.shortName || algo.name} Scheduler Visualizer`;

        const usesQuantum = algoKey === 'rr' || algoKey === 'multiqueue';
        quantumBadgeEl.style.display = usesQuantum ? 'inline-flex' : 'none';
        if (usesQuantum) {
            quantumValueEl.textContent = quantum;
        }
    }
    
    setupEventListeners() {
        document.getElementById('playBtn').addEventListener('click', () => this.togglePlay());
        document.getElementById('stepBtn').addEventListener('click', () => this.stepForward());
        document.getElementById('resetBtn').addEventListener('click', () => this.reset());
        
        document.getElementById('speedSlider').addEventListener('input', (e) => {
            this.animationSpeed = parseFloat(e.target.value);
            if (this.isPlaying) {
                this.stopPlay();
                this.startPlay();
            }
        });
        
        // Allow manually loading a different JSON file.
        document.getElementById('fileInput').addEventListener('change', (e) => {
            this.dataLoader.loadFromFile(e.target.files[0], (data) => {
                this.initializeWithData(data);
            });
        });
    }
    
    animateToStep(step) {
        if (!this.visualizer) return;
        
        this.visualizer.animateToStep(step);
        this.uiUpdater.updateUI(step, this.currentStep);
        
        // Update current time display
        if (step >= 0) {
            document.getElementById('currentTimeLabel').textContent = `Time: ${this.sequence[step].start}`;
        } else {
            document.getElementById('currentTimeLabel').textContent = 'Time: 0';
        }
    }
    
    stepForward() {
        if (!this.sequence) return;
        
        if (this.currentStep < this.sequence.length - 1) {
            this.currentStep++;
            this.animateToStep(this.currentStep);
            
            if (this.currentStep === this.sequence.length - 1 && this.isPlaying) {
                this.stopPlay();
            }
        }
    }
    
    reset() {
        this.stopPlay();
        this.currentStep = -1;
        this.animateToStep(-1);
        document.getElementById('playBtn').innerHTML = '▶ Play';
    }
    
    togglePlay() {
        if (this.isPlaying) {
            this.stopPlay();
        } else {
            this.startPlay();
        }
    }
    
    startPlay() {
        if (this.currentStep >= this.sequence.length - 1) {
            this.reset();
        }
        
        this.isPlaying = true;
        document.getElementById('playBtn').innerHTML = '⏸ Pause';
        
        this.playInterval = setInterval(() => {
            this.stepForward();
        }, 1200 / this.animationSpeed);
    }
    
    stopPlay() {
        this.isPlaying = false;
        document.getElementById('playBtn').innerHTML = '▶ Play';
        clearInterval(this.playInterval);
    }
}

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new SchedulerApp();
});