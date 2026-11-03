# SPDX-FileCopyrightText: 2025 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

"""Defines series acceleration functions and classes that can be imported into difference functions

Keeping with the modular philosophy of Tango, however once tango is in production this may be deemed an unecessary module (i.e. just code the aitkens function where it is needed!)
"""


# A simple aitkens accelerator that can be imported for use on a scalar series. Heavily inspired by Bruce Gee's similar accelerator in RAFT
def aitken_relax(
    iteration: int,
    x_tilde: float,
    x_prev: float,
    r_prev: float | None,
    delta_prev: float | None,
    init_relax: float = 1,
    min_relax: float = 0.001,
    max_relax: float = 1000,
) -> tuple[float, float, float]:
    """Scalar Aitken (Irons-Tuck) relaxation for a fixed-point iteration
    x_tilde = f(x_prev).


    Inputs:
        iteration  : 0-based counter within this fixed-point loop
        x_tilde    : raw, un-relaxed new value g(x_prev)
        x_prev     : previously accepted (already relaxed) value
        r_prev     : residual from the previous call (None on iteration 0)
        delta_prev : relaxation factor used on the previous call (None on iteration 0)
        init_relax : relaxation factor to use before there's any history
        bounds     : (min, max) magnitude clip on the relaxation factor

    Outputs:
        x_new: aitkens series term
        r_new: residual of x_tilde (x_n+1) and x_prev (x_n) entered
        delta_prev: previous update delta

    Example:
        no_iters = 10

        r_prev = None
        delta_prev = None

        x_np1 = f(x_n)

        for i in range(no_iters):
            x_new, r_prev, delta_prev = aitken(iteration=i,x_tilde=x_np1,x_prev=x_n,r_prev=r_prev,delta_prev=delta_prev,init_relax=1,bounds=(0.001,1000))
            x_n = x_np1
            x_np1 = f(x_new) #Feeding the result of Aitken's straight back into the fixed point function is technically called Steffensen's method

    Reference
        See Aitken's Method wikipedia: https://en.wikipedia.org/wiki/Aitken%27s_delta-squared_process

    """
    r_new = x_tilde - x_prev

    if iteration == 0 or delta_prev is None or r_prev is None:
        delta = init_relax
        x_new = (1 - delta) * x_prev + delta * x_tilde
        return x_new, r_new, delta

    diff = r_new - r_prev
    if diff == 0:
        delta = delta_prev  # avoid the pole
    else:
        delta = -delta_prev * (r_prev * diff) / (diff * diff)
        sign = 1.0 if delta >= 0 else -1.0
        delta = sign * min(max(abs(delta), min_relax), max_relax)

    x_new = x_prev + delta * r_new

    return x_new, r_new, delta
