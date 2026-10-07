# Debugging and Numerical Discrepancies

Rules for investigating wrong results, failing regression tests, and
mismatches against old-TANGO benchmarks.

- **Never loosen a tolerance to make a failure go away.** When a result drifts
  from a benchmark (including old-TANGO comparisons), first explain *why* it
  differs and decide whether the difference is expected (e.g. a deliberate
  modeling change) or a bug that needs investigating. A tolerance may only be
  changed together with a written justification of the cause, and only with
  the user's approval.

- **Check an explanation against the evidence before offering it.** A proposed
  cause must account for the observed *magnitude* and *direction* of the error,
  not just plausibly relate to it. Before presenting a hypothesis, work out what
  it predicts (sign, size, which outputs move, which don't) and compare that to
  the data. If it hasn't been checked, say so explicitly rather than presenting
  it as the answer.
  - Example: crossing lines in a phase diagram turned out to be a reversed
    production-well rock temperature profile. Explanations that couldn't
    produce a sign reversal could have been ruled out immediately by asking
    "would this make the lines cross at all?"

- **Prefer finding the root cause over patching the symptom.** If a fix makes
  the numbers look right but the explanation for the original error is still
  missing, the investigation isn't finished.
