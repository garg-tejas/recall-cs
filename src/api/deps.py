"""
Build RAG agent and retriever for the API (used in lifespan).
"""

from __future__ import annotations

from src.generation import AnswerGenerator
from src.llm import create_client, create_tutor_client
from src.rag import ChunkRecord, HybridSearcher, load_chunks, RAGConfig
from src.orchestrator import AnswerEvaluator, RAGAgent


def build_agent_and_chunks():
    """
    Load chunks, build HybridSearcher, LLM client, generator, agent.
    Returns (agent, retriever, chunks_by_id, num_chunks).
    """
    chunks: list[ChunkRecord] = load_chunks()
    if not chunks:
        return None, None, {}, 0
    chunks_by_id = {c.id: c for c in chunks}
    config = RAGConfig()
    searcher = HybridSearcher.from_chunks(
        chunks,
        config=config,
        use_reranker=config.use_reranker,
        use_hyde=config.use_hyde,
    )
    client = create_client()
    generator = AnswerGenerator(client)
    evaluator = AnswerEvaluator()
    agent = RAGAgent(
        retriever=searcher,
        generator=generator,
        rag_config=config,
        evaluator=evaluator,
        memory=None,
        max_iterations=2,
    )
    return agent, searcher, chunks_by_id, len(chunks)


def build_tutor_agent(retriever):
    """Build a RAG agent for the tutor using HF Router (MiniMax)."""
    from src.llm.client import HF_ROUTER_API_KEY

    if not HF_ROUTER_API_KEY:
        return None
    client = create_tutor_client()
    generator = AnswerGenerator(client)
    evaluator = AnswerEvaluator()
    return RAGAgent(
        retriever=retriever,
        generator=generator,
        rag_config=RAGConfig(),
        evaluator=evaluator,
        memory=None,
        max_iterations=2,
    )
