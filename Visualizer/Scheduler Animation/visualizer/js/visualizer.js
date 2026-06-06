
const END_REASON = {
    'QUANTUM_EXPIRE':                  { icon: 'Q',  label: 'Quantum expired — preempted, sent to back of queue' },
    'QUANTUM_EXPIRE+DEMOTED':          { icon: 'Q↓', label: 'Quantum expired — demoted one priority level' },
    'QUANTUM_EXPIRE+STARVATION_RESET': { icon: 'QR', label: 'Quantum expired — starvation reset: all processes moved to level 0' },
    'PREEMPTED_BY_HIGHER_PRIORITY':    { icon: 'P',  label: 'Preempted — higher-priority process arrived' },
    'COMPLETED':                       { icon: '■',  label: 'Process completed — burst fully consumed' },
};

export class Visualizer {
    constructor(containerId, processes, sequence, totalTime) {
        this.containerId = containerId;
        this.processes = processes;
        this.sequence = sequence;
        this.totalTime = totalTime;
        
        this.margin = { top: 20, right: 30, bottom: 40, left: 60 };
        this.width = 0;
        this.height = 200 - this.margin.top - this.margin.bottom;
        
        this.svg = null;
        this.xScale = null;
        this.yScale = null;
        this.bars       = [];
        this.icons      = [];
        this.barLabels  = [];  
        
        this.init();
    }
    
    init() {
        const accent = (getComputedStyle(document.body).getPropertyValue('--accent') || '#3b82f6').trim();

        // Calculate width based on container
        const container = document.getElementById(this.containerId);
        this.width = container.clientWidth - this.margin.left - this.margin.right - 48;
        
        // Clear previous SVG
        d3.select(`#${this.containerId}`).selectAll("*").remove();
        
        // Create SVG
        this.svg = d3.select(`#${this.containerId}`)
            .append("svg")
            .attr("width", this.width + this.margin.left + this.margin.right)
            .attr("height", this.height + this.margin.top + this.margin.bottom)
            .append("g")
            .attr("transform", `translate(${this.margin.left},${this.margin.top})`);
        
        // Create scales
        this.xScale = d3.scaleLinear()
            .domain([0, this.totalTime])
            .range([0, this.width]);
        
        const processIds = this.processes.map(p => p.id);
        this.yScale = d3.scaleBand()
            .domain(processIds)
            .range([0, this.height])
            .padding(0.3);
        
        // Add axes
        this.svg.append("g")
            .attr("transform", `translate(0,${this.height})`)
            .call(d3.axisBottom(this.xScale).ticks(10))
            .style("font-size", "10px")
            .style("color", "#8a9bb0");
        
        this.svg.append("g")
            .call(d3.axisLeft(this.yScale).tickSize(0))
            .style("font-size", "11px")
            .style("font-weight", "500")
            .style("color", "#4a5a6e");
        
        // Add horizontal grid lines
        this.svg.selectAll("horizontal-grid")
            .data(processIds)
            .enter()
            .append("line")
            .attr("x1", 0)
            .attr("x2", this.width)
            .attr("y1", d => this.yScale(d) + this.yScale.bandwidth() / 2)
            .attr("y2", d => this.yScale(d) + this.yScale.bandwidth() / 2)
            .attr("stroke", "#e2e8f0")
            .attr("stroke-dasharray", "4,4")
            .attr("stroke-width", 1);
        
        // Create bars, center-labels, and end-of-bar annotation markers
        this.bars      = [];
        this.icons     = [];
        this.barLabels = [];
        this.sequence.forEach((d) => {
            const bar = this.svg.append("rect")
                .attr("x", this.xScale(d.start))
                .attr("y", this.yScale(d.id))
                .attr("width", 0)
                .attr("height", this.yScale.bandwidth())
                .attr("fill", d.color)
                .attr("rx", 4)
                .attr("ry", 4)
                .style("opacity", 0.7)
                .style("transition", "width 0.8s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s");
            
            this.bars.push(bar);

            // Bar center label — process ID inside the bar
            // Centered at midpoint of the bar; hidden initially, revealed with the bar
            const barMidX = (this.xScale(d.start) + this.xScale(d.end)) / 2;
            const barLabel = this.svg.append("text")
                .attr("x", barMidX)
                .attr("y", this.yScale(d.id) + this.yScale.bandwidth() / 2)
                .attr("text-anchor", "middle")
                .attr("dominant-baseline", "middle")
                .attr("font-size", "10px")
                .attr("font-family", "'JetBrains Mono', monospace")
                .attr("font-weight", "600")
                .attr("fill", "#ffffff")
                .attr("pointer-events", "none")
                .style("opacity", 0)
                .text(d.id);

            this.barLabels.push(barLabel);

            const reason = END_REASON[d.endReason];
            const iconText = this.svg.append("text")
                .attr("x", this.xScale(d.end) + 4)
                .attr("y", this.yScale(d.id) + this.yScale.bandwidth() / 2)
                .attr("dominant-baseline", "middle")
                .attr("font-size", "9px")
                .attr("font-family", "'JetBrains Mono', monospace")
                .attr("font-weight", "700")
                .attr("fill", "#e2e8f0")
                .style("opacity", 0)
                .style("transition", "opacity 0.4s")
                .style("cursor", "default")
                .text(reason ? reason.icon : '');

            if (reason) {
                iconText.append("title").text(reason.label);
            }

            this.icons.push(iconText);
        });
        
        // Create cursor
        this.cursor = this.svg.append("line")
            .attr("x1", 0)
            .attr("x2", 0)
            .attr("y1", 0)
            .attr("y2", this.height)
            .attr("stroke", accent)
            .attr("stroke-width", 3)
            .attr("stroke-dasharray", "6,4")
            .style("opacity", 0)
            .style("filter", `drop-shadow(0 0 6px ${accent})`)
            .style("transition", "x1 0.5s cubic-bezier(0.4, 0, 0.2, 1), x2 0.5s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s");
    }
    
