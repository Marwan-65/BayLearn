# Test set for RAG evaluation
# ground_truth = the correct answer YOU write, not the RAG's answer
# Each case has a "level" field for filtering:
#   1 = Direct Lookup
#   2 = Synthesis (combine info from one section)
#   3 = Reasoning (infer from context)
#   4 = Negative / Hallucination Resistance
#   5 = Paraphrase (same question, different wording)
#   6 = Ambiguous (partially answerable)
#   7 = Multi-hop (requires info from multiple sections/chunks)

# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT: Algorithms-JeffE.pdf  (Chapters 1–3)
# Upload this PDF before running evaluation.
# Download free from: jeffe.cs.illinois.edu/teaching/algorithms/
# ─────────────────────────────────────────────────────────────────────────────
Scientific_TEST_CASES = [

    # ── LEVEL 1: Direct Lookup ──────────────────────────────────────────────
    {
        "level": 1,
        "question": "What is the recurrence relation for the Tower of Hanoi problem?",
        "ground_truth": (
            "Let T(n) denote the number of moves to transfer n disks. "
            "The recurrence is T(0) = 0 and T(n) = 2T(n-1) + 1 for n >= 1. "
            "The closed-form solution is T(n) = 2^n - 1."
        )
    },
    {
        "level": 1,
        "question": "What is the time complexity of MergeSort?",
        "ground_truth": (
            "MergeSort runs in O(n log n) time. "
            "Its recurrence is T(n) = 2T(n/2) + O(n), "
            "where the O(n) term comes from the Merge step, "
            "which is a simple for-loop with constant work per iteration."
        )
    },
    {
        "level": 1,
        "question": "What is the Fibonacci recurrence as defined in the book?",
        "ground_truth": (
            "The Fibonacci recurrence is: F(0) = 0, F(1) = 1, "
            "and F(n) = F(n-1) + F(n-2) for n >= 2. "
            "The book notes this originally appeared in 7th-century Indian mathematics "
            "as M(n) = M(n-2) + M(n-1) for counting poetic meters."
        )
    },
    {
        "level": 1,
        "question": "Who developed MergeSort and when?",
        "ground_truth": (
            "MergeSort was developed by John von Neumann in 1945, "
            "and described in detail in a publication with Herman Goldstine in 1947 "
            "as one of the first non-numerical programs for the EDVAC."
        )
    },
    {
        "level": 1,
        "question": "What are the three types of edit operations in edit distance?",
        "ground_truth": (
            "The three operations are: letter insertion, letter deletion, "
            "and letter substitution. The edit distance between two strings is "
            "the minimum number of such operations required to transform one string into the other. "
            "For example, the edit distance between FOOD and MONEY is 4."
        )
    },
    {
        "level": 1,
        "question": "What is memoization and who coined the term?",
        "ground_truth": (
            "Memoization is an optimization technique where a recursive algorithm "
            "stores (caches) the result of each subproblem the first time it is computed, "
            "so subsequent calls return the cached result instead of recomputing. "
            "The technique is usually credited to Donald Michie in 1967, "
            "though Arthur Samuel proposed essentially the same idea in 1959. "
            "Note: the word is spelled without an R — 'memoization', not 'memorization'."
        )
    },

    # ── LEVEL 2: Synthesis ──────────────────────────────────────────────────
    {
        "level": 2,
        "question": "Explain the three steps of the MergeSort algorithm?",
        "ground_truth": (
            "1. Divide the input array into two subarrays of roughly equal size. "
            "2. Recursively mergesort each of the two subarrays. "
            "3. Merge the newly-sorted subarrays into a single sorted array. "
            "The Merge step does the real work and takes O(n) time. "
            "The base case is an array of size 1 or less, which is already sorted."
        )
    },
    {
        "level": 2,
        "question": "How does the book define 'good' and 'bad' states in the Game Tree algorithm?",
        "ground_truth": (
            "A game state is GOOD if either: (a) the current player has already won, "
            "or (b) the current player can move to a BAD state for the opposing player. "
            "A game state is BAD if either: (a) the current player has already lost, "
            "or (b) every available move leads to a GOOD state for the opposing player. "
            "Equivalently, a non-leaf node is good if it has at least one bad child, "
            "and bad if all its children are good."
        )
    },
    {
        "level": 2,
        "question": "What is the six-step pattern for designing dynamic programming algorithms as described in the book?",
        "ground_truth": (
            "The book's DP pattern (Section 3.4/3.5) has six steps: "
            "(a) Identify the subproblems — what recursive calls does your algorithm make? "
            "(b) Choose a memoization data structure, usually a multidimensional array. "
            "(c) Identify dependencies — which subproblems does each entry depend on? "
            "(d) Find a good evaluation order so each subproblem is solved after its dependencies. "
            "(e) Analyze space and running time based on the number of distinct subproblems. "
            "(f) Write down the algorithm as nested for-loops over your data structure."
        )
    },
    {
        "level": 2,
        "question": "How does the backtracking SubsetSum algorithm work and what is its time complexity?",
        "ground_truth": (
            "SubsetSum(X, T) asks: does any subset of X sum to T? "
            "It picks any element x from X and makes two recursive calls: "
            "SubsetSum(X\\{x}, T-x) — include x — and SubsetSum(X\\{x}, T) — exclude x. "
            "Base cases: return True if T=0; return False if T<0 or X is empty. "
            "Using the array form SubsetSum(X, i, T), the recurrence is T(n) <= 2T(n-1) + O(1), "
            "giving T(n) = O(2^n) in the worst case."
        )
    },

    # ── LEVEL 3: Reasoning ──────────────────────────────────────────────────
    {
        "level": 3,
        "question": "Why is the naive recursive Fibonacci algorithm exponentially slow?",
        "ground_truth": (
            "The naive RecFibo(n) recomputes the same subproblems repeatedly. "
            "A single call to RecFibo(n) triggers one call to RecFibo(n-1), "
            "two calls to RecFibo(n-2), three calls to RecFibo(n-3), and so on. "
            "The number of calls T(n) satisfies T(n) = T(n-1) + T(n-2) + 1, "
            "which gives T(n) = 2*F(n+1) - 1 = O(phi^n) where phi ≈ 1.618 is the golden ratio. "
            "So computing F(n) takes time proportional to F(n) itself — exponential in n."
        )
    },
    {
        "level": 3,
        "question": "Why does the book say 'Greed is Stupid' as a warning in the dynamic programming chapter?",
        "ground_truth": (
            "Section 3.5 warns that greedy algorithms — which make locally optimal decisions "
            "without solving recursive subproblems — seem appealing but usually fail "
            "to find the globally optimal solution. "
            "Unlike dynamic programming, which systematically considers all subproblems, "
            "a greedy approach may commit to a decision early that prevents finding the best answer. "
            "The book uses this warning to caution students against using greedy when the "
            "problem actually requires DP. Only if we are 'incredibly lucky' can we bypass "
            "recurrences and use a greedy approach correctly."
        )
    },
    {
        "level": 3,
        "question": "How does memoization transform the exponential Fibonacci algorithm into a linear one?",
        "ground_truth": (
            "Memoization stores each computed Fibonacci value in an array F[]. "
            "Before computing F(n), MemFibo checks if F[n] is already defined and returns it if so. "
            "This ensures each value F(i) is computed exactly once. "
            "Tracing through MemFibo reveals that the array is filled bottom-up: "
            "F[2] first, then F[3], ..., up to F[n]. "
            "Each entry requires O(1) work, so the total time is O(n) with O(n) space. "
            "This is an exponential improvement over the O(phi^n) naive algorithm."
        )
    },

    # ── LEVEL 4: Negative — Hallucination Resistance ────────────────────────
    {
        "level": 4,
        "question": "What is the exact number of solutions to the 8 queens problem according to the book?",
        "ground_truth": (
            "The book states that Carl Friedrich Gauss mentioned in an 1850 letter that one could "
            "confirm Franz Nauck's claim that the Eight Queens problem has 92 solutions. "
            "The book does not independently verify or derive this number itself."
        )
    },
    {
        "level": 4,
        "question": "Does the book provide an O(n log n) algorithm for Longest Increasing Subsequence?",
        "ground_truth": (
            "In Chapters 1-3, the book presents O(n^2) dynamic programming algorithms for LIS "
            "(both the LISbigger and LISfirst approaches). "
            "The book does not present an O(n log n) LIS algorithm in these chapters."
        )
    },
    {
        "level": 4,
        "question": "What programming language does the book use for its pseudocode?",
        "ground_truth": (
            "The book does not use any specific programming language. "
            "It uses abstract pseudocode with a notation similar to mathematical logic. "
            "The book explicitly states that algorithms are abstract mechanical procedures "
            "that can be implemented in any programming language, "
            "and that idiosyncratic syntactic details of any particular language are irrelevant."
        )
    },

    # ── LEVEL 5: Paraphrase ─────────────────────────────────────────────────
    {
        "level": 5,
        "question": "What recurrence describes the number of disk moves needed in Towers of Hanoi?",
        "ground_truth": (
            "Let T(n) be the number of moves for n disks. T(0)=0 and T(n) = 2T(n-1) + 1. "
            "Solving this recurrence gives T(n) = 2^n - 1."
        )
    },
    {
        "level": 5,
        "question": "How does the iterative Fibonacci algorithm IterFibo work?",
        "ground_truth": (
            "IterFibo replaces the memoized recursion with a simple for-loop that fills "
            "an array F[] deliberately from the bottom up: F[0]=0, F[1]=1, "
            "then for i from 2 to n: F[i] = F[i-1] + F[i-2]. "
            "It returns F[n]. This uses O(n) additions and O(n) space. "
            "It is the book's first explicit dynamic programming algorithm."
        )
    },
    {
        "level": 5,
        "question": "How does divide and conquer apply to sorting?",
        "ground_truth": (
            "MergeSort applies divide and conquer to sorting: it divides the array in half, "
            "recursively sorts each half (delegating to the Recursion Fairy), "
            "then merges the two sorted halves. "
            "The recurrence T(n) = 2T(n/2) + O(n) solves to O(n log n)."
        )
    },

    # ── LEVEL 6: Ambiguous ──────────────────────────────────────────────────
    {
        "level": 6,
        "question": "Is dynamic programming always better than backtracking?",
        "ground_truth": (
            "Not necessarily. Dynamic programming improves over backtracking when a problem "
            "has overlapping subproblems — the same recursive calls appear multiple times. "
            "DP memoizes results to avoid recomputation, giving polynomial time instead of "
            "exponential. However, DP requires identifying a polynomial number of distinct "
            "subproblems and a valid evaluation order. For problems without overlapping "
            "subproblems, backtracking may be equally efficient. "
            "The book also notes that if we are lucky a greedy algorithm may suffice, "
            "which is even simpler than DP."
        )
    },
    {
        "level": 6,
        "question": "What does the Recursion Fairy represent in the book?",
        "ground_truth": (
            "The Recursion Fairy is a metaphor the book uses to help understand recursion. "
            "When writing a recursive algorithm, your only task is to reduce the problem to "
            "one or more simpler instances of the same problem, or solve it directly. "
            "You then imagine that someone else (the Recursion Fairy) will correctly solve "
            "all the smaller instances — just as you would trust other modules in a reduction. "
            "This is equivalent to the induction hypothesis in a correctness proof."
        )
    },

    # ── LEVEL 7: Multi-hop ──────────────────────────────────────────────────
    {
        "level": 7,
        "question": "How does solving Fibonacci with DP relate to solving SubsetSum with DP, and why does one remain exponential?",
        "ground_truth": (
            "Both Fibonacci (Ch. 3) and SubsetSum (Ch. 2-3) start as backtracking algorithms. "
            "Fibonacci DP works because there are only O(n) distinct subproblems (F[0]..F[n]), "
            "so memoization reduces O(phi^n) to O(n). "
            "SubsetSum's subproblems are identified by (index i, remaining target T). "
            "With i in [0..n] and T up to the original target value, the number of distinct "
            "subproblems can be O(n * T), making the DP pseudo-polynomial (not truly polynomial). "
            "If T is exponentially large, SubsetSum DP does not help as much. "
            "The key difference is the number of distinct subproblems in each problem."
        )
    },
    {
        "level": 7,
        "question": "Compare the Tower of Hanoi and MergeSort recurrences — same structure, different outcomes. Why?",
        "ground_truth": (
            "Tower of Hanoi: T(n) = 2T(n-1) + 1 — reduces n to n-1, doing O(1) extra work. "
            "This gives T(n) = 2^n - 1, which is exponential. "
            "MergeSort: T(n) = 2T(n/2) + O(n) — splits n in half, doing O(n) extra work. "
            "This gives T(n) = O(n log n), which is much better. "
            "The difference is in how the problem size shrinks: "
            "subtracting 1 leads to exponential depth, while dividing by 2 leads to logarithmic depth. "
            "The O(n) merge work at each of O(log n) levels gives n log n total work."
        )
    },
    {
        "level": 7,
        "question": "How does the edit distance problem combine the recursive structure from Chapter 1 with the DP technique introduced via Fibonacci in Chapter 3?",
        "ground_truth": (
            "Chapter 1 introduces the 'Simplify and Delegate' recursion pattern: "
            "reduce the problem to smaller instances. "
            "Edit distance follows this: Edit(i,j) — the distance between the first i characters "
            "of one string and first j of another — reduces to three subproblems: "
            "Edit(i-1,j)+1 (deletion), Edit(i,j-1)+1 (insertion), Edit(i-1,j-1)+[0 or 1] (substitution). "
            "Like naive Fibonacci, the naive recursion recomputes overlapping subproblems. "
            "Applying the Chapter 3 DP technique — memoize in a 2D table filled in row-by-row order "
            "— converts the exponential recursion into an O(mn) algorithm "
            "where m and n are the lengths of the two strings."
        )
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT: Backend Development Lecture
# ─────────────────────────────────────────────────────────────────────────────
Backend_TEST_CASES = [
    # ── LEVEL 1 ─────────────────────────────────────────────────────────────
    {
        "level": 1,
        "question": "What are the three major parts of a backend?",
        "ground_truth": "The three major parts are the server (computer that receives requests), the app (application running on the server), and the database (used to organize and persist data)."
    },
    {
        "level": 1,
        "question": "What does CRUD stand for?",
        "ground_truth": "CRUD stands for Create, Read, Update, Delete — the four basic operations for data handling."
    },
    {
        "level": 1,
        "question": "What is Docker?",
        "ground_truth": "Docker is an open-source containerization platform that enables developers to package applications into containers. It is similar to a virtual machine but much more efficient."
    },
    {
        "level": 1,
        "question": "What is the difference between TCP and UDP?",
        "ground_truth": "TCP is stream-based and connection-oriented, providing reliable delivery at the cost of connection setup. UDP is message-based and connectionless, starts faster but does not guarantee delivery."
    },
    # ── LEVEL 2 ─────────────────────────────────────────────────────────────
    {
        "level": 2,
        "question": "What security risks should a backend developer protect against and how?",
        "ground_truth": "Backend developers should protect against man-in-the-middle attacks using TLS, DoS attacks using firewalls and DDoS protection, XSS attacks on the client side, and SQL injection on the server side."
    },
    {
        "level": 2,
        "question": "What is the difference between a forward proxy and a reverse proxy?",
        "ground_truth": "In a forward proxy the client explicitly asks for a particular backend server. In a reverse proxy the client does not know the final backend server — the proxy is the destination from the client's perspective."
    },
    {
        "level": 2,
        "question": "What are the steps to build a backend from scratch?",
        "ground_truth": "Define the project, choose a tech stack, set up the dev environment, design the database schema, implement API endpoints, add authentication and security, test, then deploy."
    },
    # ── LEVEL 3 ─────────────────────────────────────────────────────────────
    {
        "level": 3,
        "question": "Why would you choose PostgreSQL over MySQL?",
        "ground_truth": "PostgreSQL is better for complex applications requiring full SQL compliance, data integrity, and extensibility, especially for enterprise-level apps with frequent write operations. MySQL is better for simple read-heavy apps."
    },
    {
        "level": 3,
        "question": "When should you use NoSQL instead of SQL?",
        "ground_truth": "NoSQL is better for unstructured data, high-throughput workloads, real-time analytics, and horizontal scalability. SQL is better for structured data and read-heavy websites."
    },
    # ── LEVEL 4 ─────────────────────────────────────────────────────────────
    {
        "level": 4,
        "question": "What is the maximum number of users FastAPI can handle?",
        "ground_truth": "The document does not specify a maximum number of users for FastAPI. It only mentions high-performance design and asynchronous capabilities."
    },
    {
        "level": 4,
        "question": "What machine learning frameworks are discussed in the materials?",
        "ground_truth": "The document does not discuss any machine learning frameworks. It focuses on backend development concepts."
    },
    # ── LEVEL 5 ─────────────────────────────────────────────────────────────
    {
        "level": 5,
        "question": "What components make up a backend system?",
        "ground_truth": "The three major parts are the server, the app, and the database."
    },
    {
        "level": 5,
        "question": "How does TCP differ from UDP in terms of connection handling?",
        "ground_truth": "TCP is stream-based and connection-oriented (reliable, slower). UDP is message-based and connectionless (faster, no delivery guarantee)."
    },
    # ── LEVEL 6 ─────────────────────────────────────────────────────────────
    {
        "level": 6,
        "question": "What database should I use for my project?",
        "ground_truth": "It depends. SQL (PostgreSQL, MySQL) is better for structured data. NoSQL is better for unstructured data, high-throughput, and horizontal scalability."
    },
    # ── LEVEL 7 ─────────────────────────────────────────────────────────────
    {
        "level": 7,
        "question": "How do security, proxies, and deployment work together in a production backend?",
        "ground_truth": "Security (TLS, firewalls, DDoS) protects the backend. Reverse proxies handle load balancing, SSL termination, and caching. Cloud deployment (AWS, Azure) with CI/CD automates delivery. Together they form a production-ready architecture."
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# MULTIMODAL TEST CASES — Algorithms-JeffE.pdf (Chapters 1–3).
#
# Design philosophy:
#   - Questions ask to EXPLAIN or UNDERSTAND, not to compute.
#     "Explain", "what is", "describe", "what does this show" → rag_only intent.
#     The RAG should retrieve equation/image chunks AND the surrounding text,
#     display the image if one is attached, and give a natural explanation.
#   - Equation-solve questions test that the intent router correctly routes to
#     the equation module ONLY for explicit compute requests.
#   - expected_chunk_type: the chunk type we expect to appear in top-3 sources.
#   - expected_intent: the intent the router should classify the question as.
# ─────────────────────────────────────────────────────────────────────────────
Multimodal_TEST_CASES = [

    # ── Equation chunk: ask for explanation, NOT computation → rag_only ───
    # The RAG retrieves the equation chunk (with image) + surrounding text
    # and the LLM explains it. The image is shown in the UI automatically.
    {
        "level": "equation_explain",
        "question": "What is the matrix form of the Fibonacci recurrence and what does it mean?",
        "ground_truth": (
            "The Fibonacci recurrence can be written in matrix form as:\n"
            "$$\\begin{pmatrix} F(n+1) \\\\ F(n) \\end{pmatrix} = "
            "\\begin{pmatrix} 1 & 1 \\\\ 1 & 0 \\end{pmatrix}^n "
            "\\begin{pmatrix} F(1) \\\\ F(0) \\end{pmatrix}$$\n"
            "This means that applying the 2×2 matrix [[1,1],[1,0]] exactly n times "
            "to the initial vector [F(1), F(0)] = [1, 0] yields [F(n+1), F(n)]. "
            "The significance is that matrix exponentiation by repeated squaring runs "
            "in O(log n) matrix multiplications, giving an O(log n) Fibonacci algorithm "
            "— much faster than the O(n) iterative or O(2^n) naive recursive approaches."
        ),
        "expected_chunk_type": "equation",
        "expected_intent": "rag_only",
    },
    {
        "level": "equation_explain",
        "question": "What is the MergeSort recurrence T(n) = 2T(n/2) + O(n) and why does each term appear?",
        "ground_truth": (
            "The MergeSort recurrence T(n) = 2T(n/2) + O(n) captures the algorithm's cost:\n"
            "- **2T(n/2)**: MergeSort makes two recursive calls, each on a subarray of size n/2.\n"
            "- **O(n)**: The Merge step — merging two sorted halves — scans both halves once, "
            "costing O(n) time (a simple for-loop with constant work per iteration).\n"
            "The recurrence solves to T(n) = O(n log n) because there are O(log n) levels of "
            "recursion and each level does O(n) total merge work."
        ),
        "expected_chunk_type": "equation",
        "expected_intent": "rag_only",
    },
    {
        "level": "equation_explain",
        "question": "What does the Tower of Hanoi recurrence T(n) = 2T(n-1) + 1 tell us about the problem?",
        "ground_truth": (
            "The recurrence T(0) = 0, T(n) = 2T(n-1) + 1 captures the three-step solution:\n"
            "- Move n-1 disks from source to spare: T(n-1) moves.\n"
            "- Move the largest disk directly to destination: 1 move.\n"
            "- Move n-1 disks from spare to destination: T(n-1) moves.\n"
            "Total: T(n) = 2T(n-1) + 1. The recurrence shows the problem has exponential "
            "structure — unlike MergeSort (which halves the input), here the input only "
            "shrinks by 1 per level, giving T(n) = 2^n − 1 moves. "
            "This is unavoidable: it has been proven that 2^n − 1 is the minimum number of moves."
        ),
        "expected_chunk_type": "equation",
        "expected_intent": "rag_only",
    },

    # ── Image chunk: ask about a figure → RAG retrieves image chunk ────────
    # The image is shown in the source panel and the LLM explains what it depicts.
    {
        "level": "image_explain",
        "question": "Can you show me what the MergeSort algorithm looks like and explain it?",
        "ground_truth": (
            "MergeSort (figure/pseudocode in the book) works as follows:\n"
            "1. **MergeSort(A, 1, n)**: if n ≤ 1 return (base case — already sorted).\n"
            "2. **Divide**: split A into A[1..⌊n/2⌋] and A[⌊n/2⌋+1..n].\n"
            "3. **Conquer**: recursively call MergeSort on each half.\n"
            "4. **Combine**: call Merge to merge the two sorted halves back into A.\n"
            "The figure typically shows the recursive splitting tree and the merge step. "
            "The Merge subroutine uses two pointers scanning both sorted halves and "
            "picks the smaller element each time — O(n) per call, O(n log n) total."
        ),
        "expected_chunk_type": "image",
        "expected_intent": "rag_only",
    },
    {
        "level": "image_explain",
        "question": "What does the edit distance DP table for FOOD vs MONEY look like and how is it filled?",
        "ground_truth": (
            "The edit distance DP table is an (m+1)×(n+1) grid where m=len(FOOD)=4, n=len(MONEY)=5.\n"
            "- Row 0 is initialised 0,1,2,3,4,5 (cost of inserting each character of MONEY).\n"
            "- Column 0 is initialised 0,1,2,3,4 (cost of deleting each character of FOOD).\n"
            "- Each cell Edit[i][j] = min of three options:\n"
            "  - Edit[i-1][j] + 1 (delete from FOOD),\n"
            "  - Edit[i][j-1] + 1 (insert from MONEY),\n"
            "  - Edit[i-1][j-1] + (0 if equal else 1) (substitute or match).\n"
            "The bottom-right cell Edit[4][5] = 4, so the edit distance is 4."
        ),
        "expected_chunk_type": "image",
        "expected_intent": "rag_only",
    },

    # ── Correct equation_from_context: explicit compute requests ─────────
    # These should trigger the equation module. Questions explicitly ask to
    # SOLVE or DIFFERENTIATE a specific expression — not just explain it.
    {
        "level": "equation_solve",
        "question": "Solve the recurrence T(n) = 2T(n-1) + 1 with T(0) = 0.",
        "ground_truth": (
            "T(n) = 2^n − 1. "
            "Unrolling: T(n) = 2T(n-1)+1 = 2(2T(n-2)+1)+1 = 4T(n-2)+3 = ... = 2^n·T(0) + (2^n−1) = 2^n−1."
        ),
        "expected_intent": "equation_from_context",
    },
    {
        "level": "equation_solve",
        "question": "Differentiate f(x) = x^2 * sin(x).",
        "ground_truth": (
            "f'(x) = 2x·sin(x) + x²·cos(x) by the product rule: (uv)' = u'v + uv'."
        ),
        "expected_intent": "equation_from_context",
    },

    # ── Intent routing boundary: equation talk → rag_only ─────────────────
    # These questions mention equations but ask for explanation, not computation.
    # The router MUST classify them as rag_only.
    {
        "level": "intent_boundary",
        "question": "What are the capabilities of the equation module in BayLearn?",
        "ground_truth": (
            "The equation module in BayLearn is a symbolic solver. It can:\n"
            "- **Solve** equations (find roots, closed-form solutions of recurrences).\n"
            "- **Differentiate** expressions (symbolic derivatives).\n"
            "- **Integrate** expressions (definite and indefinite integrals).\n"
            "- **Plot/graph** functions.\n"
            "- **Simplify** algebraic expressions.\n"
            "It CANNOT explain what an equation means conceptually, give historical context, "
            "or answer RAG-style questions about lecture content."
        ),
        "expected_intent": "rag_only",
    },
    {
        "level": "intent_boundary",
        "question": "What recurrences appear in Chapter 1 of the Algorithms book?",
        "ground_truth": (
            "Chapter 1 (recursion chapter) introduces several recurrences:\n"
            "- **Tower of Hanoi**: T(n) = 2T(n-1) + 1, solution T(n) = 2^n − 1.\n"
            "- **MergeSort**: T(n) = 2T(n/2) + O(n), solution T(n) = O(n log n).\n"
            "These are used as running examples to illustrate the 'Simplify and Delegate' "
            "pattern: reduce the problem by one step (Hanoi) or split in half (MergeSort), "
            "then trust the Recursion Fairy to solve the smaller instance."
        ),
        "expected_intent": "rag_only",
    },

    # ── Equation rendered INSIDE a figure → ask RAG to EXPLAIN ─────────────
    # This is the case our caption-neighbor logic was built for. The image
    # chunk only describes the picture; the actual formula lives in adjacent
    # text chunks. The LLM needs both to give a real answer.
    {
        "level": "equation_in_image_explain",
        "question": (
            "On the page that shows the recursion tree figure (around page 50), "
            "what is the level-by-level summation equation for T(n), and how does "
            "the figure illustrate where each term in the sum comes from?"
        ),
        "ground_truth": (
            "The equation is T(n) = Σ_{i=0..L} r^i · f(n/c^i), where r is the "
            "branching factor (children per node), c is the size-shrink factor per "
            "level, and L = log_c n is the depth at which n/c^L = 1 hits the base "
            "case. The figure shows it directly: each level i of the tree has r^i "
            "nodes, and the work at each of those nodes is f(n/c^i), so the i-th "
            "term in the sum is exactly the total work at level i. Summing over "
            "levels gives the total cost of the recursion."
        ),
        "expected_chunk_type": "image",
        "expected_intent": "rag_only",
    },
    {
        "level": "equation_in_image_explain",
        "question": (
            "Show me the recursion-tree-style figure for MergeSort and explain "
            "what equation it represents."
        ),
        "ground_truth": (
            "The MergeSort recursion tree shows T(n) = 2T(n/2) + O(n). At the "
            "root, the cost is O(n) for the merge. The root has two children, "
            "each contributing T(n/2). At level i there are 2^i nodes, each "
            "doing O(n/2^i) merge work, so each level contributes O(n) total. "
            "Depth is log₂ n levels, giving total work O(n log n). The figure "
            "shows this as a balanced binary tree where every level sums to n."
        ),
        "expected_chunk_type": "image",
        "expected_intent": "rag_only",
    },

    # ── Equation in TEXT, ask to SOLVE → equation_from_context ────────────
    # Simple textual equations the equation module CAN handle (closed-form,
    # symbolic). These should route to the solver, not RAG.
    {
        "level": "equation_in_text_solve",
        "question": "Solve the MergeSort recurrence T(n) = 2T(n/2) + n with T(1) = 1.",
        "ground_truth": (
            "T(n) = n log₂ n + n  (i.e. Θ(n log n)). "
            "Master theorem case 2 (a=2, b=2, f(n)=n, n^log_b a = n) gives "
            "T(n) = Θ(n log n). Exact: unrolling gives n levels each costing n "
            "for log n levels, plus the n leaf costs."
        ),
        "expected_intent": "equation_from_context",
    },
    {
        "level": "equation_in_text_solve",
        "question": (
            "From the book, find the roots of the characteristic equation "
            "x^2 - x - 1 = 0 used in the closed-form Fibonacci derivation."
        ),
        "ground_truth": (
            "x = (1 ± √5) / 2. The positive root φ = (1+√5)/2 ≈ 1.618 is the "
            "golden ratio; the negative root ψ = (1−√5)/2 ≈ −0.618. These give "
            "Binet's formula: F(n) = (φ^n − ψ^n) / √5."
        ),
        "expected_intent": "equation_from_context",
    },

    # ── Equation in image, ask to SOLVE → equation_from_context ────────────
    # Tests both retrieval (RAG must surface the figure + caption with the
    # actual formula) AND extraction (equation module must parse it from
    # the recovered text). Hardest case.
    {
        "level": "equation_in_image_solve",
        "question": (
            "Find the closed-form solution of the recurrence shown in the "
            "Tower of Hanoi figure: T(n) = 2T(n-1) + 1 with T(0) = 0."
        ),
        "ground_truth": (
            "T(n) = 2^n − 1. Unroll: T(n) = 2T(n-1)+1 = 2(2T(n-2)+1)+1 "
            "= 4T(n-2)+3 = ... = 2^n·T(0) + (1+2+4+...+2^(n-1)) = 2^n − 1."
        ),
        "expected_intent": "equation_from_context",
    },
]


def get_test_cases(dataset="scientific", levels=None):
    """
    Args:
        dataset: "scientific" | "backend" | "multimodal"
        levels: list of level values to filter on, or None for all.
                For multimodal use e.g. levels=["image"] or ["equation"].
    """
    mapping = {
        "scientific":  Scientific_TEST_CASES,
        "backend":     Backend_TEST_CASES,
        "multimodal":  Multimodal_TEST_CASES,
    }
    cases = mapping.get(dataset, Scientific_TEST_CASES)
    if levels:
        return [c for c in cases if c.get("level") in levels]
    return cases


TEST_CASES = Scientific_TEST_CASES
