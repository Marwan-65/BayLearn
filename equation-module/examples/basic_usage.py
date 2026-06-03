from baylearn import level_2_solver, solve_math_string

def example_basic_equation():
    """Example 1: Solve a basic equation."""
    print("=" * 60)
    print("Example 1: Solve 2x + 5 = 15")
    print("=" * 60)
    
    result1 = solve_math_string("2x + 5 = 15")
    print(f"Result: {result1}\n")

    # More advanced solver with steps
    result2 = level_2_solver("Solve 2x + 5 = 15")
    print(f"Detailed Solution:\n{result2}\n")


def example_system_of_equations():
    """Example 2: Solve system of equations."""
    print("=" * 60)
    print("Example 2: Solve system of equations")
    print("=" * 60)
    
    query = "Solve 2x + y = 10 and x - y = 2"
    result = level_2_solver(query)
    print(f"Query: {query}")
    print(f"Result:\n{result}\n")


def example_derivative():
    """Example 3: Compute derivative."""
    print("=" * 60)
    print("Example 3: Find derivative")
    print("=" * 60)
    
    query = "Find the derivative of x^3 + 2*x^2 - 5 with respect to x"
    result = level_2_solver(query)
    print(f"Query: {query}")
    print(f"Result:\n{result}\n")

def example_integral():
    """Example 4: Compute integral."""
    print("=" * 60)
    print("Example 4: Find integral")
    print("=" * 60)
    
    query = "Find the integral of 3*x^2 + 2*x with respect to x"
    result = level_2_solver(query)
    print(f"Query: {query}")
    print(f"Result:\n{result}\n")


def example_matrix_operation():
    """Example 5: Matrix operations."""
    print("=" * 60)
    print("Example 5: Matrix operations")
    print("=" * 60)
    
    query = "Find the determinant of [[1, 2], [3, 4]]"
    result = level_2_solver(query)
    print(f"Query: {query}")
    print(f"Result:\n{result}\n")


def example_with_translation():
    """Example 6: Getting AI translation along with solution."""
    print("=" * 60)
    print("Example 6: Solution with AI translation")
    print("=" * 60)
    
    query = "Solve y^2 - 9 = 0"
    solution, translation = level_2_solver(query, return_translation=True)
    
    print(f"Query: {query}")
    print(f"\nAI Translation:")
    print(f"  Operation: {translation.get('operation')}")
    print(f"  Target Variables: {translation.get('target_variables')}")
    print(f"\nSolution:\n{solution}\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("BayLearn Module - Basic Usage Examples")
    print("=" * 60 + "\n")
    
    try:
        example_basic_equation()
        example_system_of_equations()
        example_derivative()
        example_integral()
        example_matrix_operation()
        example_with_translation()
        
        print("=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        print("Make sure GROQ_API_KEY is set in your .env file")
