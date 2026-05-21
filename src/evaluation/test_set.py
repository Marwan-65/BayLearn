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

CV_TEST_CASES = [
    # ── LEVEL 1: Direct Lookup ──────────────────────────────
    {
        "level": 1,
        "question": "What programming languages does Manar know?",
        "ground_truth": "Manar knows C++, C, HTML5, CSS, Node.js, MSSQL, Python, MATLAB, C#, x86 assembly, and ARM Cortex-M3 assembly."
    },
    {
        "level": 1,
        "question": "What is Manar's GPA?",
        "ground_truth": "Manar's GPA is 3.3 out of 4.00."
    },
    {
        "level": 1,
        "question": "Where does Manar study?",
        "ground_truth": "Manar studies at Cairo University, Faculty of Engineering, Department of Computer Engineering."
    },
    {
        "level": 1,
        "question": "What is Manar's email address?",
        "ground_truth": "Manar's email address is m.f.abdelshay@gmail.com."
    },
    {
        "level": 1,
        "question": "When is Manar expected to graduate?",
        "ground_truth": "Manar is expected to graduate in 2026."
    },

    # ── LEVEL 2: Synthesis ──────────────────────────────────
    {
        "level": 2,
        "question": "What microcontroller and display did Manar use in her game project?",
        "ground_truth": "Manar used an STM32 Bluebill microcontroller and a 2.8-inch ILI9341 TFT screen in the Pacman Atari-Game project."
    },
    {
        "level": 2,
        "question": "Which of Manar's projects involved helping vulnerable populations?",
        "ground_truth": "The Family Forever project was a desktop application to help orphanages, and Manar also volunteered at Resala Charity."
    },
    {
        "level": 2,
        "question": "What signal processing techniques did Manar use in her speaker recognition project?",
        "ground_truth": "Manar used Mel-frequency cepstral coefficients (MFCCs) extracted from recorded audio signals using Python."
    },
    {
        "level": 2,
        "question": "What frameworks and tools has Manar used across all her projects?",
        "ground_truth": "Manar has used .NET framework with C# (Family Forever), ARM Cortex-M3 assembly with STM32 (Pacman), C++ with OOP and data structures (CPU Scheduler), Logisim (Calculator), and Python (Speaker Recognition)."
    },

    # ── LEVEL 3: Reasoning ──────────────────────────────────
    {
        "level": 3,
        "question": "Based on her projects, does Manar have experience with both hardware and software development?",
        "ground_truth": "Yes. Manar has software experience from projects like Family Forever (.NET, C#) and CPU Scheduler (C++), and hardware experience from the Pacman game (ARM Cortex-M3 assembly, STM32 microcontroller, TFT screen)."
    },
    {
        "level": 3,
        "question": "What programming paradigms has Manar studied?",
        "ground_truth": "Manar has studied Object Oriented Programming (OOP), Data Structures and Algorithms, and Database Design."
    },
    {
        "level": 3,
        "question": "Based on her skills and projects, what type of engineering roles would Manar be qualified for?",
        "ground_truth": "Based on her skills in C++, Python, embedded systems (STM32, ARM assembly), signal processing, and .NET development, Manar would be qualified for embedded systems engineering, software development, and signal processing roles."
    },

    # ── LEVEL 4: Negative — hallucination resistance ────────
    {
        "level": 4,
        "question": "What is Manar's CGPA on a 5.0 scale?",
        "ground_truth": "The document does not provide a GPA on a 5.0 scale. Only a 4.0 scale GPA of 3.3 is mentioned."
    },
    {
        "level": 4,
        "question": "What internships has Manar completed?",
        "ground_truth": "The document does not mention any internships. It only mentions volunteer work at Resala Charity."
    },
    {
        "level": 4,
        "question": "Does Manar have a master's degree?",
        "ground_truth": "The document does not mention a master's degree. Manar is pursuing a B.S. in Computer Engineering expected 2026."
    },

    # ── LEVEL 5: Paraphrase ─────────────────────────────────
    {
        "level": 5,
        "question": "What grade point average did Manar achieve?",
        "ground_truth": "Manar's GPA is 3.3 out of 4.00."
    },
    {
        "level": 5,
        "question": "Which coding languages is Manar proficient in?",
        "ground_truth": "Manar knows C++, C, HTML5, CSS, Node.js, MSSQL, Python, MATLAB, C#, x86 assembly, and ARM Cortex-M3 assembly."
    },
    {
        "level": 5,
        "question": "What institution does Manar attend?",
        "ground_truth": "Manar studies at Cairo University, Faculty of Engineering, Department of Computer Engineering."
    },
    {
        "level": 5,
        "question": "What hardware components were used in the Pacman project?",
        "ground_truth": "The Pacman project used an STM32 Bluebill microcontroller, a 2.8-inch ILI9341 TFT screen, and input/output buttons, programmed in ARM Cortex-M3 assembly."
    },
    {
        "level": 5,
        "question": "How can I reach Manar?",
        "ground_truth": "Manar can be reached via email at m.f.abdelshay@gmail.com or by phone at +201205819054. She also has a LinkedIn profile."
    },

    # ── LEVEL 6: Ambiguous ──────────────────────────────────
    {
        "level": 6,
        "question": "What are all languages Manar knows?",
        "ground_truth": "Manar knows programming languages: C++, C, HTML5, CSS, Node.js, MSSQL, Python, MATLAB, C#, x86 assembly, ARM Cortex-M3 assembly. She also speaks English and Arabic (mother tongue)."
    },
    {
        "level": 6,
        "question": "What are Manar's achievements?",
        "ground_truth": "Manar won a Golden Prize in the Kangaroo Math Competition. She also completed multiple academic projects and volunteered at Resala Charity."
    },
    {
        "level": 6,
        "question": "What work experience does Manar have?",
        "ground_truth": "The document does not mention formal work experience or internships. Manar has volunteer experience at Resala Charity (July-September 2021) and was a Public Relations member in TCCD student activity."
    },

    # ── LEVEL 7: Multi-hop ──────────────────────────────────
    {
        "level": 7,
        "question": "Did Manar use Python in multiple projects?",
        "ground_truth": "Yes, Python is listed in Manar's skills section, and she specifically used Python in the Speaker Recognition project for extracting MFCCs from audio signals."
    },
    {
        "level": 7,
        "question": "What skills from Manar's coursework were applied in her projects?",
        "ground_truth": "OOP and Data Structures (from her courses) were applied in the CPU Scheduler project using C++. Database Design knowledge may have been applied in the Family Forever project which managed children's data."
    },
]

