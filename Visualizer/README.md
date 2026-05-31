
### Prerequisites
1. Ensure **Docker Desktop** is open and running in the background.
2. Ensure you have your `.env` files set up in both `Input-Parsing-Module` (with `DATABASE_URL`) and `Visualizer/Parser` (with `GEMINI_API_KEY`).

---

### Step 1: Start the Backend APIs
You need to start the two Python servers that handle PDF extraction and LLM orchestration. Open two separate terminals:

**Terminal 1 (Input Parsing Module):**
```bash
cd "Input-Parsing-Module"
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 (Transform & Orchestration API):**
```bash
cd "Visualizer/Parser"
uvicorn transform_api:app --reload --port 8010
```

---

### Step 2: Start the Visualizer Frontends
You need to serve the static HTML web pages for the three animations. Open three more terminals:

**Terminal 3 (Linked List UI):**
```bash
cd "Visualizer/Linked List Animation"
python -m http.server 8081
```

**Terminal 4 (Scheduler UI):**
```bash
cd "Visualizer/Scheduler Animation/visualizer"
python -m http.server 8082
```

**Terminal 5 (B-Tree UI):**
```bash
cd "Visualizer/btree-visualizer"
python -m http.server 8083
```

---

### Step 3: Trigger the Automated Pipeline!
Once all 5 terminals are running, you can ingest any document. Open a final terminal and run:

```bash
cd "Visualizer/Parser"
curl -X POST "http://localhost:8010/v1/ingest-launch" -F "file=@your-test-file.pdf"
```

The system will automatically:
1. Parse the PDF and save it to PostgreSQL.
2. Send the text to Gemini to classify the algorithm and extract the scenario.
3. Automatically boot up the C-Simulation Docker container (for Scheduler).
4. Save the generated JSON files directly into the frontend directories.
5. Return a `viewer_url` (e.g., `http://localhost:8082?run_id=...`) that you can click to view the immediately updated animation!