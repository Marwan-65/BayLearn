import json
import os
import sympy as sp
from sympy.parsing.sympy_parser import parse_expr
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

# Initialize the Groq client (make sure your API key is in your environment variables)
client = Groq(api_key=api_key)

system_prompt = """
You are a mathematical translation API. 
Read the user's messy mathematical input and translate it into strict, unambiguous SymPy-compatible syntax.
1. Fix human typos and ambiguities (e.g., if 'x' is used as a multiplication sign, replace it with '*').
2. Identify the core mathematical operation ('solve', 'solve_system', 'derive', or 'integrate').
3. Format the equations as a list of objects. Each object must have a "lhs" and "rhs".
  -ALL values for "lhs" and "rhs" MUST be formatted as strings, even if they are plain numbers. 
4. Identify the target variables and return them as a list of strings.
5. Output ONLY a valid JSON object with these exact keys: "operation", "equations", "target_variables". Do not include markdown.
"""

def level_2_solver(user_input):
    try:
        # Phase 1: The AI Translator
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input}
            ],
            response_format={"type": "json_object"}, # Forces pure JSON output
            temperature=0.1
        )
        
        # Parse the AI's JSON string into a Python dictionary
        ai_data = json.loads(response.choices[0].message.content)
        
        print(f"--- AI Translation --- \n{json.dumps(ai_data, indent=2)}\n")
        
        # ... inside your try block after json.loads ...
        
        # 1. Dynamically build a list of all equations
        sympy_equations = []
        for eq_data in ai_data["equations"]:
            # Wrap the JSON values in str() to guarantee they are strings
            lhs_expr = parse_expr(str(eq_data["lhs"]))
            rhs_expr = parse_expr(str(eq_data["rhs"]))
            sympy_equations.append(sp.Eq(lhs_expr, rhs_expr))
            
        # 2. Dynamically build a list of all target variables
        target_vars = [sp.Symbol(var) for var in ai_data["target_variables"]]
        
        # 3. Route the logic
        if ai_data["operation"] in ["solve", "solve_system"]:
            # sp.solve() natively handles both single equations and lists of equations!
            solutions = sp.solve(sympy_equations, target_vars)
            return f"Solutions: {solutions}"
            
        elif ai_data["operation"] == "derive":
            # Assuming standard single derivation for now
            derivative = sp.diff(sympy_equations[0].lhs, target_vars[0])
            return f"Derivative: {derivative}"
            
        else:
            return "Operation not fully implemented in backend yet."

    except Exception as e:
        return f"System Error: {e}"

# Test it with your exact trap equation!
print(level_2_solver("Solve 2x + y = 10 and x - y = 2"))