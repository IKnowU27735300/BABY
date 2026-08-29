"""
tools/math_tools.py — Mathematical Computation Tools for Baby.

Provides precise mathematical computation using SymPy and NumPy:
- evaluate_expression: Evaluate mathematical expressions with exact results
- solve_equation: Solve equations for unknown variables
- simplify_expression: Simplify mathematical expressions
- differentiate: Compute derivatives
- integrate: Compute integrals
- factorize: Factor expressions
- expand_expression: Expand expressions
- calculate_statistics: Compute mean, median, std dev, etc.
- convert_units: Convert between different units
- memory_recall: Search stored memory for user information

All tools return structured results with LaTeX formatting for the LLM to use.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from loguru import logger


# ─── Tool Schema ──────────────────────────────────────────────────────────────

MATH_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "matrix_operations",
            "description": "Perform matrix operations: multiply, add, subtract, determinant, inverse, transpose, eigenvalues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "Operation to perform: 'multiply', 'add', 'subtract', 'determinant', 'inverse', 'transpose', 'trace', 'rank'.",
                    },
                    "matrix_a": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "First matrix (2D array). Example: [[1,2],[3,4]]",
                    },
                    "matrix_b": {
                        "type": "array",
                        "items": {"type": "array", "items": {"type": "number"}},
                        "description": "Second matrix (for binary operations). Example: [[5,6],[7,8]]",
                    },
                },
                "required": ["operation", "matrix_a"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "base_conversion",
            "description": "Convert a number between different bases (binary, octal, decimal, hexadecimal, or any base 2-36).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "string",
                        "description": "The number to convert. Example: '255', 'FF', '11111111'",
                    },
                    "from_base": {
                        "type": "integer",
                        "description": "The base of the input number (2-36). Example: 10 for decimal, 16 for hex, 2 for binary",
                    },
                    "to_base": {
                        "type": "integer",
                        "description": "The target base (2-36). Example: 2 for binary, 16 for hex, 10 for decimal",
                    },
                },
                "required": ["value", "from_base", "to_base"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_primes",
            "description": "List prime numbers up to a given limit, or find the Nth prime number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Find all primes up to this number. Example: 100",
                    },
                    "nth": {
                        "type": "integer",
                        "description": "Find the Nth prime number. Example: 10 for the 10th prime",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scientific_constants",
            "description": "Get the value of common mathematical and physical constants (pi, e, c, g, h, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "constant": {
                        "type": "string",
                        "description": "Constant name: 'pi', 'e', 'phi' (golden ratio), 'c' (speed of light), 'g' (gravity), 'h' (Planck), 'k' (Boltzmann), 'NA' (Avogadro)",
                    },
                },
                "required": ["constant"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_expression",
            "description": "Evaluate a mathematical expression and return the exact result. Supports arithmetic, algebra, trigonometry, logarithms, exponents, and more. Use this for ANY calculation the user asks for — do NOT rely on the LLM's arithmetic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate. Examples: '2+2', 'sqrt(144)', 'sin(pi/4)', 'log(100)', '2^10', 'factorial(5)'",
                    },
                    "variables": {
                        "type": "object",
                        "description": "Optional variable values for substitution. Example: {'x': 2, 'y': 3}",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "solve_equation",
            "description": "Solve one or more equations for the specified unknown variables. Returns exact symbolic solutions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "equations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of equations to solve. Use '==' for equality. Examples: ['x**2 - 4 == 0', '2*x + 3 == 7']",
                    },
                    "variables": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The unknown variables to solve for. Example: ['x'] or ['x', 'y']",
                    },
                },
                "required": ["equations", "variables"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simplify_expression",
            "description": "Simplify a mathematical expression to its most compact form.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The expression to simplify. Example: 'x**2 + 2*x + 1' or 'sin(x)**2 + cos(x)**2'",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "differentiate",
            "description": "Compute the derivative of an expression with respect to a variable.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The expression to differentiate. Example: 'x**3 + 2*x**2 + x'",
                    },
                    "variable": {
                        "type": "string",
                        "description": "The variable to differentiate with respect to. Default: 'x'",
                    },
                    "order": {
                        "type": "integer",
                        "description": "Order of derivative (1 for first derivative, 2 for second, etc.). Default: 1",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "integrate",
            "description": "Compute the integral of an expression. Can do indefinite or definite integrals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The expression to integrate. Example: 'x**2 + 2*x'",
                    },
                    "variable": {
                        "type": "string",
                        "description": "The variable to integrate with respect to. Default: 'x'",
                    },
                    "lower_limit": {
                        "type": "string",
                        "description": "Lower limit for definite integral. Leave empty for indefinite integral.",
                    },
                    "upper_limit": {
                        "type": "string",
                        "description": "Upper limit for definite integral. Leave empty for indefinite integral.",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "factorize",
            "description": "Factor a polynomial expression into its irreducible factors.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The polynomial to factorize. Example: 'x**2 - 4' or 'x**3 - 8'",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand_expression",
            "description": "Expand a factored or compact expression into its full form.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The expression to expand. Example: '(x+1)*(x-1)' or '(x+2)**3'",
                    },
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_statistics",
            "description": "Calculate statistical measures for a list of numbers: mean, median, mode, standard deviation, variance, min, max, range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "List of numbers to analyze. Example: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]",
                    },
                },
                "required": ["numbers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_units",
            "description": "Convert between common units (length, weight, temperature, time, data).",
            "parameters": {
                "type": "object",
                "properties": {
                    "value": {
                        "type": "number",
                        "description": "The numeric value to convert.",
                    },
                    "from_unit": {
                        "type": "string",
                        "description": "The source unit. Examples: 'km', 'miles', 'kg', 'lbs', 'celsius', 'fahrenheit', 'bytes', 'mb', 'gb'",
                    },
                    "to_unit": {
                        "type": "string",
                        "description": "The target unit. Examples: 'miles', 'km', 'lbs', 'kg', 'fahrenheit', 'celsius', 'mb', 'gb'",
                    },
                },
                "required": ["value", "from_unit", "to_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": "Search Baby's memory for information about the user (name, preferences, favorites, personal details, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for. Examples: 'my name', 'my favorite color', 'what do I like', 'my workplace', 'my hobbies'",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

MATH_TOOL_RISK = {t["function"]["name"]: "low" for t in MATH_TOOLS_SCHEMA if isinstance(t, dict) and isinstance(t.get("function"), dict)}


# ─── Tool Implementations ─────────────────────────────────────────────────────

def _safe_sympy():
    """Lazy import of sympy with error handling."""
    try:
        import sympy
        return sympy
    except ImportError:
        return None


def evaluate_expression(expression: str, variables: dict | None = None) -> dict:
    """Evaluate a mathematical expression using SymPy."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, pi, E, oo, zoo, I, sqrt, log, sin, cos, tan, exp

        # Create local namespace with common math functions
        local_dict = {
            "pi": pi, "e": E, "inf": oo, "infinity": oo,
            "zoo": zoo, "I": I, "i": I,
            "sqrt": sqrt, "log": log, "ln": log,
            "sin": sin, "cos": cos, "tan": tan,
            "exp": exp, "abs": abs,
        }

        # Add user variables
        if variables:
            for k, v in variables.items():
                local_dict[k] = sympify(v)

        # Parse and evaluate
        expr = sympify(expression, locals=local_dict)

        # If there are free symbols, substitute variables
        if expr.free_symbols and variables:
            subs_dict = {sympy.Symbol(k): sympify(v) for k, v in variables.items()}
            result = expr.subs(subs_dict)
        else:
            result = expr

        # Try to get numeric value
        try:
            numeric_result = float(result.evalf())
            is_numeric = True
        except (TypeError, ValueError):
            numeric_result = None
            is_numeric = False

        return {
            "success": True,
            "expression": str(expr),
            "result": str(result),
            "latex": sympy.latex(result),
            "numeric": numeric_result,
            "is_numeric": is_numeric,
            "simplified": str(sympy.simplify(result)),
        }
    except Exception as e:
        logger.error("[MathTools] evaluate_expression failed: {}", e)
        return {"error": f"Failed to evaluate expression: {e}"}


