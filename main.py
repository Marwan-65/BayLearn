import os
from dotenv import load_dotenv
from groq import Groq
import re
import subprocess

# Load environment variables from .env file
load_dotenv()

# Get the API key from environment variables
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in environment variables. Please check your .env file.")

client = Groq(api_key=api_key)

# system_instruction = """
# You are a code-generating math assistant. 
# Analyze the user's math equation and write a Python script using the `sympy` library to solve it.
# The script must print the step-by-step logical breakdown.
# Output ONLY valid Python code wrapped in ```python and ``` markers.
# """
system_instruction = """You are a code-generating math assistant for a neuro-symbolic solver. 
Analyze the user's math equation and write a Python script using the `sympy` library to solve it.

Strict Rules for the Python script:
1. Print the step-by-step logical breakdown of how you are setting up the problem.
2. Solve the equation using `sympy` to find the exact mathematical roots. Print these exact roots clearly.
3. At the very end of the script, iterate through the final solutions and use `.evalf(4)` to print a clean, user-friendly decimal approximation. 
4. If the exact roots contain complex fractions that evaluate to real numbers (Casus Irreducibilis), ensure the final decimal output filters out any negligible imaginary artifacts (e.g., drop `+ 0.e-20*I`) so the user only sees clean real numbers.
5. Output ONLY valid, executable Python code wrapped in ```python and ``` markers. Do not include any conversational text, explanations, or markdown outside of the code block.
6. Use ONLY standard ASCII characters in your print statements. Do not use special unicode math symbols like ≈, π, or ∞. Spell them out or use standard keyboard equivalents (e.g., use '=' instead of '≈').
7. If the user provides a differential equation, strictly use SymPy's `Function` class to define the dependent variable, `Derivative` to set up the equation, and `dsolve()` to solve it. If the user provides initial conditions (an Initial Value Problem), pass them into `dsolve()` using the `ics` parameter."""


user_equation = "Solve this differential equation: $y''(t) + 4y'(t) + 13y(t) = 0$ with the initial conditions $y(0) = 1$ and $y'(0) = -2$."

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_equation}
    ],
    temperature=0.1
)
raw_ai_output = response.choices[0].message.content
print(raw_ai_output)


def extract_code(ai_text):
    # Regex pattern to find everything between ```python and ```
    pattern = r"```python\n(.*?)\n```"
    
    # re.DOTALL allows the regex to match across multiple lines
    match = re.search(pattern, ai_text, re.DOTALL)
    
    if match:
        return match.group(1) # Returns just the code inside the block
    else:
        return None # In case the AI failed to format properly

clean_python_code = extract_code(raw_ai_output)


def run_generated_code(python_code):
  
  with open("tmp_code.py","w") as f:
    f.write(python_code)
  
  try:
    result = subprocess.run(
        ["python", "tmp_code.py"],
        capture_output=True,
        text=True,
        check=True,
        timeout=5
    )
    return result.stdout
  except subprocess.TimeoutExpired:
    return "the code took too long to execute."
  except subprocess.CalledProcessError as e:
    return f"An error occurred: {e}\nError output: {e.stderr}"
  
  finally:
    os.remove("tmp_code.py")

if clean_python_code:
  execution_result = run_generated_code(clean_python_code)
  print("Execution Result:")
  print(execution_result)
    
