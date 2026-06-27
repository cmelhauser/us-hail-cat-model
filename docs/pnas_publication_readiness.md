# PNAS Publication Readiness Memo

**Working manuscript:** *The Age of AI: Building a US Catastrophe Hail Model*  
**Status:** Promising, but contingent on final model results and reproducibility evidence  
**Last reviewed:** 2026-05-02

---

## Bottom Line

The article is potentially novel enough for a broad journal if it is framed as a rigorous case study in AI-assisted scientific infrastructure construction, demonstrated through a public radar-first US hail catastrophe hazard model. It is less likely to succeed if framed only as "an AI wrote a hail model" or only as "a new hail climatology."

The strongest claim is:

> Human-directed frontier AI agents can materially reduce the fixed cost of building transparent, auditable scientific hazard-model infrastructure, but only when paired with public data, explicit provenance, automated tests, human scientific review, and reproducibility controls.

The hail model is the scientific demonstration. The AI process is the cross-disciplinary significance.

---

## Literature Search Conclusion

### What already exists

The online literature indicates mature prior work in each separate ingredient:

- **Radar hail estimation:** MESH, SHI, MRMS, MYRORSS, GridRad, and corrected MESH/MESH75 relationships are well established.
- **Radar hail climatology:** MYRORSS, MRMS, and GridRad have been used to study severe hail occurrence and report bias.
- **Hail risk and damage modeling:** Academic and commercial work exists on hail claims, vulnerability, stochastic event structure, and damage estimation.
- **AI scientific agents:** Recent work includes tool-using chemistry agents, autonomous research systems, and multi-agent AI-human scientific workflows.
- **Journal AI policy:** PNAS-family instructions require disclosure of generative-AI use and do not permit AI systems to be authors.

### What appears distinctive

No reviewed source appears to combine all of the following in one transparent artifact:

1. a public-data, radar-first US hail catastrophe hazard pipeline;
2. daily source provenance distinguishing missing-source days from source-present no-hail days;
3. corrected daily hail rasters, sparse event templates, analytical return-period maps, and stochastic event catalogs;
4. a documented human-AI development process spanning literature review, implementation, testing, CI, data QA, git operations, long-run monitoring, and manuscript drafting;
5. an open repository intended to preserve the exact methods, commands, logs, and reproducibility controls.

That combination is the novelty argument.

---

## Recommended PNAS Framing

### Preferred title

The current title is memorable, but for PNAS it may benefit from a more precise subtitle:

```text
The Age of AI: Building a Transparent US Hail Catastrophe Model with Human-Directed Scientific Agents
```

### Central question

Can frontier AI agents help build scientific infrastructure, not merely write isolated code or draft text?

### Central answer

Yes, in this case study, but the value came from disciplined human-AI workflow design: source manifests, staged execution, tests, documentation, map QA, version control, and human interpretation.

### Claims to avoid

- Do not claim the first hail model.
- Do not claim the first radar hail climatology.
- Do not claim an AI independently discovered the model.
- Do not claim production insurance loss modeling until exposure, vulnerability, and financial terms are implemented.
- Do not claim validated climate-change trends from a short, source-transitioned radar record.

### Claims to emphasize

- First or among the first transparent case studies of AI-assisted catastrophe-model construction.
- Public-data hail hazard pipeline rather than proprietary black-box model.
- Auditable provenance distinguishing missing source from true no-hail days.
- Human-directed AI as a workflow for building and hardening scientific software.
- Reproducibility through tests, logs, documentation, and archived code release.

---

## Evidence Needed Before Submission

### Scientific evidence

The manuscript needs final values for:

- total processed days and source coverage by era (MYRORSS 5,023; GridRad 2,501+; MRMS 2,060 as of 2026-06-27);
- manifest status counts by year (Stage 01 and Stage 04c manifests on disk);
- missing-source versus no-hail days (712 GridRad `missing_source` rows documented);
- corrected annual hail climatology;
- SPC validation metrics by size bin, region, season, and source era;
- source-transition diagnostics at MYRORSS/GridRad/MRMS boundaries;
- threshold diagnostics and GPD tail stability;
- analytical return-period maps;
- stochastic catalog event counts and return-period agreement;
- map QA confirming no longitude/latitude orientation or Mexico/Canada displacement artifacts.

### AI-process evidence

The manuscript should include:

- development timeline;
- commit and pull-request counts;
- counts of tests/docs/config changes;
- examples of AI-assisted defects found and fixed;
- table of representative interventions with validation evidence;
- approximate wall-clock time and cost, if available;
- clear human-responsibility statement.

### Reproducibility evidence

Before submission:

- archive the code release with a DOI;
- record exact commit SHA for the manuscript;
- provide environment setup and run commands;
- cite public input data sources;
- state why generated outputs are not tracked in git;
- document where large outputs can be retained or regenerated;
- preserve logs and manifests for the final full run.

---

## Suggested Main Figures

1. Human-AI scientific infrastructure workflow.
2. Data-source timeline and model-stage architecture.
3. Stage 01 source-coverage manifest by year.
4. Corrected annual hail climatology.
5. Validation against SPC reports.
6. Analytical 100-year and 1,000-year return-period maps.
7. Stochastic versus analytical return-period comparison.
8. AI-assisted development evidence table or timeline.

---

## Suggested Reviewer Questions and Answers

**Is this just a hail climatology?**  
No. The manuscript should show daily ingestion, manifest provenance, calibration, sparse event construction, extreme-value fitting, stochastic catalogs, and reproducibility controls.

**Is this just an AI narrative?**  
No. The article must include a real scientific model, final hazard outputs, validation, and uncertainty discussion. The AI process is important because it explains how the scientific infrastructure was built and audited.

**Can AI-generated code be trusted?**  
Only through normal scientific software controls: tests, CI, smoke runs, manifest checks, map QA, code review, and transparent limitations. The manuscript should make that point explicit.

**Why PNAS?**  
The broad significance is not hail alone. It is the demonstration that frontier AI agents can help construct auditable hazard-model infrastructure from public data, which is relevant to climate risk, disaster science, reproducible computation, and the future organization of scientific work.

---

## Go / No-Go Criteria

### Ready for PNAS-style submission when:

- full pipeline completes without unresolved stage failures;
- maps pass visual and numerical sanity checks;
- validation metrics are credible and transparently discussed;
- source-transition artifacts are either controlled or disclosed;
- code release is archived with a DOI;
- AI-use disclosure is exact and complete;
- significance statement is under 120 words and understandable to a broad scientific reader.

### Reposition if:

- final hazard maps have unresolved geographic artifacts;
- SPC validation shows severe unexplained bias;
- source transitions dominate return-period maps;
- stochastic and analytical return-period maps disagree without explanation;
- AI-process evidence cannot be quantified beyond anecdote.

If repositioning is needed, a strong alternative target is a computational-science, environmental-data, or natural-hazards methods journal with the AI-process component presented as a transparent case study rather than the main novelty.

