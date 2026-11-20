# IEEE Revisions Summary

## Replaced Research Narrative

The new IEEE LaTeX paper replaces broad or cross-workflow claims with a precise
description of the implementation. The title now emphasizes deterministic
constrained path planning and evidence-aware execution rather than unsupported
general closed-loop or formal-verification novelty.

## Sections Revised

- **Abstract:** distinguishes the three workflows and summarizes only
  retained evidence.
- **Introduction:** adds research questions and narrow contribution statements.
- **Related work:** replaces unsupported narrative citations with verifiable
  peer-reviewed/IETF references.
- **Architecture:** aligns the diagram with API, worker, Mininet/Ryu/OVS,
  compilation, measurement, and evidence flow.
- **Mathematical formulation:** defines exact configured aggregates,
  fail-closing, constraint operators, objective ranking, and fingerprint
  tie-breaking.
- **Methodology:** separates DESIGN preview, generalized LIVE execution, and
  legacy ONE_SHOT/CLOSED_LOOP bandwidth feedback.
- **Experimental setup:** records the fixed diamond, active measurement tools,
  repetition plan, timeout behavior, and missing environment metadata.
- **Results:** adds retained systematic counts, scenario differences,
  infrastructure failures, generalized runs, manual examples, and test results.
- **Discussion:** explains what the data demonstrate and do not demonstrate.
- **Limitations:** includes unequal samples, timeout selection bias, fixed
  topology, missing raw artifacts, software datapath, coarse packet-loss, and
  bounded search.
- **Conclusion:** reduces the central claim to implementation and narrow
  empirical evidence.

## Claims Strengthened or Removed

Removed claims of:

- statistically significant closed-loop improvement;
- general congestion control;
- scalability;
- independent baseline superiority;
- formal network-wide verification;
- LLM planning or LLM safety superiority;
- live random-topology evaluation;
- reproducibility of missing generalized or historical raw runs.

Retained only implementation-backed claims and clearly labeled isolated or
single-run demonstrations.

## Supporting Files

- `intentflow_ieee.tex`: complete revised IEEE conference paper.
- `IEEE_REVIEW_RESPONSE.md`: row-by-row reviewer response.
- `IEEE_RESEARCH_DOSSIER.md`: rewritten code-and-evidence dossier.
