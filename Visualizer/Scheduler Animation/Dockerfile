FROM ubuntu:22.04

# Install toolchain needed by the existing Makefile workflow.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        make \
        python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Default command runs build + scheduler + JSON translation.
# SCH values: 0=SJF, 1=HPF, 2=RR, 3=MLQ
CMD ["bash", "-lc", "make build && make run SCH=${SCH:-2} Q=${Q:-3} && python3 scripts/log_to_json.py -sch ${SCH:-2} -q ${Q:-3}"]
