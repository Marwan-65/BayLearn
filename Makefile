#  We use `conda run -n <env>` so no manual `conda activate` is needed.
#       make all           # Full system
#       make stop          # stop everything started in the background
#       make rag           # RAG/orchestrator backend  :8000
#       make frontend      # main React frontend        :5173
#       make minimal       # parser + RAG backend + main frontend


#  Conda environments (edit to match `conda env list you have` if you are a developer but users just run make all) 
RAG_ENV       ?= mini-rag-app
PARSER_ENV    ?= baylearn-parsing
EQUATION_ENV  ?= baylearn-equation
ADAPTIVE_ENV  ?= baylearn-adaptive
QUESTION_ENV  ?= baylearn-qg
CONDA_RUN      = conda run --no-capture-output -n

#  Python version per env (their deps conflict; one env each) 
RAG_PY        ?= 3.12
PARSER_PY     ?= 3.11
EQUATION_PY   ?= 3.11
ADAPTIVE_PY   ?= 3.11
QUESTION_PY   ?= 3.11

#  Ports (single source of truth)
RAG_PORT       ?= 8000
PARSER_PORT    ?= 8100
ADAPTIVE_PORT  ?= 8002
QUESTION_PORT  ?= 8001
EQUATION_PORT  ?= 9001
FRONTEND_PORT  ?= 5173
LINKED_LIST_UI ?= 8081
SCHEDULAR_UI   ?= 8082
BTREE_UI       ?= 8083

#  Equation module paths (launch commands per your spec). Edit if the folder
#  layout differs (this repo currently ships src/baylearn + src/baylearn-frontend).
EQUATION_DIR   ?= Equation_Solving_Module
EQUATION_UI    ?= $(EQUATION_DIR)/src/ui

ROOT  := $(shell pwd)
LOGS  := $(ROOT)/.run-logs
PIDS  := $(ROOT)/.run-pids
STAMP := $(ROOT)/.run-stamps

.DEFAULT_GOAL := help


# stamp file records that an env is ready; it depends on that module's requirements.txt file
# so nothing will be updated unless requirements.txt changes.

$(STAMP):
	@mkdir -p $(STAMP)

# ensure-env,<env>,<python-version>  -> create the conda env iff it does not exist
define ensure_env
	@conda env list | awk '{print $$1}' | grep -qx "$(1)" \
	  || { echo "creating conda env $(1) (python $(2))"; conda create -n $(1) python=$(2) -y; }
endef

$(STAMP)/rag: Rag_Module/src/requirements.txt | $(STAMP)
	$(call ensure_env,$(RAG_ENV),$(RAG_PY))
	$(CONDA_RUN) $(RAG_ENV) pip install -r $<
	@touch $@

$(STAMP)/parser: Input-Parsing-Module/requirements.txt | $(STAMP)
	$(call ensure_env,$(PARSER_ENV),$(PARSER_PY))
	$(CONDA_RUN) $(PARSER_ENV) pip install -r $<
	@touch $@

$(STAMP)/equation: equation-module/requirements.txt | $(STAMP)
	$(call ensure_env,$(EQUATION_ENV),$(EQUATION_PY))
	$(CONDA_RUN) $(EQUATION_ENV) pip install -r $<
	@touch $@

$(STAMP)/equation-frontend: $(EQUATION_UI)/package.json | $(STAMP)
	cd $(EQUATION_UI) && npm install
	@touch $@

$(STAMP)/adaptive: Adaptive-Learning-Module/requirements.txt | $(STAMP)
	$(call ensure_env,$(ADAPTIVE_ENV),$(ADAPTIVE_PY))
	$(CONDA_RUN) $(ADAPTIVE_ENV) pip install -r $<
	@touch $@

$(STAMP)/questions: question-generation-module/requirements.txt | $(STAMP)
	$(call ensure_env,$(QUESTION_ENV),$(QUESTION_PY))
	$(CONDA_RUN) $(QUESTION_ENV) pip install -r $<
	@touch $@

$(STAMP)/frontend: Frontend/package.json | $(STAMP)
	cd Frontend && npm install
	@touch $@

.PHONY: setup setup-minimal
setup-minimal: $(STAMP)/parser $(STAMP)/rag $(STAMP)/frontend ## Install the 3 RAG-demo modules
	@echo "RAG-demo environments ready."
setup: $(STAMP)/rag $(STAMP)/parser $(STAMP)/equation-frontend $(STAMP)/adaptive $(STAMP)/questions $(STAMP)/frontend 
	@echo "All environments ready." 


# run one service in the current terminal tab
.PHONY: rag
rag: # RAG backend :8000
	cd Rag_Module/src && $(CONDA_RUN) $(RAG_ENV) uvicorn main:app --reload --port $(RAG_PORT)

.PHONY: parser
parser: # Input-Parsing backend :8100
	cd Input-Parsing-Module && $(CONDA_RUN) $(PARSER_ENV) uvicorn app.main:app --port $(PARSER_PORT)

.PHONY: equation-api
equation-api: # Equation backend :9001
	cd $(EQUATION_DIR) && $(CONDA_RUN) $(EQUATION_ENV) uvicorn src.api:app --reload --port $(EQUATION_PORT)

.PHONY: equation-frontend
equation-frontend: # Equation UI (Vite dev)
	cd $(EQUATION_UI) && npm run dev

.PHONY: adaptive
adaptive: # Adaptive-learning backend (Flask) :8002  
	cd Adaptive-Learning-Module && $(CONDA_RUN) $(ADAPTIVE_ENV) flask --app app.backend run --port $(ADAPTIVE_PORT)