def solve_equation(equations: list[str], variables: list[str]) -> dict:
    """Solve equations using SymPy."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, Eq, Symbol, solve

        # Parse equations
        eq_list = []
        for eq_str in equations:
            if "==" in eq_str:
                left, right = eq_str.split("==", 1)
                eq_list.append(Eq(sympify(left.strip()), sympify(right.strip())))
            else:
                # Assume expression == 0
                eq_list.append(Eq(sympify(eq_str.strip()), 0))

        # Create symbols
        sym_list = [Symbol(v) for v in variables]

        # Solve
        solution = solve(eq_list, sym_list, dict=True)

        # Format results
        formatted = []
        for sol in solution:
            formatted.append({str(k): str(v) for k, v in sol.items()})

        return {
            "success": True,
            "equations": [str(eq) for eq in eq_list],
            "variables": variables,
            "solutions": formatted,
            "latex": [sympy.latex(eq) for eq in eq_list],
            "solution_latex": [sympy.latex(sol) for sol in solution] if solution else [],
        }
    except Exception as e:
        logger.error("[MathTools] solve_equation failed: {}", e)
        return {"error": f"Failed to solve equation: {e}"}


def simplify_expression(expression: str) -> dict:
    """Simplify a mathematical expression."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, simplify, trigsimp

        expr = sympify(expression)
        simplified = simplify(expr)
        trig_simplified = trigsimp(expr)

        return {
            "success": True,
            "original": str(expr),
            "simplified": str(simplified),
            "trig_simplified": str(trig_simplified),
            "latex": sympy.latex(simplified),
            "trig_latex": sympy.latex(trig_simplified),
        }
    except Exception as e:
        logger.error("[MathTools] simplify_expression failed: {}", e)
        return {"error": f"Failed to simplify expression: {e}"}


