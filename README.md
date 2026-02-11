## RAG-Module

### Requirements:

- python 3.12 or later

#### Intialize conda environment

- create the conda environment

```bash
    $ conda create -n mini-rag-app
```

- activate it

```bash
    $ conda activate mini-rag-app
```

#### Installation

- Install the required packages

```bash
   $ pip install -r requirements.txt
```

- set up the environment variables

```bash
   $ cp .env.example into .env
```

- To run the app

```bash
   $ uvicorn main:app --reload --host 0.0.0.0 --port 3000
```