.PHONY: questions
questions: # Question-generation backend :8001  
	cd question-generation-module && $(CONDA_RUN) $(QUESTION_ENV) uvicorn app.main:app --port $(QUESTION_PORT)

.PHONY: visualizer
visualizer: ## Start visualizer UIs
	@echo "Starting all visualizers..."
	$(call bg,linkedlist,"Visualizer/Linked_List_Animation",python3 -m http.server $(LINKED_LIST_UI))
	$(call bg,scheduler,"Visualizer/Scheduler_Animation/visualizer",python3 -m http.server $(SCHEDULAR_UI))
	$(call bg,btree,"Visualizer/btree-visualizer",python3 -m http.server $(BTREE_UI))

.PHONY: frontend
frontend: # Main frontend :5173
	cd Frontend && npm run dev -- --port $(FRONTEND_PORT)

#  Background groups of services with logs
$(LOGS):
	@mkdir -p $(LOGS)

# Internal helper: $(call bg,<name>,<dir>,<command>)
define bg
	@echo "starting $(1) ... (log: $(LOGS)/$(1).log)"
	@cd $(2) && nohup bash -c 'exec $(3)' > $(LOGS)/$(1).log 2>&1 & echo $$! >> $(PIDS)
endef

.PHONY: check-node
check-node:
	@required=$$(cat .nvmrc); \
	current=$$(node -v | sed 's/v//'); \
	echo "Required Node: $$required | Current Node: $$current"; \
	node -e "\
	const cur = process.argv[2].split('.').map(Number);\
	const req = process.argv[1].split('.').map(Number);\
	for (let i = 0; i < 3; i++) {\
	  if (cur[i] > req[i]) process.exit(0);\
	  if (cur[i] < req[i]) {\
	    console.error('\n Node version incompatible');\
	    console.error(' Required: ' + process.argv[1]);\
	    console.error(' Current: ' + process.argv[2]);\
	    console.error('\nFix: nvm install ' + process.argv[1] + ' && nvm use ' + process.argv[1]);\
	    process.exit(1);\
	  }\
	}" $$required $$current

.PHONY: minimal
minimal: check-node setup-minimal $(LOGS) 
	@rm -f $(PIDS) 
	$(call bg,parser,Input-Parsing-Module,$(CONDA_RUN) $(PARSER_ENV) uvicorn app.main:app --port $(PARSER_PORT))
	$(call bg,rag,Rag_Module/src,$(CONDA_RUN) $(RAG_ENV) uvicorn main:app --port $(RAG_PORT))
	$(call bg,frontend,Frontend,npm run dev -- --port $(FRONTEND_PORT))
	@echo ""
	@echo "RAG demo up.  Open  http://localhost:$(FRONTEND_PORT)"
	@echo "Logs: $(LOGS)/   |   Stop: make stop"

.PHONY: all
all: check-node setup $(LOGS)
	@rm -f $(PIDS)
	$(call bg,parser,Input-Parsing-Module,$(CONDA_RUN) $(PARSER_ENV) uvicorn app.main:app --port $(PARSER_PORT))
	$(call bg,rag,Rag_Module/src,$(CONDA_RUN) $(RAG_ENV) uvicorn main:app --port $(RAG_PORT))
	$(call bg,equation-api,$(EQUATION_DIR),$(CONDA_RUN) $(EQUATION_ENV) uvicorn src.api:app --reload --port $(EQUATION_PORT))
	$(call bg,equation-frontend,$(EQUATION_UI),npm run dev)
	$(call bg,adaptive,Adaptive-Learning-Module,$(CONDA_RUN) $(ADAPTIVE_ENV) flask --app app.backend run --port $(ADAPTIVE_PORT))
	$(call bg,questions,question-generation-module,$(CONDA_RUN) $(QUESTION_ENV) uvicorn app.main:app --port $(QUESTION_PORT))
	$(call bg,linkedlist,Visualizer/Linked_List_Animation,python3 -m http.server $(LINKED_LIST_UI))
	$(call bg,scheduler,Visualizer/Scheduler_Animation/visualizer,python3 -m http.server $(SCHEDULAR_UI))
	$(call bg,btree,Visualizer/btree-visualizer,python3 -m http.server $(BTREE_UI))
	$(call bg,frontend,Frontend,npm run dev -- --port $(FRONTEND_PORT))
	@echo ""
	@echo "Full system up.  Open  http://localhost:$(FRONTEND_PORT)"
	@echo "    Logs: $(LOGS)/   |   Stop: make stop"


.PHONY: stop
stop:
	@echo "Stopping tracked PIDs..."
	@if [ -f $(PIDS) ]; then \
	  while read pid; do \
	    echo "killing $$pid"; \
	    kill -9 $$pid 2>/dev/null || true; \
	  done < $(PIDS); \
	  rm -f $(PIDS); \
	fi

	@echo "Killing by ports (hard cleanup)..."
	@for port in $(RAG_PORT) $(PARSER_PORT) $(FRONTEND_PORT) \
		$(ADAPTIVE_PORT) $(QUESTION_PORT) \
		$(LINKED_LIST_UI) $(SCHEDULAR_UI) $(BTREE_UI); do \
	  lsof -ti :$$port | xargs kill -9 2>/dev/null || true; \
	done

	@echo "Done"

.PHONY: logs
logs: # Tail all background logs
	@tail -n 20 -f $(LOGS)/*.log


#  Setup / help
.PHONY: install-frontend
install-frontend: ## npm install for the main frontend
	cd Frontend && npm install

.PHONY: help
help: ## Show this help
	@echo "BayLearn — run targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Typical: 'make minimal' then open http://localhost:$(FRONTEND_PORT)"
