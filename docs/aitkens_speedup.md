# Aitkens Speedup
## Introduction
### What does Aitkens Process Do?
Aitkens process accelerates the convergence of fixed point problems. Fixed point problems are problems where we want to find x so that $f(x) = x$. Often numerially the way to do this is to start with a guess $x_0$ and calculate $f(x_0)$ and then use this as the next guess, if we are lucky the series converges and eventually $f(x_n) \approx x_n$ within a tollerance. Cosine is a function that converges to a fixed point when starting with any guess angle in radians $x_{n+1} = Cos(x_n)$. It converges to "dotties number" $0.739085133 ...$. This method of feeding the output directly back into the function to iterate towards a solution is often refered to as the <em>Piccard</em> method:
$$x_n = f(x_{n-1})$$

<em>Aitken's</em> method builds on the Piccard method. It essentially augements our next guess term
$$x_{n+1} = f(x_n) + \frac{x_n - x_n{-1}}{x_n - 2x_{n-1} + x_{n-2}}$$
The fraction can be re-expressed using $\Delta x_n = x_n - x_n{n-1}$ and $\Delta x_n{x-1} = x_{n-1} - x{n-2}$ as
$$x_{n+1} = f(x_n) + \frac{\Delta x_n}{\Delta x_n - \Delta x_{n-1}}$$
This first term is taking the evaulation of $f(x_n)$ the second term is a damping/accelerating term. We can approximatley say that we amplify the series by adding the first derivative and dampen by the second derivative. E.g. if our convergence always trends in one direction Aitkens process will start to take bigger steps thanks to the first derivate. However if we are always "overshooting" the solution, the second derivate will dampen these overshots.

<img src="./diagrams/img/tango/cos_converge_example.png" alt="Example of Aitkens Process in action of Cos(x) = x" width="1100">

### The Fixed Point problem in Tango
We approximate the re-injection temperature in our power plants as a fixed point problem. Starting with a re-injection temperature $T_n$ we expect fluid to travel down the injection well(s), through the reservoir, up the production well(s) through the power plant/heat exchanger and be ready for re-injection at a temperature $T_{n+1}$ that is within a small tollerance (less than 0.5K) of the initial re-injection temperature $T_n$. We solve this problem at every timestep, starting with the solution from the last timestep.

Old tango solved this fixed point problem using piccards method
$$T_{n+1} = G(T_n)$$
In this branch Aitkens Process has been implemented
$$T_{n+1} = G(T_n) + \frac{\Delta T_n}{\Delta T_n - \Delta T_{n-1}}$$

## Method
### How this was coded up

To implement Aitkens process I defined a function ``aitken_relax`` in a new ``src/tango/core/accelerators.py``. And then imported this into ``system_bc_iteration.py`` to act as a function that changes the injection temperature between solves.

There are some important conditions placed on the Aitkens Process:
1. If the denominator is zero in Aitkens formula, we use the update value from the last term
2. We only start Aitkens process once we have enough of a Piccard series, i.e. on the third iteration if we start with a guess of None (first timestep), or on the second iteration if we have a value from the previous timestep.
3. There are limits on how much we can relax the series
4. On the very first <strong>timestep</strong> the injection temperature is ``nan`` this is dealt with by bypassing ``aitken_relax()`` with the check ``T_inj_prev > 0`` which 1. Should always be true for a numeric temperature value 2. All comparisons fail for ``nan`` value.

```python
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
```

### Eulers method for timestep temperature changes

I coded up a very simple method to try take a better first guess at the injection temperature at a new timestep rather than re-using the solution from the last timestep. Note that this was done several commits and merges ago with different parameter names.
$$T_{t+1} = T_{t} + (T_{t} - T_{t-1})$$
Basically just adding the Delta from the previous two timesteps. This had mixed results.
```python
if self.euler_on and (self.Tm2 is not None) and (self.Tm2 is not None):
    inj_well.inlet.T = (self.Tm1 + (self.Tm1 - self.Tm2))
```
The above was run before the convergence loop starts to update the inj_well.inlet.T with an initial extrapolated guess, then at the end of the loop we set $T_{t-1}$ to $T_{t-2}$ and we store the new result as $T_{t-1}$.
```python
self.Tm2 = self.Tm1
self.Tm1 = T_tilde
```

## Results
### Euler
Secondly I (with a bit of help from my friend Claude) wrote a demo using a prototype of the aitkens implementation ``system_bc_iteration_aitkens.py`` with the toggle attributes and ``self.euler_on: bool``.

Sweeping Euler (for SF and DF configurations) across mass rates leads to the following

| Mass Rate | Iterations Without Euler | Iterations With Euler | Decrease in Iterations (%) |
|-----------|---------------------------|-------------------------|------------------------------|
| 50 | 14 | 16 | -14.29 |
| 70 | 23 | 21 | 8.70 |
| 90 | 25 | 23 | 8.00 |
| 110 | 25 | 24 | 4.00 |
| 130 | 25 | 23 | 8.00 |
| 150 | 26 | 22 | 15.38 |

We see that for high mass rates Euler speeds up. When we look at the temperature over time for different mass rates, this makes sense:

<img src="./diagrams/img/tango/mass_rate_profiles.png" alt="Temperature over time for different mass rates" width="1100">

Using a high mass rate seems to smooth out the low to high temperature transition we see, which aligns better with a linear extrapolation. And also explains why Euler worked well in the $0.5 K$ sweep, which ran through the same mass rate sweep.

### Aitkens

For a standard run with ``_DT_SURFACE_TOL = 0.5`` Aitkens runs at the same speed as without. This can be verified by running ``uv run tools/run_tango_profile.py --profile`` on ``dev/tango-intern-tasks`` or some other branch without aitkens and on ``dev/aitkens-process``, as there is know way to remove aitkens from the orchestrator at this point.

## Discussion
### What tolerance $T_{n+1} - T_n < \epsilon$ should we be using?

Varying the surface tollerance from 0.5K to 1e-6K for single flash and double flash power plants has negligible impact on the production well temperature output and the net power output. However I have noticed that a lower tolerance helps with converging pressure and/or flow rate in auto injection modes running through a few runs at different pressure/flow rate convergence tollerances and temperature convergence tollerances, I found the rule of thumb that the temperature tolerance should be only around 500 times greater than the pressure/flow rate tolerance. So we should either bring down the surface tolerance to 0.05 K in line with the flow rate/pressure tolerance of 0.0001 or bring the flow rate/pressure tolerance up to 0.001.

## Conclusions

### When to use Euler

High mass rates (or other times when the temperature profile is smooth), as far as I can tell the times when in practice this is actual useful is a bit limited. I recommend discarding it from the code, considering most of the time it won't be useful and to know whether or not it would be, we would already need to know the result of the simulation.

### What I think was the best design for the code

<strong>Aitkens always on</strong>, this is the simplest way to do things. I have tried to keep the aitkens code as lean as possible so that it is not much slower than without Aitkens, this mean removing the ``aitkens_on`` tag, so there is no easy way for the user to toggle it on or off. Euler has been removed from the code, it was a relatively simple implenetation so it could be re-implemented quite easily if it becomes clear that there is a large array of simulations that would greatly benefit from it.

I have increased the convergence tolerance for pressure/flow rate to 0.001.
