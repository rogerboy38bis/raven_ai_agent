"""
Memory Manager - Raymond-Lucy Protocol Memory Operations
Split from agent.py - Phase 2 Optimization

Contains: MemoryMixin with morning briefing, memory search, fact storage
"""
import frappe
from typing import Dict, List


class MemoryMixin:
    """
    Mixin that adds memory management to the agent.
    Requires: self.user, self.settings
    Optional: VECTOR_SEARCH_ENABLED, VectorStore (imported at module level)
    """

    def get_morning_briefing(self) -> str:
        """Lucy Protocol: Load context at session start"""
        # Get user's critical memories
        memories = frappe.get_list(
            "AI Memory",
            filters={"user": self.user, "importance": ["in", ["Critical", "High"]]},
            fields=["content", "importance", "source"],
            order_by="creation desc",
            limit=10
        )

        # Get latest summary
        summaries = frappe.get_list(
            "AI Memory",
            filters={"user": self.user, "memory_type": "Summary"},
            fields=["content"],
            order_by="creation desc",
            limit=1
        )

        briefing = "## Morning Briefing\n\n"

        if summaries:
            briefing += f"**Last Session Summary:**\n{summaries[0].content}\n\n"

        if memories:
            briefing += "**Key Facts:**\n"
            for m in memories:
                briefing += f"- [{m.importance}] {m.content}\n"

        return briefing

    def search_memories(self, query: str, limit: int = 5) -> List[Dict]:
        """RAG: Search relevant memories using vector similarity"""
        # Try vector search first
        try:
            from raven_ai_agent.utils.vector_store import VectorStore
            vector_store = VectorStore()
            return vector_store.search_similar(
                user=self.user,
                query=query,
                limit=limit,
                similarity_threshold=self.settings.get("confidence_threshold", 0.7)
            )
        except (ImportError, Exception):
            pass  # Fallback to keyword search

        # Fallback: Simple keyword search
        memories = frappe.get_list(
            "AI Memory",
            filters={
                "user": self.user,
                "content": ["like", f"%{query}%"]
            },
            fields=["content", "importance", "source", "creation"],
            order_by="creation desc",
            limit=limit
        )
        return memories

    def tattoo_fact(self, content: str, importance: str = "Normal", source: str = None):
        """Memento Protocol: Store important fact with embedding"""
        # Try vector-enhanced storage first
        try:
            from raven_ai_agent.utils.vector_store import VectorStore
            vector_store = VectorStore()
            return vector_store.store_memory_with_embedding(
                user=self.user,
                content=content,
                importance=importance,
                source=source
            )
        except (ImportError, Exception):
            pass  # Fallback to basic storage

        # Fallback: Store without embedding
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": self.user,
            "content": content,
            "importance": importance,
            "memory_type": "Fact",
            "source": source or "Conversation"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def end_session(self, conversation: List[Dict]):
        """Lucy Protocol: Generate session summary"""
        if not conversation:
            return

        summary_prompt = "Summarize this conversation in 2-3 sentences, focusing on key decisions and information shared."

        import json
        messages = [
            {"role": "system", "content": summary_prompt},
            {"role": "user", "content": json.dumps(conversation[-20:], default=str)}
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=200
            )

            summary = response.choices[0].message.content

            # Store summary
            doc = frappe.get_doc({
                "doctype": "AI Memory",
                "user": self.user,
                "content": summary,
                "importance": "High",
                "memory_type": "Summary",
                "source": "Session End"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()

        except Exception:
            pass