def differentiate(expression: str, variable: str = "x", order: int = 1) -> dict:
    """Compute the derivative of an expression."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, Symbol, diff, simplify

        expr = sympify(expression)
        var = Symbol(variable)
        derivative = diff(expr, var, order)
        simplified = simplify(derivative)

        return {
            "success": True,
            "original": str(expr),
            "variable": variable,
            "order": order,
            "derivative": str(derivative),
            "simplified": str(simplified),
            "latex": sympy.latex(simplified),
        }
    except Exception as e:
        logger.error("[MathTools] differentiate failed: {}", e)
        return {"error": f"Failed to differentiate: {e}"}


def integrate(expression: str, variable: str = "x",
              lower_limit: str | None = None, upper_limit: str | None = None) -> dict:
    """Compute the integral of an expression."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, Symbol, integrate as sym_integrate, simplify

        expr = sympify(expression)
        var = Symbol(variable)

        if lower_limit and upper_limit:
            # Definite integral
            lower = sympify(lower_limit)
            upper = sympify(upper_limit)
            result = sym_integrate(expr, (var, lower, upper))
            integral_type = "definite"
        else:
            # Indefinite integral
            result = sym_integrate(expr, var)
            integral_type = "indefinite"

        simplified = simplify(result)

        return {
            "success": True,
            "original": str(expr),
            "variable": variable,
            "integral_type": integral_type,
            "limits": f"[{lower_limit}, {upper_limit}]" if lower_limit and upper_limit else None,
            "integral": str(result),
            "simplified": str(simplified),
            "latex": sympy.latex(simplified),
        }
    except Exception as e:
        logger.error("[MathTools] integrate failed: {}", e)
        return {"error": f"Failed to integrate: {e}"}


