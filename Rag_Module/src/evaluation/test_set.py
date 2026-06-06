Networks_TEST_CASES = [
    {
        "level": 1,
        "question": 'What is an ARQ protocol?',
        "ground_truth": 'ARQ stands for Automatic Repeat reQuest. It is the class of protocols in which one side implements retransmit-on-timeout: if a packet is transmitted and no acknowledgment is received within the timeout interval, the packet is resent.',
    },
    {
        "level": 1,
        "question": 'What policy is used to build reliable transport on top of unreliable lower layers?',
        "ground_truth": 'A retransmit-on-timeout policy: a lost packet is detected by the absence of an acknowledgment within the timeout interval and is then resent. This is the basis of ARQ protocols.',
    },
    {
        "level": 1,
        "question": 'What is the self-clocking property of sliding windows?',
        "ground_truth": "ACKs return at exactly the rate at which the slowest (bottleneck) link delivers packets, so new packets are sent at an average rate matching the delivery rate. This self-clocking automatically reduces the sender's rate and thereby reduces congestion.",
    },
    {
        "level": 1,
        "question": 'What is the bottleneck link?',
        "ground_truth": 'The bottleneck link is the slowest link on the path; if several links tie for slowest, the first one is the bottleneck. It is the link where the queue forms.',
    },
    {
        "level": 2,
        "question": 'How does retransmit-on-duplicate differ from retransmit-on-timeout?',
        "ground_truth": 'Retransmit-on-timeout resends a packet when no acknowledgment arrives within the timeout interval (it is triggered by the absence of a response). Retransmit-on-duplicate instead resends the acknowledgment when a duplicate data packet is received (it is triggered by receiving a duplicate). At least one side must implement retransmit-on-timeout to avoid deadlock; the other side commonly implements retransmit-on-duplicate.',
    },
    {
        "level": 2,
        "question": 'In stop-and-wait, what must each side implement to avoid deadlock?',
        "ground_truth": 'At least one side must implement retransmit-on-timeout; otherwise a lost packet causes deadlock, with sender and receiver both waiting forever. The other side must implement at least one of retransmit-on-duplicate or retransmit-on-timeout (usually retransmit-on-duplicate alone). If both sides use retransmit-on-timeout with different timeout values, the protocol generally still works.',
    },
    {
        "level": 2,
        "question": 'How does window size relate to bottleneck link utilization in sliding windows?',
        "ground_truth": 'With winsize=1 you send 1 packet per RTT; with winsize=4 you average 4 packets per RTT. For a 6 packets/RTT link, winsize values of 1, 4 and 6 give bottleneck utilizations of 1/6, 4/6 and 6/6 = 100%. Ideally winsize equals bandwidth × RTT.',
    },
    {
        "level": 3,
        "question": 'Why is stop-and-wait inefficient, and how do sliding windows improve on it?',
        "ground_truth": 'Stop-and-wait sends one packet and then waits for its ACK, so most links on a multi-hop path sit idle; it is only efficient on a single LAN link with no intermediate switches or significant propagation delay. Sliding windows keep multiple packets (up to the window size) in transit at once, filling the pipe and raising throughput toward the bottleneck bandwidth.',
    },
    {
        "level": 3,
        "question": 'What happens to throughput, delay, and queue utilization when winsize exceeds the congestion knee?',
        "ground_truth": 'Beyond the knee (winsize = bandwidth × RTT_noLoad), throughput stays constant at the bottleneck bandwidth while delay and queue utilization increase linearly with winsize. Below the knee, throughput is proportional to winsize, delay is constant, and steady-state queue utilization is zero.',
    },
    {
        "level": 3,
        "question": "Why doesn't increasing the window size indefinitely keep increasing throughput?",
        "ground_truth": 'Once the window size exceeds the congestion knee, throughput is already limited by the bottleneck bandwidth. Increasing the window further only increases queue utilization and delay without increasing throughput.',
    },
    {
        "level": 4,
        "question": 'What timeout value should be used in an ARQ protocol?',
        "ground_truth": 'The chapter explains retransmit-on-timeout behavior but does not specify a particular timeout value or a formula for choosing one.',
    },
    {
        "level": 4,
        "question": 'What TCP congestion-window formula does this chapter give?',
        "ground_truth": 'The document does not give a TCP congestion-window formula. It covers stop-and-wait, sliding windows, the bottleneck link, and the congestion knee (winsize = bandwidth × RTT_noLoad); it only refers to TCP flow control in section 18.10.',
    },
    {
        "level": 4,
        "question": 'What encryption algorithm does this chapter recommend?',
        "ground_truth": 'The document does not discuss encryption. It is about reliable data transport, ARQ, and sliding windows.',
    },
    {
        "level": 5,
        "question": 'What does the acronym ARQ mean and how does the mechanism work?',
        "ground_truth": 'ARQ means Automatic Repeat reQuest. One side retransmits on timeout: if no acknowledgment arrives within the timeout interval, the packet is sent again.',
    },
    {
        "level": 5,
        "question": 'Which link on a path determines where packets queue up?',
        "ground_truth": 'The bottleneck (slowest) link; the queue forms there. If links tie for slowest, the first one is the bottleneck.',
    },
    {
        "level": 6,
        "question": 'How do you make data transport reliable?',
        "ground_truth": 'Build on a retransmit-on-timeout policy (ARQ): detect loss from missing ACKs within a timeout and resend. Stop-and-wait is the simplest reliable scheme; sliding windows add efficiency while keeping reliability.',
    },
    {
        "level": 7,
        "question": 'How do the bottleneck link, RTT_noLoad, and the ideal window size relate to each other?',
        "ground_truth": 'The bottleneck (slowest) link sets the maximum throughput and is where queueing occurs. RTT_noLoad is the round-trip time on an idle network. The ideal window size is the congestion knee, winsize = bandwidth × RTT_noLoad: there the pipe is full (100% bottleneck utilization) with zero steady-state queue, while any larger window only adds delay and queueing without increasing throughput.',
    },
]