    animateToStep(step, speed = 1) {
        if (!this.svg) return;


        const barDur    = Math.max(100, Math.round(800  / speed));
        const cursorDur = Math.max(100, Math.round(600  / speed));
        const exitDur   = Math.max(100, Math.round(600  / speed));
        if (step < 0) {
            this.bars.forEach((bar) => {
                bar.transition()
                    .duration(exitDur)
                    .attr("width", 0)
                    .style("opacity", 0.3);
            });

            this.barLabels.forEach((lbl) => lbl.style("opacity", 0));

            this.icons.forEach((icon) => {
                icon.style("opacity", 0);
            });
            
            this.cursor.transition()
                .duration(cursorDur)
                .style("opacity", 0);
            
            return;
        }

        const isFinal = step === this.sequence.length;
        const activeIdx = isFinal ? -1 : step;

        // Animate bars, bar labels, and icons up to current step (or all bars on final frame)
        this.bars.forEach((bar, i) => {
            const seg     = this.sequence[i];
            const barPixW = this.xScale(seg.end) - this.xScale(seg.start);
            const isActive = !isFinal && i === activeIdx;

            if (isFinal || i <= step) {
                bar.transition()
                    .duration(barDur)
                    .attr("width", barPixW)
                    .style("opacity", isActive ? 1 : 0.82)
                    .attr("stroke",       isActive ? "#ffffff" : "none")
                    .attr("stroke-width", isActive ? 1.2 : 0);

                // Show label only if bar is wide enough to hold it (> 28px)
                const labelOpacity = barPixW > 28 ? (isActive ? 1 : 0.55) : 0;
                this.barLabels[i]
                    .style("opacity", labelOpacity)
                    .attr("font-size", isActive ? "11px" : "9px");
            } else {
                bar.transition()
                    .duration(exitDur)
                    .attr("width", 0)
                    .style("opacity", 0.2);

                this.barLabels[i].style("opacity", 0);
            }
        });

        this.icons.forEach((icon, i) => {
            icon.style("opacity", (isFinal || i <= step) ? 1 : 0);
        });
        
        // Move cursor: to end of timeline on final frame, otherwise to segment start
        const cursorX = isFinal
            ? this.xScale(this.totalTime)
            : this.xScale(this.sequence[step].start);

        this.cursor.transition()
            .duration(cursorDur)
            .style("opacity", 1)
            .attr("x1", cursorX)
            .attr("x2", cursorX);
    }
    
    resize() {
        // Handle window resize
        const container = document.getElementById(this.containerId);
        this.width = container.clientWidth - this.margin.left - this.margin.right - 48;
        
        this.xScale.range([0, this.width]);
        
        // Update axes
        this.svg.selectAll("g").remove();
        this.svg.selectAll("line").remove();
        
        // Reinitialize
        this.init();
    }
}