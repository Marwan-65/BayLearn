//el file el byload el data
export class DataLoader {
    constructor() {
        this.supportedFormats = ['json'];
    }
    //by load ashkal mo5talefa hena el file
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
    //hena from url
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
    //ba3deen byvalidate enaha sa7
    validateData(data) {
        // Check required fields
        if (!data.processes || !Array.isArray(data.processes)) {
            throw new Error('Data must contain a "processes" array');
        }

        // Quantum is required for RR/MLQ runs, optional otherwise.
        if (data.quantum !== undefined && typeof data.quantum !== 'number') {
            throw new Error('If provided, "quantum" must be a number');
        }

        if (!data.algorithm || typeof data.algorithm !== 'object') {
            data.algorithm = { key: 'rr', name: 'Round Robin', shortName: 'RR' };
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

        if (data.quantum === undefined) {
            data.quantum = 0;
        }
        
        return data;
    }
}