OS_Threads_TEST_CASES = [
    {
        "level": 1,
        "question": 'What does a multithreaded process share among its threads, and what is private to each thread?',
        "ground_truth": 'Threads of a process share the code, data, and open files; each thread has its own registers and its own stack.',
    },
    {
        "level": 1,
        "question": "State Amdahl's Law for the speedup from adding processing cores.",
        "ground_truth": 'speedup ≤ 1 / (S + (1 − S)/N), where S is the fraction of the application that must run serially and N is the number of processing cores. For example, a 75% parallel / 25% serial application gets about 1.6× speedup on 2 cores and about 2.28× on 4 cores.',
    },
    {
        "level": 1,
        "question": 'What are the four major benefits of multithreaded programming?',
        "ground_truth": 'Responsiveness, resource sharing, economy, and scalability.',
    },
    {
        "level": 1,
        "question": 'Which functions create and wait for a thread in Pthreads and in the Windows API?',
        "ground_truth": 'In Pthreads, pthread_create() creates a thread and pthread_join() waits for it. In the Windows API, CreateThread() creates a thread.',
    },
    {
        "level": 2,
        "question": 'Describe the one-to-one threading model and its main drawback.',
        "ground_truth": 'The one-to-one model maps each user thread to a kernel thread. It gives more concurrency than the many-to-one model (another thread can run when one makes a blocking call) and allows parallelism on multiprocessors. Its drawback is that creating a user thread requires creating a kernel thread, so most implementations limit the number of threads.',
    },
    {
        "level": 2,
        "question": 'What is the two-level threading model?',
        "ground_truth": 'The two-level model is a variation of the many-to-many model: it multiplexes many user-level threads onto a smaller-or-equal number of kernel threads, but also allows a user-level thread to be bound to a kernel thread. The Solaris operating system used this model.',
    },
    {
        "level": 2,
        "question": 'What challenges do programmers face when designing applications for multicore systems?',
        "ground_truth": 'The challenges discussed include identifying tasks (finding areas that can be divided into independent concurrent tasks), balance (ensuring tasks perform work of equal value), and data splitting (dividing the data accessed by the tasks across cores).',
    },
    {
        "level": 3,
        "question": 'Why can the one-to-one model achieve greater concurrency than the many-to-one model?',
        "ground_truth": 'In the one-to-one model, each user thread maps to its own kernel thread. Therefore, when one thread blocks, another can continue executing, and threads can run in parallel on multiprocessors. In the many-to-one model, a blocking system call can block the entire process.',
    },
    {
        "level": 3,
        "question": 'Why does multithreading benefit a multicore system more than a single-core one?',
        "ground_truth": 'On a single core, threads only interleave through time-slicing (concurrency, not parallelism), and a single-threaded process can use just one processor no matter how many exist. On multiple cores, threads run in parallel on different cores, so multithreading scales — this is the scalability benefit.',
    },
    {
        "level": 3,
        "question": 'What is the difference between data parallelism and task parallelism?',
        "ground_truth": 'Data parallelism distributes subsets of the same data across multiple cores, each performing the same operation; task parallelism distributes distinct tasks (threads) across cores. In practice most applications use a hybrid of the two.',
    },
    {
        "level": 3,
        "question": 'How do user threads and kernel threads differ in how they are supported?',
        "ground_truth": 'User threads are supported above the kernel and are managed without kernel support; kernel threads are supported and managed directly by the operating system. Multithreading models (many-to-one, one-to-one, many-to-many) describe how user threads are mapped onto kernel threads.',
    },
    {
        "level": 4,
        "question": 'How many kernel threads are created by default when a process starts?',
        "ground_truth": 'The chapter does not specify a default number of kernel threads created when a process starts.',
    },
    {
        "level": 4,
        "question": 'What CPU scheduling algorithm does Linux use, according to this chapter?',
        "ground_truth": "This chapter (Chapter 4, Threads) does not specify Linux's CPU scheduling algorithm — CPU scheduling is covered in Chapter 6. It only discusses thread support and notes that Windows uses the one-to-one model.",
    },
    {
        "level": 4,
        "question": 'How many threads does a thread pool create by default?',
        "ground_truth": 'The document does not state a default thread-pool size. It says the number of threads can be set heuristically based on factors such as the number of CPUs and the amount of physical memory.',
    },
    {
        "level": 5,
        "question": 'Which resources are common to all threads of a process, and which are per-thread?',
        "ground_truth": 'Code, data, and open files are shared by all threads of the process; the registers and the stack are private to each thread.',
    },
    {
        "level": 5,
        "question": 'Write the formula that bounds the speedup obtained by adding cores.',
        "ground_truth": "Amdahl's Law: speedup ≤ 1 / (S + (1 − S)/N), with S the serial fraction and N the number of cores.",
    },
    {
        "level": 6,
        "question": 'What is implicit threading?',
        "ground_truth": 'Implicit threading moves the creation and management of threads from application developers to compilers and run-time libraries. Approaches include thread pools, OpenMP, and Grand Central Dispatch (GCD).',
    },
    {
        "level": 7,
        "question": 'How do thread pools and OpenMP each manage concurrency, and what do they have in common?',
        "ground_truth": 'Both are implicit-threading approaches that offload thread management from the developer. A thread pool creates a number of threads at startup and reuses them to service requests, which is faster than creating a thread per request and bounds the total thread count. OpenMP is a set of compiler directives (e.g. #pragma omp parallel for) that parallelize regions of code across a team of threads, with control over the number of threads and over which data are shared or private. In common, both let the developer express parallelism while the library/runtime handles the thread lifecycle.',
    },
]


def get_test_cases(dataset="networks", levels=None):
    """dataset: "networks" | "os_threads".  Optional level filter."""
    mapping = {
        "networks":   Networks_TEST_CASES,
        "os_threads": OS_Threads_TEST_CASES,
    }
    cases = mapping.get(dataset, Networks_TEST_CASES)
    if levels:
        return [c for c in cases if c.get("level") in levels]
    return cases


TEST_CASES = Networks_TEST_CASES
