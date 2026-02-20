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

- If you are MAC M series use this after requirements.txt for GPU acceleration

```bash
   $ CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python==0.3.16 --force-reinstall --no-cache-dir
```

- Note : langchain 0.2.16 requires numpy < 2.0 so make sure

```bash
   $ pip show numpy langchain llama-cpp-python
```

- set up the environment variables

```bash
   $ cp .env.example into .env
```

- To run the app

```bash
   $ uvicorn main:app --reload --host 0.0.0.0 --port 3000
```

- Local LLM Setup (Required)

* This project uses local GGUF models via llama-cpp.

1- Install Hugging Face CLI

```bash
   $ pip install huggingface-hub
```

2- Login to Hugging Face
huggingface-cli login and Paste your access token.

3- Download Mistral 7B (Q4_K_M)

```bash
huggingface-cli download TheBloke/Mistral-7B-Instruct-v0.1-GGUF \
mistral-7b-instruct-v0.1.Q4_K_M.gguf \
--local-dir models \
--local-dir-use-symlinks False
```

3- The model file must exist inside:
project_root/models/
