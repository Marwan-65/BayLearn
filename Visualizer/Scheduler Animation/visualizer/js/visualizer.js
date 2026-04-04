// Icon and tooltip label for each end-of-bar reason code.
const END_REASON = {
    'QUANTUM_EXPIRE':                  { icon: '⏱', label: 'Quantum expired — preempted, sent to back of queue' },
    'QUANTUM_EXPIRE+DEMOTED':          { icon: '⏱↓', label: 'Quantum expired — demoted one priority level' },
    'QUANTUM_EXPIRE+STARVATION_RESET': { icon: '⏱↺', label: 'Quantum expired — starvation reset: all processes moved to level 0' },
    'PREEMPTED_BY_HIGHER_PRIORITY':    { icon: '▶', label: 'Preempted — higher-priority process arrived' },
    'COMPLETED':                       { icon: '✓', label: 'Process completed — burst fully consumed' },
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
        this.bars = [];
        this.icons = [];
        
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
        
        // Create bars and end-of-bar annotation icons
        this.bars = [];
        this.icons = [];
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

            // End-of-bar icon — sits just to the right of the bar's right edge
            const reason = END_REASON[d.endReason];
            const iconText = this.svg.append("text")
                .attr("x", this.xScale(d.end) + 3)
                .attr("y", this.yScale(d.id) + this.yScale.bandwidth() / 2)
                .attr("dominant-baseline", "middle")
                .attr("font-size", "11px")
                .attr("font-family", "sans-serif")
                .attr("fill", "#4a5a6e")
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
    
    animateToStep(step) {
        if (!this.svg) return;
        
        if (step < 0) {
            // Reset all bars and icons
            this.bars.forEach((bar) => {
                bar.transition()
                    .duration(600)
                    .attr("width", 0)
                    .style("opacity", 0.3);
            });

            this.icons.forEach((icon) => {
                icon.style("opacity", 0);
            });
            
            this.cursor.transition()
                .duration(600)
                .style("opacity", 0);
            
            return;
        }
        
        // Animate bars and icons up to current step
        this.bars.forEach((bar, i) => {
            if (i <= step) {
                bar.transition()
                    .duration(800)
                    .attr("width", this.xScale(this.sequence[i].end) - this.xScale(this.sequence[i].start))
                    .style("opacity", i === step ? 1 : 0.82)
                    .attr("stroke", i === step ? "#ffffff" : "none")
                    .attr("stroke-width", i === step ? 1.2 : 0);
            } else {
                bar.transition()
                    .duration(600)
                    .attr("width", 0)
                    .style("opacity", 0.2);
            }
        });

        this.icons.forEach((icon, i) => {
            icon.style("opacity", i <= step ? 1 : 0);
        });
        
        // Move cursor
        if (step >= 0) {
            this.cursor.transition()
                .duration(600)
                .style("opacity", 1)
                .attr("x1", this.xScale(this.sequence[step].start))
                .attr("x2", this.xScale(this.sequence[step].start));
        }
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