export class DataLoader {
    constructor() {
        this.supportedFormats = ['json'];
    }
    
    loadFromFile(file, callback) {
        const reader = new FileReader();
        
        reader.onload = (e) => {
            try {
                const data = JSON.parse(e.target.result);
                const validatedData = this.validateData(data);
                callback(validatedData);
            } catch (error) {
                alert('Error loading file: ' + error.message);
            }
        };
        
        reader.readAsText(file);
    }
    
    loadFromUrl(url, callback) {
        fetch(url)
            .then(response => response.json())
            .then(data => {
                const validatedData = this.validateData(data);
                callback(validatedData);
            })
            .catch(error => {
                alert('Error loading from URL: ' + error.message);
            });
    }
    
    validateData(data) {
        // Check required fields
        if (!data.processes || !Array.isArray(data.processes)) {
            throw new Error('Data must contain a "processes" array');
        }
        
        if (!data.quantum || typeof data.quantum !== 'number') {
            throw new Error('Data must contain a "quantum" number');
        }
        
        // Validate each process
        const colors = ['#4285F4', '#0F9D58', '#F4B400', '#DB4437', '#AA46BB', '#FF6D00', '#00ACC1', '#E91E63'];
        
        data.processes.forEach((p, index) => {
            if (!p.id) p.id = `P${index + 1}`;
            if (!p.arrival && p.arrival !== 0) throw new Error(`Process ${p.id} missing arrival time`);
            if (!p.burst) throw new Error(`Process ${p.id} missing burst time`);
            
            // Assign color if not provided
            if (!p.color) {
                p.color = colors[index % colors.length];
            }
        });
        
        return data;
    }
}