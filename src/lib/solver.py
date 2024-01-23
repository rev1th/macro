
from scipy import optimize
import logging

logger = logging.Logger(__name__)

# https://stackoverflow.com/questions/63377926/quick-question-use-the-default-value-of-the-scipy-optimize-minimize-tol-paramet
ROOT_TOLERANCE = 1e-12

def find_root(error_f, args: tuple[any], bracket: tuple[float] = None, init_guess: float = None, f_prime = None):
    if f_prime:
        solver = optimize.root_scalar(
                f=error_f,
                args=args,
                x0=init_guess,
                fprime=f_prime,
                method='newton',
            )
    else:
        try:
            assert len(bracket) == 2, f"Lower and Upper bounds expected in bracket for solver {bracket}"
            solver = optimize.root_scalar(
                    f=error_f,
                    args=args,
                    bracket=bracket,
                    method='brentq',
                )
        except Exception as e:
            if abs(error_f(bracket[1], *args)) <= ROOT_TOLERANCE:
                logger.error(f"Solver failed but using {bracket[1]}")
                return bracket[1]
            raise Exception(f"Solver failed with {e}")
    if not solver.converged:
        raise Exception(f"Failed to converge after {solver.iterations} iterations due to {solver.flag}")
    return solver.root
