# Preparing benchmark ground truth

`seed_from_test_queries.py` writes an unfinished draft to `eval/dataset/questions.jsonl`. It contains TODO answers and empty relevance labels and must not be scored. The builder and question evaluator default to `data/questions.jsonl`, which also serves the generated question bank. A useful quiz question is not automatically a labeled retrieval benchmark. Keep a separate reviewed benchmark file; do not overwrite the question bank or manufacture answers to pass validation.

Three structural validation profiles have different purposes:

- `draft` permits unfinished answers and missing chunk labels for curation. Passing it does not make a dataset evaluation-ready.
- `retrieval` requires real question text, unique IDs, and nonempty, unique `supporting_chunk_ids`. Any supplied answer and atomic facts must be non-placeholder text. Pure retrieval fixtures may omit answer fields.
- `answer` requires a nonempty, non-placeholder reference answer. Supporting chunks remain optional because an answer benchmark may use a different scoring protocol.

The canned `TestQuery` fixtures in `eval/runners/test_queries.py` describe retrieval smoke checks and noise/type expectations. They remain usable without reference answers and must not be presented as annotated recall/MRR ground truth.

Curate each benchmark question by reading the original source, writing or correcting its reference answer, and verifying relevant chunk IDs against a frozen corpus. Review atomic facts as factual assertions, not merely topic keywords. Record reviewer identity, review date, corpus revision, inclusion criteria, and split in a dataset manifest. Generated quality scores or `llm_review_decision: keep` are not evidence of human review. Structural validation cannot establish factual accuracy or label completeness.

```bash
# Pure checks: no embedding/model imports, downloads, API calls, or inference.
python -m eval.dataset.build_questions validate --profile retrieval --questions-file path/to/reviewed-retrieval.jsonl
python -m eval.dataset.build_questions validate --profile answer --questions-file path/to/reviewed-answers.jsonl
python -m eval.runners.run_question_eval --questions-file path/to/reviewed-retrieval.jsonl --validate-only
```

Invalid datasets exit nonzero and list row IDs and fields to repair. The evaluator honors `--questions-file`, validates selected questions before importing the retrieval stack, and checks relevance IDs against the loaded corpus before building the searcher. Empty ground truth is an error rather than a zero score; missing labels cannot silently disappear from aggregate metrics. Normal evaluation still loads models and runs retrieval, so reserve it for an explicitly authorized compute run.

Files may include blank lines and full-line `#` or `//` comments. Malformed JSON and non-object rows produce file/line diagnostics. No rows are silently skipped.

Run the dependency-free regression tests with:

```bash
python -m unittest discover -s tests -p test_eval_dataset_validation.py -v
```
