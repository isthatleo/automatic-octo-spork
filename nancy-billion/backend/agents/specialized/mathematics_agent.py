"""
Mathematics Agent for Nancy/Billion Backend
Real number theory, combinatorics, polynomial calculus, and linear algebra --
all computed exactly/numerically via numpy (already a project dependency),
never via eval()/exec() on caller-supplied expression strings. Polynomials
and matrices are passed as structured coefficient/row lists, not free-text
formulas, so there is no code-injection surface here.
"""
from __future__ import annotations

import math
import logging
from typing import Any, Dict, List

import numpy as np

from .base_specialized_agent import SpecializedAgent

logger = logging.getLogger(__name__)


class MathematicsAgent(SpecializedAgent):
    """Pure mathematics: number theory, combinatorics, polynomial calculus, linear algebra"""

    def __init__(self, settings):
        super().__init__(settings, "Mathematics Agent", "mathematics")
        self.capabilities.update({
            "description": (
                "Pure mathematics agent: real number theory (primality, factorization, GCD/LCM), "
                "combinatorics, exact polynomial root-finding/calculus, linear algebra (determinant, "
                "inverse, eigenvalues, linear-system solving), and classic sequences -- all computed "
                "exactly via numpy, no expression-string evaluation."
            ),
            "confidence": 0.88,
            "specializations": [
                "number-theory",
                "combinatorics",
                "polynomial-algebra-calculus",
                "linear-algebra",
                "sequences",
            ],
            "tools": ["numpy-linalg", "polynomial-root-finder"],
        })

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task_type = task_data.get("type", "number-theory")
        try:
            if task_type == "number-theory":
                return self._number_theory(task_data)
            elif task_type == "combinatorics":
                return self._combinatorics(task_data)
            elif task_type == "polynomial-roots":
                return self._polynomial_roots(task_data)
            elif task_type == "polynomial-calculus":
                return self._polynomial_calculus(task_data)
            elif task_type == "linear-algebra":
                return self._linear_algebra(task_data)
            elif task_type == "sequence":
                return self._sequence(task_data)
            else:
                return await self._general_query(task_data)
        except Exception as e:
            return {"success": False, "error": str(e), "task_type": task_type}

    # ------------------------------------------------------------------
    # Real number theory
    # ------------------------------------------------------------------

    @staticmethod
    def _is_prime(n: int) -> bool:
        if n < 2:
            return False
        if n in (2, 3):
            return True
        if n % 2 == 0:
            return False
        for i in range(3, int(math.isqrt(n)) + 1, 2):
            if n % i == 0:
                return False
        return True

    @staticmethod
    def _factorize(n: int) -> List[int]:
        n = abs(n)
        factors = []
        d = 2
        while d * d <= n:
            while n % d == 0:
                factors.append(d)
                n //= d
            d += 1
        if n > 1:
            factors.append(n)
        return factors

    def _number_theory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        op = str(params.get("operation", "is_prime"))

        if op == "is_prime":
            n = int(params.get("n", 2))
            return {"success": True, "task_type": "number-theory", "operation": op, "n": n, "is_prime": self._is_prime(n)}

        if op == "factorize":
            n = int(params.get("n", 60))
            factors = self._factorize(n)
            from collections import Counter
            counts = Counter(factors)
            return {
                "success": True, "task_type": "number-theory", "operation": op, "n": n,
                "prime_factors": factors,
                "factorization": " * ".join(f"{p}^{c}" if c > 1 else str(p) for p, c in sorted(counts.items())),
            }

        if op == "gcd_lcm":
            a = int(params.get("a", 12))
            b = int(params.get("b", 18))
            g = math.gcd(a, b)
            lcm = abs(a * b) // g if g else 0
            return {"success": True, "task_type": "number-theory", "operation": op, "a": a, "b": b, "gcd": g, "lcm": lcm}

        if op == "mod_pow":
            base = int(params.get("base", 2))
            exponent = int(params.get("exponent", 10))
            modulus = int(params.get("modulus", 1000))
            return {"success": True, "task_type": "number-theory", "operation": op,
                    "base": base, "exponent": exponent, "modulus": modulus,
                    "result": pow(base, exponent, modulus)}

        return {"success": False, "task_type": "number-theory", "error": f"Unknown operation '{op}'",
                "known_operations": ["is_prime", "factorize", "gcd_lcm", "mod_pow"]}

    # ------------------------------------------------------------------
    # Real combinatorics
    # ------------------------------------------------------------------

    def _combinatorics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        op = str(params.get("operation", "combinations"))
        n = int(params.get("n", 10))
        r = int(params.get("r", 3))

        if op == "factorial":
            return {"success": True, "task_type": "combinatorics", "operation": op, "n": n, "result": math.factorial(n)}
        if op == "permutations":
            if r > n or n < 0 or r < 0:
                return {"success": False, "task_type": "combinatorics", "error": "require 0 <= r <= n"}
            return {"success": True, "task_type": "combinatorics", "operation": op, "n": n, "r": r,
                    "result": math.perm(n, r), "formula": "n! / (n-r)!"}
        if op == "combinations":
            if r > n or n < 0 or r < 0:
                return {"success": False, "task_type": "combinatorics", "error": "require 0 <= r <= n"}
            return {"success": True, "task_type": "combinatorics", "operation": op, "n": n, "r": r,
                    "result": math.comb(n, r), "formula": "n! / (r! * (n-r)!)"}

        return {"success": False, "task_type": "combinatorics", "error": f"Unknown operation '{op}'",
                "known_operations": ["factorial", "permutations", "combinations"]}

    # ------------------------------------------------------------------
    # Real polynomial roots (numpy.roots -- eigenvalues of the companion
    # matrix; exact numerical method, no expression parsing)
    # ------------------------------------------------------------------

    def _polynomial_roots(self, params: Dict[str, Any]) -> Dict[str, Any]:
        coefficients = params.get("coefficients")  # highest degree first, e.g. [1, -3, 2] for x^2-3x+2
        if not isinstance(coefficients, list) or len(coefficients) < 2:
            return {"success": False, "task_type": "polynomial-roots", "error": "'coefficients' (list, highest degree first, e.g. [1,-3,2] for x^2-3x+2) is required"}

        roots = np.roots([float(c) for c in coefficients])
        real_roots = [complex(r) for r in roots]
        formatted = []
        for r in real_roots:
            if abs(r.imag) < 1e-9:
                formatted.append({"real": round(r.real, 8), "imaginary": 0.0, "is_real": True})
            else:
                formatted.append({"real": round(r.real, 8), "imaginary": round(r.imag, 8), "is_real": False})

        return {
            "success": True,
            "task_type": "polynomial-roots",
            "coefficients": coefficients,
            "degree": len(coefficients) - 1,
            "roots": formatted,
            "method": "numpy.roots (companion-matrix eigenvalues) -- exact numerical root-finding",
        }

    # ------------------------------------------------------------------
    # Real polynomial calculus (exact analytic derivative/integral --
    # power-rule formulas, not numerical approximation)
    # ------------------------------------------------------------------

    def _polynomial_calculus(self, params: Dict[str, Any]) -> Dict[str, Any]:
        coefficients = params.get("coefficients")  # highest degree first
        if not isinstance(coefficients, list) or not coefficients:
            return {"success": False, "task_type": "polynomial-calculus", "error": "'coefficients' (list, highest degree first) is required"}
        coefficients = [float(c) for c in coefficients]
        operation = str(params.get("operation", "derivative"))
        degree = len(coefficients) - 1

        if operation == "derivative":
            if degree == 0:
                return {"success": True, "task_type": "polynomial-calculus", "operation": operation,
                        "input_coefficients": coefficients, "result_coefficients": [0.0],
                        "method": "d/dx of a constant = 0"}
            result = [coefficients[i] * (degree - i) for i in range(degree)]
            return {
                "success": True, "task_type": "polynomial-calculus", "operation": operation,
                "input_coefficients": coefficients, "result_coefficients": result,
                "method": "Power rule: d/dx(a_n x^n) = n*a_n x^(n-1)",
            }

        if operation == "integral":
            constant_of_integration = float(params.get("constant_of_integration", 0.0))
            result = [coefficients[i] / (degree - i + 1) for i in range(len(coefficients))] + [constant_of_integration]
            output: Dict[str, Any] = {
                "success": True, "task_type": "polynomial-calculus", "operation": operation,
                "input_coefficients": coefficients, "result_coefficients": result,
                "method": "Power rule: integral(a_n x^n)dx = a_n/(n+1) x^(n+1) + C",
            }
            lower = params.get("definite_lower")
            upper = params.get("definite_upper")
            if lower is not None and upper is not None:
                def antiderivative_value(x: float) -> float:
                    total = 0.0
                    n_terms = len(result)
                    for i, coeff in enumerate(result):
                        power = n_terms - 1 - i
                        total += coeff * (x ** power)
                    return total
                definite_value = antiderivative_value(float(upper)) - antiderivative_value(float(lower))
                output["definite_integral"] = {"lower": lower, "upper": upper, "value": round(definite_value, 8)}
            return output

        return {"success": False, "task_type": "polynomial-calculus", "error": f"Unknown operation '{operation}'",
                "known_operations": ["derivative", "integral"]}

    # ------------------------------------------------------------------
    # Real linear algebra (numpy.linalg)
    # ------------------------------------------------------------------

    def _linear_algebra(self, params: Dict[str, Any]) -> Dict[str, Any]:
        matrix = params.get("matrix")
        if not isinstance(matrix, list) or not matrix:
            return {"success": False, "task_type": "linear-algebra", "error": "'matrix' (list of row-lists) is required"}
        operation = str(params.get("operation", "determinant"))
        arr = np.array(matrix, dtype=np.float64)

        try:
            if operation == "determinant":
                return {"success": True, "task_type": "linear-algebra", "operation": operation, "result": round(float(np.linalg.det(arr)), 8)}

            if operation == "inverse":
                inv = np.linalg.inv(arr)
                return {"success": True, "task_type": "linear-algebra", "operation": operation,
                        "result": [[round(float(v), 8) for v in row] for row in inv]}

            if operation == "eigenvalues":
                eigvals = np.linalg.eigvals(arr)
                formatted = [
                    {"real": round(float(v.real), 8), "imaginary": round(float(v.imag), 8)}
                    for v in eigvals
                ]
                return {"success": True, "task_type": "linear-algebra", "operation": operation, "result": formatted}

            if operation == "rank":
                return {"success": True, "task_type": "linear-algebra", "operation": operation, "result": int(np.linalg.matrix_rank(arr))}

            if operation == "solve":
                b = params.get("b")
                if not isinstance(b, list):
                    return {"success": False, "task_type": "linear-algebra", "error": "'b' (vector) is required for operation='solve'"}
                x = np.linalg.solve(arr, np.array(b, dtype=np.float64))
                return {"success": True, "task_type": "linear-algebra", "operation": operation,
                        "result": [round(float(v), 8) for v in x]}
        except np.linalg.LinAlgError as e:
            return {"success": False, "task_type": "linear-algebra", "operation": operation, "error": f"Matrix operation failed: {e}"}

        return {"success": False, "task_type": "linear-algebra", "error": f"Unknown operation '{operation}'",
                "known_operations": ["determinant", "inverse", "eigenvalues", "rank", "solve"]}

    # ------------------------------------------------------------------
    # Real classic sequences (closed-form / exact recurrence, not fabricated)
    # ------------------------------------------------------------------

    def _sequence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        seq_type = str(params.get("sequence_type", "fibonacci"))
        n = int(params.get("n", 10))
        if n < 1 or n > 10000:
            return {"success": False, "task_type": "sequence", "error": "'n' must be between 1 and 10000"}

        if seq_type == "fibonacci":
            values: List[int] = []
            a, b = 0, 1
            for _ in range(n):
                values.append(a)
                a, b = b, a + b
            return {"success": True, "task_type": "sequence", "sequence_type": seq_type, "n": n, "values": values}

        if seq_type == "primes":
            values = []
            candidate = 1
            while len(values) < n:
                candidate += 1
                if self._is_prime(candidate):
                    values.append(candidate)
            return {"success": True, "task_type": "sequence", "sequence_type": seq_type, "n": n, "values": values}

        if seq_type == "arithmetic":
            first = float(params.get("first_term", 1.0))
            diff = float(params.get("common_difference", 1.0))
            values = [first + i * diff for i in range(n)]
            return {"success": True, "task_type": "sequence", "sequence_type": seq_type, "n": n, "values": values,
                    "sum": round(sum(values), 6), "formula": "a_n = a_1 + (n-1)d"}

        if seq_type == "geometric":
            first = float(params.get("first_term", 1.0))
            ratio = float(params.get("common_ratio", 2.0))
            values = [first * (ratio ** i) for i in range(n)]
            return {"success": True, "task_type": "sequence", "sequence_type": seq_type, "n": n, "values": values,
                    "sum": round(sum(values), 6), "formula": "a_n = a_1 * r^(n-1)"}

        return {"success": False, "task_type": "sequence", "error": f"Unknown sequence_type '{seq_type}'",
                "known_types": ["fibonacci", "primes", "arithmetic", "geometric"]}

    async def _general_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "general mathematics question")
        answer = await self._llm_answer(query)
        return {
            "success": True,
            "task_type": "general-query",
            "query": query,
            **({"response": answer} if answer else {}),
            "capabilities_hint": [
                "number-theory — is_prime, factorize, gcd_lcm, mod_pow",
                "combinatorics — factorial, permutations, combinations",
                "polynomial-roots — exact roots via numpy.roots",
                "polynomial-calculus — exact derivative/integral (with optional definite bounds)",
                "linear-algebra — determinant, inverse, eigenvalues, rank, solve",
                "sequence — fibonacci, primes, arithmetic, geometric",
            ],
        }
