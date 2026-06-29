# Welcome to the TANGO Team

## How We Use Claude

Based on Chad Baker's usage over the last 30 days:

**Work Type Breakdown:**
```
Improve Quality  ████████████░░░░░░░░  ~38%
Build Feature    ████████░░░░░░░░░░░░  ~25%
Debug Fix        ██████░░░░░░░░░░░░░░  ~19%
Plan Design      ████░░░░░░░░░░░░░░░░  ~12%
Write Docs       ██░░░░░░░░░░░░░░░░░░  ~6%
```

**Top Skills & Commands:**
```
/compact   ████████████████████  1x/month
/clear     ████████████████████  1x/month
/effort    ████████████████████  1x/month
```

**Top MCP Servers:** (none configured)

## Your Setup Checklist

### Codebases
- [ ] tango-core — main simulation framework
- [ ] tango-super — monorepo wrapper / integration layer
- [ ] [fastsim](https://github.com/NatLabRockies/fastsim) — reference implementation (Rust); used for design patterns
- [ ] python-template — team project scaffolding template
- [ ] GEOPHIRES-X — geothermal resource estimation tool
- [ ] geg-dvc-data-registry — DVC-backed data registry (GCS remote)

### MCP Servers to Activate
  (none in use — nothing to configure)

### Skills to Know About
- `/compact` — summarizes the conversation to free up context when a session
  runs long; use it before switching topics or when Claude starts losing track
- `/clear` — wipes the conversation and starts fresh; useful between unrelated
  tasks in the same project
- `/effort` — adjusts how much thinking Claude puts into a response; handy for
  quick questions vs. deep architectural work

## Team Tips

- **You do the commits.** Claude will propose a commit message when the work is
  ready, but you run `git commit` yourself. This keeps you in control of what
  goes into the history and makes it easy to review before it lands.

## Get Started

### 0. Clone the repo and check out the active branch

First, make sure your SSH key is registered with ETH GitLab —
[SSH setup guide](https://gitlab.ethz.ch/geg/computing-guide/-/wikis/ssh).

Then clone and switch to the active development branch
([MR !59](https://gitlab.ethz.ch/geg/tango-projects/tango-core/-/merge_requests/59)):

```bash
git clone git@gitlab.ethz.ch:geg/tango-projects/tango-core.git
cd tango-core
git checkout dev/tango-intern-tasks
uv sync --group dev
```

### Parity test porting workflow

A great first task is porting an old-tango example to tango_next and getting
the parity test to pass.  Here's the workflow:

**1. Run the parity tests to see what needs work.**

```bash
uv run pytest tests/regtest/test_old_new_parity.py -v
```

You'll see one passing case (`flexible_SF_manual.yml`) and the remaining
stubs marked as expected failures (`xfailed`).  Pick one stub.

**2. Create the tango_next config file.**

The old config lives in `examples/<name>.yml`.  The new format goes in
`examples/tango_next/<name>.yml`.  Use
`examples/tango_next/flexible_SF_manual.yml` as a template — the header
comments in that file explain every structural change.

You have a few options for doing the conversion:
- **Manual** — follow the template and the `ADDING A NEW CASE` instructions
  at the top of `tests/regtest/test_old_new_parity.py`.  This is the most
  reliable approach and the one we'd recommend starting with.
- **LLM-assisted** — paste the old YAML and the template into Claude and ask
  it to convert.  Fast but not deterministic; always review the output
  carefully against the old file before trusting it.

**3. Wire up the test case.**

In `tests/regtest/test_old_new_parity.py`, find the stub `ParityCase` for
your case and fill in `new_yml` and the tolerance fields.  Set `res_T_atol`,
`prod_T_atol`, and `power_rtol` to values that make physical sense — start
loose and tighten once the test passes.

**4. Verify what's being compared makes sense.**

The test compares per-timestep histories for reservoir outlet T, production
well outlet T, and gross power.  Before locking in tolerances, print both
histories and sanity-check the shape of the curves.  If the new result
looks physically wrong, investigate before adjusting the tolerance.

**5. Investigate discrepancies — don't just widen tolerances.**

When the values don't match, ask whether the difference is a known
deliberate deviation (e.g. tango_next's 1-step-lag fix) or a bug.  Old
tango has known logic flaws; if you find one, document it in the `notes`
field of the `ParityCase` and in the PR description rather than silently
absorbing it into a wide tolerance.

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
