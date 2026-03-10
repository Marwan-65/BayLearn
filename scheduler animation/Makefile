SRC = scheduler

build:
	gcc $(SRC)/process_generator.c -o $(SRC)/process_generator.out
	gcc $(SRC)/clk.c -o $(SRC)/clk.out
	gcc $(SRC)/scheduler.c -o $(SRC)/scheduler.out
	gcc $(SRC)/process.c -o $(SRC)/process.out
	gcc $(SRC)/test_generator.c -o $(SRC)/test_generator.out

clean:
	rm -f $(SRC)/*.out $(SRC)/processes.txt

all: clean build

run:
	cd $(SRC) && touch keyfile && ./process_generator.out processes.txt -sch 2 -q 3

stop:
	-pkill -9 -f "process_generator.out|scheduler.out|clk.out|process.out"
	-ipcs -m | awk 'NR>3{print $$2}' | xargs -r ipcrm -m
	-ipcs -q | awk 'NR>3{print $$2}' | xargs -r ipcrm -q

# Translate the C scheduler's output logs into the visualizer's JSON format.
# Run this after `make run` completes.
# Pass Q=<value> to override the quantum (default 3).
Q ?= 3
translate:
	python3 scripts/log_to_json.py -q $(Q)