Backend_TEST_CASES = [
    # ── LEVEL 1: Direct Lookup ──────────────────────────────
    {
        "level": 1,
        "question": "What are the three major parts of a backend?",
        "ground_truth": "The three major parts are the server (computer that receives requests), the app (application running on the server that listens for requests), and the database (used to organize and persist data)."
    },
    {
        "level": 1,
        "question": "What does CRUD stand for?",
        "ground_truth": "CRUD stands for Create, Read, Update, Delete — the four basic operations for data handling."
    },
    {
        "level": 1,
        "question": "What is the difference between TCP and UDP?",
        "ground_truth": "TCP is stream-based and connection-oriented, providing reliable delivery at the cost of connection setup. UDP is message-based and connectionless, starts faster but does not guarantee delivery."
    },
    {
        "level": 1,
        "question": "What is Docker?",
        "ground_truth": "Docker is an open-source containerization platform that enables developers to package applications into containers. It is similar to a virtual machine but much more efficient."
    },
    {
        "level": 1,
        "question": "What is middleware in backend development?",
        "ground_truth": "Middleware functions have access to the request and response objects and the next middleware function. They can execute code, modify request/response objects, end the request-response cycle, or call the next middleware."
    },

    # ── LEVEL 2: Synthesis ──────────────────────────────────
    {
        "level": 2,
        "question": "What security risks should a backend developer protect against and how?",
        "ground_truth": "Backend developers should protect against man-in-the-middle attacks using TLS encryption, denial of service attacks using firewalls and DDoS protection, XSS attacks on the client side, and SQL injection on the server side."
    },
    {
        "level": 2,
        "question": "What is the difference between a forward proxy and a reverse proxy?",
        "ground_truth": "In a forward proxy, the client explicitly asks for a particular backend server and the proxy fulfills it. In a reverse proxy, the client does not know the final backend server — the proxy is the destination from the client's perspective."
    },
    {
        "level": 2,
        "question": "What cloud platforms are commonly used for deployment?",
        "ground_truth": "Common cloud platforms include AWS, Google Cloud, Microsoft Azure, Alibaba Cloud, IBM Cloud, Firebase, DigitalOcean, and Heroku."
    },
    {
        "level": 2,
        "question": "What are the steps to build a backend from scratch?",
        "ground_truth": "The steps include: 1) Define your project (purpose, audience, functionalities), 2) Choose tech stack, 3) Set up development environment, 4) Design database schema, 5) Implement API endpoints, 6) Add authentication and security, 7) Test, 8) Deploy."
    },

    # ── LEVEL 3: Reasoning ──────────────────────────────────
    {
        "level": 3,
        "question": "Why would you choose PostgreSQL over MySQL?",
        "ground_truth": "PostgreSQL is better for complex applications requiring full SQL compliance, data integrity, and extensibility, especially for enterprise-level apps with frequent write operations. MySQL is better for simple read-heavy applications."
    },
    {
        "level": 3,
        "question": "When should you use NoSQL instead of SQL?",
        "ground_truth": "NoSQL is better for unstructured data, high-throughput workloads, real-time analytics, and scenarios requiring horizontal scalability. SQL is better for structured data and read-heavy websites."
    },
    {
        "level": 3,
        "question": "When would you use a reverse proxy instead of connecting directly to the server?",
        "ground_truth": "A reverse proxy is used for load balancing across multiple servers, SSL termination, caching, security (hiding backend server details), and compression. It is essential when scaling beyond a single server."
    },

    # ── LEVEL 4: Negative — hallucination resistance ────────
    {
        "level": 4,
        "question": "What is the maximum number of users FastAPI can handle?",
        "ground_truth": "The document does not specify a maximum number of users for FastAPI. It only mentions that FastAPI has high-performance design and asynchronous capabilities."
    },
    {
        "level": 4,
        "question": "What is the salary of a backend developer?",
        "ground_truth": "The document does not contain any information about backend developer salaries."
    },
    {
        "level": 4,
        "question": "What machine learning frameworks are discussed in the materials?",
        "ground_truth": "The document does not discuss any machine learning frameworks. It focuses on backend development concepts like servers, databases, APIs, and deployment."
    },

    # ── LEVEL 5: Paraphrase ─────────────────────────────────
    {
        "level": 5,
        "question": "What components make up a backend system?",
        "ground_truth": "The three major parts are the server (computer that receives requests), the app (application running on the server that listens for requests), and the database (used to organize and persist data)."
    },
    {
        "level": 5,
        "question": "Explain the Create Read Update Delete operations.",
        "ground_truth": "CRUD stands for Create, Read, Update, Delete — the four basic operations for data handling in backend systems."
    },
    {
        "level": 5,
        "question": "How does TCP differ from UDP in terms of connection handling?",
        "ground_truth": "TCP is stream-based and connection-oriented, providing reliable delivery at the cost of connection setup. UDP is message-based and connectionless, starts faster but does not guarantee delivery."
    },
    {
        "level": 5,
        "question": "What containerization tool packages apps into portable units?",
        "ground_truth": "Docker is an open-source containerization platform that enables developers to package applications into containers. It is similar to a virtual machine but much more efficient."
    },
    {
        "level": 5,
        "question": "What are the deployment platforms available for hosting backend applications?",
        "ground_truth": "Common cloud platforms include AWS, Google Cloud, Microsoft Azure, Alibaba Cloud, IBM Cloud, Firebase, DigitalOcean, and Heroku."
    },

    # ── LEVEL 6: Ambiguous ──────────────────────────────────
    {
        "level": 6,
        "question": "How do you handle errors in a backend?",
        "ground_truth": "The document mentions implementing proper error handling and logging as an additional consideration for backend development. It also mentions testing as a crucial step to ensure there are no bugs before production."
    },
    {
        "level": 6,
        "question": "What database should I use for my project?",
        "ground_truth": "It depends on the use case. SQL databases (PostgreSQL, MySQL) are better for structured data and read-heavy websites. NoSQL databases are better for unstructured data, high-throughput workloads, and horizontal scalability."
    },
    {
        "level": 6,
        "question": "Is Node.js good for backend development?",
        "ground_truth": "Node.js has pros: scalability, good for real-time apps, popular for web applications. Cons: unstable API, not suited for CPU-intensive tasks, lacks strong library support, and dealing with relational databases can be difficult."
    },

    # ── LEVEL 7: Multi-hop ──────────────────────────────────
    {
        "level": 7,
        "question": "How do security, proxies, and deployment work together in a production backend?",
        "ground_truth": "Security measures (TLS, firewalls, DDoS protection) protect the backend. Reverse proxies handle load balancing, SSL termination, and caching. Deployment to cloud platforms (AWS, Azure, etc.) with CI/CD pipelines automates the process. Together they form a production-ready architecture."
    },
    {
        "level": 7,
        "question": "Compare the testing and deployment stages of backend development.",
        "ground_truth": "Testing ensures there are no bugs before production by deploying to various environments. Deployment involves using CI/CD pipelines for continuous integration and delivery, containerization with Docker, and hosting on cloud platforms. Testing must happen before deployment to production."
    },
]


def get_test_cases(dataset="cv", levels=None):
    """
    Get test cases filtered by dataset and optional level filter.

    Args:
        dataset: "cv" or "backend"
        levels: list of ints e.g. [1, 2, 5] or None for all

    Returns:
        list of test case dicts
    """
    cases = CV_TEST_CASES if dataset == "cv" else Backend_TEST_CASES
    if levels:
        return [c for c in cases if c.get("level") in levels]
    return cases


# Default: all CV cases (for backward compatibility)
TEST_CASES = CV_TEST_CASES
