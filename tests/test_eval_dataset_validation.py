"""Ground-truth validation tests; standard library only, no retrieval imports."""
import builtins
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from eval.dataset.validation import DatasetValidationError, load_questions, validate_questions
from eval.dataset.build_questions import validate_dataset
from eval.runners.run_question_eval import compute_retrieval_metrics, evaluate_question, main
from eval.runners.test_queries import get_test_queries


def question(**overrides):
    return {"id": "q_reviewed", "query": "What is deadlock?", "answer": "Processes wait indefinitely for resources held by one another.", "supporting_chunk_ids": ["chunk_1"], **overrides}


class DatasetValidationTests(unittest.TestCase):
    def test_placeholder_variants_rejected(self):
        for answer in ["", "   ", "[TODO: Add ground truth answer]", "TODO answer", "TBD", "TBD: author answer", "<placeholder>", "Your answer here", None, 123]:
            with self.subTest(answer=answer), self.assertRaisesRegex(DatasetValidationError, "answer"):
                validate_questions([question(answer=answer)])

    def test_drafts_remain_editable_but_cannot_be_scored(self):
        draft = question(answer="[TODO: Add answer]", supporting_chunk_ids=[])
        validate_questions([draft], profile="draft")
        with self.assertRaises(DatasetValidationError):
            validate_questions([draft], profile="retrieval")

    def test_retrieval_and_answer_profiles_have_distinct_requirements(self):
        retrieval_only = {"id": "retrieval", "query": "Explain scheduling", "supporting_chunk_ids": ["chunk_1"]}
        validate_questions([retrieval_only], profile="retrieval")
        with self.assertRaisesRegex(DatasetValidationError, "answer"):
            validate_questions([retrieval_only], profile="answer")
        answer_only = question()
        del answer_only["supporting_chunk_ids"]
        validate_questions([answer_only], profile="answer")
        with self.assertRaisesRegex(DatasetValidationError, "supporting_chunk_ids"):
            validate_questions([answer_only], profile="retrieval")

    def test_missing_duplicate_or_placeholder_labels_rejected(self):
        for labels in [[], None, "chunk_1", [""], ["TODO"], ["chunk_1", "chunk_1"], [None]]:
            with self.subTest(labels=labels), self.assertRaises(DatasetValidationError):
                validate_questions([question(supporting_chunk_ids=labels)])

    def test_duplicate_ids_unknown_corpus_labels_and_empty_datasets_rejected(self):
        for dataset in [[], [question(), question()]]:
            with self.assertRaises(DatasetValidationError):
                validate_questions(dataset)
        with self.assertRaisesRegex(DatasetValidationError, "absent from this corpus"):
            validate_questions([question()], known_chunk_ids={"other_chunk"})

    def test_atomic_facts_are_not_allowed_to_hide_placeholders(self):
        with self.assertRaisesRegex(DatasetValidationError, "atomic_facts"):
            validate_questions([question(atomic_facts=["[TODO: fact]"])])
        validate_questions([question(atomic_facts=["A TODO marker is a source-code convention."])])

    def test_loader_preserves_comments_and_custom_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reviewed.jsonl"
            path.write_text("\ufeff// header\n# review notes\n\n" + json.dumps(question()) + "\n", encoding="utf-8")
            self.assertEqual(load_questions(path), [question()])
            validate_dataset(profile="retrieval", path=path)

    def test_malformed_rows_report_file_and_line_without_silently_skipping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.jsonl"
            path.write_text('// header\n{"bad":\n[]\n', encoding="utf-8")
            with self.assertRaises(DatasetValidationError) as raised:
                load_questions(path)
            self.assertIn(f"{path}:2", str(raised.exception))
            self.assertIn(f"{path}:3", str(raised.exception))

    def test_metrics_refuse_empty_ground_truth_before_returning_scores(self):
        with self.assertRaises(DatasetValidationError):
            compute_retrieval_metrics(["chunk_1"], [])
        metrics = compute_retrieval_metrics(["chunk_1"], ["chunk_1"], k=3)
        self.assertEqual(metrics["recall@3"], 1)

    def test_direct_question_boundary_rejects_before_search(self):
        searcher = Mock()
        with self.assertRaises(DatasetValidationError):
            evaluate_question(question(answer="[TODO: answer]"), searcher)
        searcher.search_raw.assert_not_called()

    def test_metadata_only_smoke_fixtures_keep_their_own_schema(self):
        fixtures = get_test_queries()
        self.assertTrue(fixtures)
        self.assertFalse(hasattr(fixtures[0], "answer"))

    def test_cli_custom_file_and_invalid_data_never_import_retrieval(self):
        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if name.startswith("src.rag"):
                raise AssertionError("Retrieval imports forbidden during validation")
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.jsonl"
            path.write_text(json.dumps(question()), encoding="utf-8")
            with patch("builtins.__import__", side_effect=guard), contextlib.redirect_stdout(io.StringIO()):
                main(["--questions-file", str(path), "--validate-only"])
            path.write_text(json.dumps(question(answer="TODO: missing")), encoding="utf-8")
            with patch("builtins.__import__", side_effect=guard), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(["--questions-file", str(path)])
            self.assertEqual(raised.exception.code, 2)

    def test_cli_filtered_empty_subset_is_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cn.jsonl"
            path.write_text(json.dumps(question(subject="cn")), encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(["--questions-file", str(path), "--subject", "os", "--validate-only"])
            self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
