# Your test set — questions you write manually based on your PDF
# ground_truth = the correct answer YOU write, not the RAG's answer
# This is your evaluation "answer key"

CV_TEST_CASES = [
    # ── LEVEL 1: Direct Lookup ──────────────────────────────
    {
        "question": "What programming languages does Manar know?",
        "ground_truth": "Manar knows C++, C, HTML5, CSS, Node.js, MSSQL, Python, MATLAB, C#, x86 assembly, and ARM Cortex-M3 assembly."
    },
    {
        "question": "What is Manar's GPA?",
        "ground_truth": "Manar's GPA is 3.3 out of 4.00."
    },
    {
        "question": "Where does Manar study?",
        "ground_truth": "Manar studies at Cairo University, Faculty of Engineering, Department of Computer Engineering."
    },

    # ── LEVEL 2: Synthesis ──────────────────────────────────
    {
        "question": "What microcontroller and display did Manar use in her game project?",
        "ground_truth": "Manar used an STM32 Bluebill microcontroller and a 2.8-inch ILI9341 TFT screen in the Pacman Atari-Game project."
    },
    {
        "question": "Which of Manar's projects involved helping vulnerable populations?",
        "ground_truth": "The Family Forever project was a desktop application to help orphanages, and Manar also volunteered at Resala Charity."
    },
    {
        "question": "What signal processing techniques did Manar use in her speaker recognition project?",
        "ground_truth": "Manar used Mel-frequency cepstral coefficients (MFCCs) extracted from recorded audio signals using Python."
    },

    # ── LEVEL 3: Reasoning ──────────────────────────────────
    {
        "question": "Based on her projects, does Manar have experience with both hardware and software development?",
        "ground_truth": "Yes. Manar has software experience from projects like Family Forever (.NET, C#) and CPU Scheduler (C++), and hardware experience from the Pacman game (ARM Cortex-M3 assembly, STM32 microcontroller, TFT screen)."
    },
    {
        "question": "What programming paradigms has Manar studied?",
        "ground_truth": "Manar has studied Object Oriented Programming (OOP), Data Structures and Algorithms, and Database Design."
    },

    # ── LEVEL 4: Negative — hallucination resistance ────────
    {
        "question": "What is Manar's CGPA on a 5.0 scale?",
        "ground_truth": "The document does not provide a GPA on a 5.0 scale. Only a 4.0 scale GPA of 3.3 is mentioned."
    },
    {
        "question": "What internships has Manar completed?",
        "ground_truth": "The document does not mention any internships. It only mentions volunteer work at Resala Charity."
    },
]
Backend_TEST_CASES = [
    {
        "question": "What are the three major parts of a backend?",
        "ground_truth": "The three major parts are the server (computer that receives requests), the app (application running on the server that listens for requests), and the database (used to organize and persist data)."
    },
    {
        "question": "What does CRUD stand for?",
        "ground_truth": "CRUD stands for Create, Read, Update, Delete — the four basic operations for data handling."
    },
    {
        "question": "What is the difference between TCP and UDP?",
        "ground_truth": "TCP is stream-based and connection-oriented, providing reliable delivery at the cost of connection setup. UDP is message-based and connectionless, starts faster but does not guarantee delivery."
    },

    # Level 2 — Synthesis
    {
        "question": "What security risks should a backend developer protect against and how?",
        "ground_truth": "Backend developers should protect against man-in-the-middle attacks using TLS encryption, denial of service attacks using firewalls and DDoS protection, XSS attacks on the client side, and SQL injection on the server side."
    },
    {
        "question": "What is the difference between a forward proxy and a reverse proxy?",
        "ground_truth": "In a forward proxy, the client explicitly asks for a particular backend server and the proxy fulfills it. In a reverse proxy, the client does not know the final backend server — the proxy is the destination from the client's perspective."
    },
    {
        "question": "What cloud platforms are commonly used for deployment?",
        "ground_truth": "Common cloud platforms include AWS, Google Cloud, Microsoft Azure, Alibaba Cloud, IBM Cloud, Firebase, DigitalOcean, and Heroku."
    },

    # Level 3 — Reasoning
    {
        "question": "Why would you choose PostgreSQL over MySQL?",
        "ground_truth": "PostgreSQL is better for complex applications requiring full SQL compliance, data integrity, and extensibility, especially for enterprise-level apps with frequent write operations. MySQL is better for simple read-heavy applications."
    },
    {
        "question": "When should you use NoSQL instead of SQL?",
        "ground_truth": "NoSQL is better for unstructured data, high-throughput workloads, real-time analytics, and scenarios requiring horizontal scalability. SQL is better for structured data and read-heavy websites."
    },

    # Level 4 — Negative (hallucination resistance)
    {
        "question": "What is the maximum number of users FastAPI can handle?",
        "ground_truth": "The document does not specify a maximum number of users for FastAPI. It only mentions that FastAPI has high-performance design and asynchronous capabilities."
    },
    {
        "question": "What is the salary of a backend developer?",
        "ground_truth": "The document does not contain any information about backend developer salaries."
    },
]

TEST_CASES = CV_TEST_CASES[:5]
# TEST_CASES = CV_TEST_CASES[5:]
# TEST_CASES = Backend_TEST_CASES[:5]
# TEST_CASES = Backend_TEST_CASES[5:]