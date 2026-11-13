"""
Helper script to generate initial seed questions from test_queries.py.

This creates a starting point for questions.jsonl. You should manually review
and add ground truth answers, then use build_questions.py to link chunks.
"""

from __future__ import annotations

import json
from pathlib import Path

from eval.runners.test_queries import TEST_QUERIES

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS_PATH = ROOT / "eval" / "dataset" / "questions.jsonl"


# Mapping from test queries to initial seed questions
# These are placeholders - you'll need to add actual ground truth answers
SEED_QUESTIONS = [
    {
        "id": "q_001",
        "subject": "os",
        "query": "tell me about page replacement algos",
        "question_type": "procedural",
        "answer": "[TODO: Add ground truth answer about page replacement algorithms]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["page replacement algorithms", "optimal algorithm", "FIFO", "LRU"],
        "difficulty": "medium",
    },
    {
        "id": "q_002",
        "subject": "cn",
        "query": "what is tcp 3 way handshake",
        "question_type": "definition",
        "answer": "[TODO: Add ground truth answer about TCP 3-way handshake]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["TCP", "three-way handshake", "SYN", "ACK", "connection establishment"],
        "difficulty": "medium",
    },
    {
        "id": "q_003",
        "subject": "dbms",
        "query": "how to do b+ tree insertion and deletion",
        "question_type": "procedural",
        "answer": "[TODO: Add ground truth answer about B+ tree insertion/deletion steps]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["B+ tree", "insertion", "deletion", "node split", "node merge"],
        "difficulty": "hard",
    },
    {
        "id": "q_004",
        "subject": "os",
        "query": "what is deadlock",
        "question_type": "definition",
        "answer": "[TODO: Add ground truth answer about deadlock]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["deadlock", "circular wait", "resource allocation", "process blocking"],
        "difficulty": "easy",
    },
    {
        "id": "q_005",
        "subject": "cn",
        "query": "compare tcp and udp",
        "question_type": "comparative",
        "answer": "[TODO: Add ground truth answer comparing TCP and UDP]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["TCP is connection-oriented", "UDP is connectionless", "TCP is reliable", "UDP is unreliable"],
        "difficulty": "medium",
    },
    {
        "id": "q_006",
        "subject": "os",
        "query": "explain process scheduling algorithms",
        "question_type": "procedural",
        "answer": "[TODO: Add ground truth answer about process scheduling algorithms]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["CPU scheduling", "round robin", "FCFS", "priority scheduling"],
        "difficulty": "medium",
    },
    {
        "id": "q_007",
        "subject": "dbms",
        "query": "what are acid properties in databases",
        "question_type": "definition",
        "answer": "[TODO: Add ground truth answer about ACID properties]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["Atomicity", "Consistency", "Isolation", "Durability"],
        "difficulty": "medium",
    },
    {
        "id": "q_008",
        "subject": "os",
        "query": "how does virtual memory work",
        "question_type": "procedural",
        "answer": "[TODO: Add ground truth answer about virtual memory]",
        "supporting_chunk_ids": [],
        "atomic_facts": ["virtual memory", "paging", "page table", "address translation"],
        "difficulty": "medium",
    },
]


def main() -> None:
    """Generate seed questions file."""
    QUESTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with QUESTIONS_PATH.open("w", encoding="utf-8") as f:
        f.write("// Questions dataset for Phase 1 reasoning model evaluation\n")
        f.write("// Each line is a JSON object with the following schema:\n")
        f.write("// {\n")
        f.write("//   \"id\": \"q_001\",\n")
        f.write("//   \"subject\": \"os|dbms|cn\",\n")
        f.write("//   \"query\": \"what is deadlock\",\n")
        f.write("//   \"question_type\": \"definition|procedural|comparative|factual\",\n")
        f.write("//   \"answer\": \"Deadlock occurs when...\",\n")
        f.write("//   \"supporting_chunk_ids\": [\"chunk_00294\", \"chunk_00431\"],\n")
        f.write("//   \"atomic_facts\": [\"deadlock involves processes\", \"circular wait condition\"],\n")
        f.write("//   \"difficulty\": \"easy|medium|hard\"\n")
        f.write("// }\n\n")
        
        for q in SEED_QUESTIONS:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
    
    print(f"Generated {len(SEED_QUESTIONS)} seed questions in {QUESTIONS_PATH}")
    print("\nNext steps:")
    print("1. Review questions.jsonl and add ground truth answers (replace [TODO] placeholders)")
    print("2. Manually verify and annotate supporting_chunk_ids against a fixed corpus")
    print("3. Keep reviewed benchmark entries in a separate file; the link tool edits data/questions.jsonl by default")
    print("4. Draft output is NOT an evaluation-ready benchmark. Validate it explicitly:")
    print(f"   python -m eval.dataset.build_questions validate --profile retrieval --questions-file {QUESTIONS_PATH}")
    print("   The seed draft and data/questions.jsonl are separate files; merge reviewed entries deliberately, preserving existing data.")


if __name__ == "__main__":
    main()