def factorize(expression: str) -> dict:
    """Factor a polynomial expression."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, factor, factorint

        expr = sympify(expression)
        factored = factor(expr)

        # Also try to get integer factorization if it's a number
        int_factors = None
        try:
            num = int(expr)
            int_factors = factorint(num)
        except (TypeError, ValueError):
            pass

        return {
            "success": True,
            "original": str(expr),
            "factored": str(factored),
            "latex": sympy.latex(factored),
            "integer_factors": int_factors,
        }
    except Exception as e:
        logger.error("[MathTools] factorize failed: {}", e)
        return {"error": f"Failed to factorize: {e}"}


def expand_expression(expression: str) -> dict:
    """Expand a factored expression."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import sympify, expand

        expr = sympify(expression)
        expanded = expand(expr)

        return {
            "success": True,
            "original": str(expr),
            "expanded": str(expanded),
            "latex": sympy.latex(expanded),
        }
    except Exception as e:
        logger.error("[MathTools] expand_expression failed: {}", e)
        return {"error": f"Failed to expand expression: {e}"}


def calculate_statistics(numbers: list[float]) -> dict:
    """Calculate statistical measures for a list of numbers."""
    import statistics

    if not numbers:
        return {"error": "No numbers provided"}

    try:
        result = {
            "success": True,
            "count": len(numbers),
            "mean": statistics.mean(numbers),
            "median": statistics.median(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "range": max(numbers) - min(numbers),
            "sum": sum(numbers),
        }

        # Standard deviation and variance (need at least 2 numbers)
        if len(numbers) >= 2:
            result["stdev"] = statistics.stdev(numbers)
            result["variance"] = statistics.variance(numbers)

        # Mode (may fail if all values are unique)
        try:
            result["mode"] = statistics.mode(numbers)
        except statistics.StatisticsError:
            result["mode"] = None
            result["mode_note"] = "No unique mode (all values appear equally)"

        # Round for readability
        for key in ["mean", "median", "stdev", "variance"]:
            if key in result and result[key] is not None:
                result[key] = round(result[key], 4)

        return result
    except Exception as e:
        logger.error("[MathTools] calculate_statistics failed: {}", e)
        return {"error": f"Failed to calculate statistics: {e}"}


# Unit conversion table
_UNIT_CONVERSIONS = {
    # Length
    ("km", "miles"): lambda x: x * 0.621371,
    ("miles", "km"): lambda x: x * 1.60934,
    ("m", "feet"): lambda x: x * 3.28084,
    ("feet", "m"): lambda x: x * 0.3048,
    ("cm", "inches"): lambda x: x * 0.393701,
    ("inches", "cm"): lambda x: x * 2.54,
    ("mm", "inches"): lambda x: x * 0.0393701,
    # Weight
    ("kg", "lbs"): lambda x: x * 2.20462,
    ("lbs", "kg"): lambda x: x * 0.453592,
    ("g", "oz"): lambda x: x * 0.035274,
    ("oz", "g"): lambda x: x * 28.3495,
    # Temperature
    ("celsius", "fahrenheit"): lambda x: x * 9/5 + 32,
    ("fahrenheit", "celsius"): lambda x: (x - 32) * 5/9,
    ("celsius", "kelvin"): lambda x: x + 273.15,
    ("kelvin", "celsius"): lambda x: x - 273.15,
    # Data
    ("bytes", "kb"): lambda x: x / 1024,
    ("kb", "mb"): lambda x: x / 1024,
    ("mb", "gb"): lambda x: x / 1024,
    ("gb", "tb"): lambda x: x / 1024,
    ("gb", "mb"): lambda x: x * 1024,
    ("mb", "kb"): lambda x: x * 1024,
    ("kb", "bytes"): lambda x: x * 1024,
    # Time
    ("hours", "minutes"): lambda x: x * 60,
    ("minutes", "seconds"): lambda x: x * 60,
    ("days", "hours"): lambda x: x * 24,
    ("weeks", "days"): lambda x: x * 7,
    ("hours", "seconds"): lambda x: x * 3600,
    ("seconds", "milliseconds"): lambda x: x * 1000,
    # Volume
    ("liters", "ml"): lambda x: x * 1000,
    ("ml", "liters"): lambda x: x / 1000,
    ("gallons", "liters"): lambda x: x * 3.78541,
    ("liters", "gallons"): lambda x: x / 3.78541,
    ("cups", "ml"): lambda x: x * 236.588,
    ("oz", "ml"): lambda x: x * 29.5735,
    # Speed
    ("mph", "kmh"): lambda x: x * 1.60934,
    ("kmh", "mph"): lambda x: x / 1.60934,
    ("mph", "ms"): lambda x: x * 0.44704,
    ("kmh", "ms"): lambda x: x / 3.6,
    ("knots", "kmh"): lambda x: x * 1.852,
    # Angle
    ("degrees", "radians"): lambda x: x * math.pi / 180,
    ("radians", "degrees"): lambda x: x * 180 / math.pi,
}


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    """Convert between common units."""
    from_key = from_unit.lower().strip()
    to_key = to_unit.lower().strip()

    if from_key == to_key:
        return {"success": True, "value": value, "from": from_unit, "to": to_unit, "result": value}

    conversion = _UNIT_CONVERSIONS.get((from_key, to_key))
    if conversion:
        result = conversion(value)
        return {
            "success": True,
            "value": value,
            "from": from_unit,
            "to": to_unit,
            "result": round(result, 6),
        }

    return {"error": f"Unknown conversion: {from_unit} → {to_unit}"}


def matrix_operations(operation: str, matrix_a: list[list[float]], matrix_b: list[list[float]] | None = None) -> dict:
    """Perform matrix operations using SymPy."""
    sympy = _safe_sympy()
    if sympy is None:
        return {"error": "SymPy is not installed. Run: pip install sympy"}

    try:
        from sympy import Matrix, ones, eye

        A = Matrix(matrix_a)

        if operation == "transpose":
            result = A.T
            return {"success": True, "operation": "transpose", "result": result.tolist(), "latex": sympy.latex(result)}

        if operation == "determinant":
            if A.rows != A.cols:
                return {"error": "Determinant requires a square matrix"}
            det = A.det()
            num_val = None
            try:
                if getattr(det, "is_number", False):
                    num_val = float(str(det.evalf()))
            except (TypeError, ValueError):
                num_val = None
            return {"success": True, "operation": "determinant", "result": str(det), "numeric": num_val, "latex": sympy.latex(det)}

        if operation == "trace":
            if A.rows != A.cols:
                return {"error": "Trace requires a square matrix"}
            tr = A.trace()
            tr_num = None
            try:
                if getattr(tr, "is_number", False):
                    tr_num = float(str(tr.evalf()))
            except (TypeError, ValueError):
                tr_num = None
            return {"success": True, "operation": "trace", "result": str(tr), "numeric": tr_num}

        if operation == "rank":
            r = A.rank()
            return {"success": True, "operation": "rank", "result": r}

        if operation == "inverse":
            if A.rows != A.cols:
                return {"error": "Inverse requires a square matrix"}
            if A.det() == 0:
                return {"error": "Matrix is singular (determinant = 0), cannot invert"}
            inv = A.inv()
            return {"success": True, "operation": "inverse", "result": inv.tolist(), "latex": sympy.latex(inv)}

        if operation == "multiply":
            if matrix_b is None:
                return {"error": "Second matrix (matrix_b) required for multiplication"}
            B = Matrix(matrix_b)
            if A.cols != B.rows:
                return {"error": f"Dimension mismatch: {A.rows}x{A.cols} cannot multiply with {B.rows}x{B.cols}"}
            result = A * B
            return {"success": True, "operation": "multiply", "result": result.tolist(), "latex": sympy.latex(result)}

        if operation == "add":
            if matrix_b is None:
                return {"error": "Second matrix (matrix_b) required for addition"}
            B = Matrix(matrix_b)
            if A.rows != B.rows or A.cols != B.cols:
                return {"error": "Dimension mismatch for addition"}
            result = A + B
            return {"success": True, "operation": "add", "result": result.tolist(), "latex": sympy.latex(result)}

        if operation == "subtract":
            if matrix_b is None:
                return {"error": "Second matrix (matrix_b) required for subtraction"}
            B = Matrix(matrix_b)
            if A.rows != B.rows or A.cols != B.cols:
                return {"error": "Dimension mismatch for subtraction"}
            result = A - B
            return {"success": True, "operation": "subtract", "result": result.tolist(), "latex": sympy.latex(result)}

        return {"error": f"Unknown matrix operation: {operation}"}

    except Exception as e:
        logger.error("[MathTools] matrix_operations failed: {}", e)
        return {"error": f"Matrix operation failed: {e}"}


def base_conversion(value: str, from_base: int, to_base: int) -> dict:
    """Convert a number between different bases."""
    try:
        if not (2 <= from_base <= 36) or not (2 <= to_base <= 36):
            return {"error": "Bases must be between 2 and 36"}

        # Parse the input number
        decimal_value = int(value.strip(), from_base)

        # Convert to target base
        if decimal_value == 0:
            result = "0"
        else:
            digits = []
            n = abs(decimal_value)
            while n > 0:
                remainder = n % to_base
                if remainder < 10:
                    digits.append(str(remainder))
                else:
                    digits.append(chr(ord('A') + remainder - 10))
                n //= to_base
            if decimal_value < 0:
                digits.append('-')
            result = ''.join(reversed(digits))

        # Also provide common bases for reference
        common = {}
        for base_name, base_val in [("binary", 2), ("octal", 8), ("decimal", 10), ("hexadecimal", 16)]:
            if base_val != to_base:
                if base_val == 10:
                    common[base_name] = str(decimal_value)
                else:
                    common[base_name] = format(decimal_value, f"0{max(1, len(result))}X" if base_val == 16 else 'b') if base_val == 2 else oct(decimal_value)[2:]

        return {
            "success": True,
            "input": value,
            "from_base": from_base,
            "to_base": to_base,
            "result": result,
            "decimal": decimal_value,
            "common_bases": common,
        }
    except ValueError as e:
        return {"error": f"Invalid number for base {from_base}: {e}"}
    except Exception as e:
        logger.error("[MathTools] base_conversion failed: {}", e)
        return {"error": f"Base conversion failed: {e}"}


def list_primes(limit: int | None = None, nth: int | None = None) -> dict:
    """List primes up to a limit or find the Nth prime."""
    try:
        def is_prime(n):
            if n < 2:
                return False
            if n < 4:
                return True
            if n % 2 == 0 or n % 3 == 0:
                return False
            i = 5
            while i * i <= n:
                if n % i == 0 or n % (i + 2) == 0:
                    return False
                i += 6
            return True

        if nth is not None and nth >= 1:
            count = 0
            num = 1
            while count < nth:
                num += 1
                if is_prime(num):
                    count += 1
            return {
                "success": True,
                "operation": "nth_prime",
                "n": nth,
                "result": num,
                "latex": f"p_{{{nth}}} = {num}",
            }

        if limit is not None:
            primes = [n for n in range(2, limit + 1) if is_prime(n)]
            return {
                "success": True,
                "operation": "primes_up_to",
                "limit": limit,
                "count": len(primes),
                "primes": primes,
                "latex": ", ".join(map(str, primes[:20])) + ("..." if len(primes) > 20 else ""),
            }

        return {"error": "Provide either 'limit' or 'nth'"}

    except Exception as e:
        logger.error("[MathTools] list_primes failed: {}", e)
        return {"error": f"Prime calculation failed: {e}"}


def scientific_constants(constant: str) -> dict:
    """Get common mathematical and physical constants."""
    import math

    CONSTANTS = {
        "pi": {"value": math.pi, "symbol": "\\pi", "name": "Pi", "description": "Ratio of circumference to diameter"},
        "e": {"value": math.e, "symbol": "e", "name": "Euler's number", "description": "Base of natural logarithm"},
        "phi": {"value": (1 + math.sqrt(5)) / 2, "symbol": "\\phi", "name": "Golden Ratio", "description": "1.618..."},
        "tau": {"value": 2 * math.pi, "symbol": "\\tau", "name": "Tau", "description": "2*pi, full circle ratio"},
        "sqrt2": {"value": math.sqrt(2), "symbol": "\\sqrt{2}", "name": "Square root of 2", "description": "1.4142..."},
        "c": {"value": 299792458, "symbol": "c", "name": "Speed of light", "description": "m/s in vacuum"},
        "g": {"value": 9.80665, "symbol": "g", "name": "Standard gravity", "description": "m/s^2"},
        "h": {"value": 6.62607015e-34, "symbol": "h", "name": "Planck constant", "description": "J*s"},
        "k": {"value": 1.380649e-23, "symbol": "k_B", "name": "Boltzmann constant", "description": "J/K"},
        "NA": {"value": 6.02214076e23, "symbol": "N_A", "name": "Avogadro's number", "description": "mol^-1"},
        "R": {"value": 8.314462618, "symbol": "R", "name": "Gas constant", "description": "J/(mol*K)"},
        "epsilon0": {"value": 8.8541878128e-12, "symbol": "\\epsilon_0", "name": "Vacuum permittivity", "description": "F/m"},
    }

    key = constant.strip().lower()
    if key in CONSTANTS:
        c = CONSTANTS[key]
        return {
            "success": True,
            "constant": c["name"],
            "symbol": c["symbol"],
            "value": c["value"],
            "description": c["description"],
            "latex": f"{c['symbol']} = {c['value']}",
        }

    return {"error": f"Unknown constant: '{constant}'. Available: {', '.join(CONSTANTS.keys())}"}


def memory_recall(query: str = "", **kwargs) -> dict:
    """
    Search Baby's memory for information about the user.
    
    Args:
        query: What to search for (e.g., "my name", "my favorite color", "what do I like")
        
    Returns:
        dict: Search results with matching facts about the user
    """
    if not query:
        # If no query, return all stored profile information
        try:
            from core.memory_engine import get_memory
            memory_engine = get_memory()
            profile_block = memory_engine.get_profile_system_block()
            if profile_block:
                return {"success": True, "query": "all", "results": profile_block}
            else:
                return {"success": True, "query": "all", "results": "No stored information yet."}
        except Exception as e:
            logger.error("[MathTools] Failed to retrieve memory: {}", e)
            return {"success": False, "error": f"Failed to retrieve memory: {str(e)}"}
    
    try:
        from core.memory_engine import get_memory
        memory_engine = get_memory()
        
        # Use the memory engine's recall method
        results = memory_engine.memory_recall(query)
        
        if results:
            return {"success": True, "query": query, "results": results}
        else:
            return {"success": True, "query": query, "results": "No matching information found in memory."}
    except Exception as e:
        logger.error("[MathTools] Memory recall failed: {}", e)
        return {"success": False, "error": f"Memory recall failed: {str(e)}"}


# ─── Dispatcher ───────────────────────────────────────────────────────────────

_MATH_REGISTRY = {
    "evaluate_expression": evaluate_expression,
    "solve_equation": solve_equation,
    "simplify_expression": simplify_expression,
    "differentiate": differentiate,
    "integrate": integrate,
    "factorize": factorize,
    "expand_expression": expand_expression,
    "calculate_statistics": calculate_statistics,
    "convert_units": convert_units,
    "matrix_operations": matrix_operations,
    "base_conversion": base_conversion,
    "list_primes": list_primes,
    "scientific_constants": scientific_constants,
    "memory_recall": memory_recall,
}


def execute_math_tool(name: str, args: dict) -> dict:
    """Execute a math tool by name with arguments."""
    fn = _MATH_REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown math tool: {name}"}

    try:
        # Normalize argument names (handle LLM variations)
        normalized = {}
        for key, value in args.items():
            normalized[key.lower().strip()] = value

        result = fn(**normalized)
        logger.info("[MathTools] Executed '{}': success={}", name, result.get("success", False))
        return result
    except TypeError as e:
        # Handle argument mismatches
        logger.error("[MathTools] Argument error for '{}': {}", name, e)
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        logger.error("[MathTools] Execution error for '{}': {}", name, e)
        return {"error": f"Math tool error: {e}"}



















