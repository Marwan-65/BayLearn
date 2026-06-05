SRC = scheduler
Q ?= 3
SCH ?= 2
INPUT ?= processes.txt

#complie each source file into the .out executables.
build:
	gcc $(SRC)/process_generator.c -o $(SRC)/process_generator.out
	gcc $(SRC)/clk.c -o $(SRC)/clk.out
	gcc $(SRC)/scheduler.c -o $(SRC)/scheduler.out
	gcc $(SRC)/process.c -o $(SRC)/process.out
	gcc $(SRC)/test_generator.c -o $(SRC)/test_generator.out

#used to dlete all the generated binaries after we are done
clean:
	rm -f $(SRC)/*.out

# same as clean but also delete the process file so we start over
clean-all: clean
	rm -f $(SRC)/processes.txt


all: clean build

# keyfile-> ipc signal file
run:
	cd $(SRC) && touch keyfile && ./process_generator.out $(INPUT) -sch $(SCH) -q $(Q) || true

#pkill 9 force kills all theses scheduler related processes
#ipcs m to list all shared memory segments, awk to extract the segment id, xargs to pass this value to ipcrm to remove it
#ipcs q is the same but for message (Q)ueues
stop:
	-pkill -9 -f "process_generator.out|scheduler.out|clk.out|process.out"
	-ipcs -m | awk 'NR>3{print $$2}' | xargs -r ipcrm -m
	-ipcs -q | awk 'NR>3{print $$2}' | xargs -r ipcrm -q

# translate the c scheduler output logs into the visualizer's JSON format.
# run this after `make run` completes.
# pass Q=something to override the quantum (default 3).
translate:
	python3 scripts/log_to_json.py -q $(Q) -sch $(SCH)

#the full pipeline
simulate: build stop run translate
