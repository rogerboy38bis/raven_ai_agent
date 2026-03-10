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
        """RAG: Search relevant memories using vector similarity with citations"""
        # Try vector search first
        memories = []
        try:
            from raven_ai_agent.utils.vector_store import VectorStore
            vector_store = VectorStore()
            memories = vector_store.search_similar(
                user=self.user,
                query=query,
                limit=limit,
                similarity_threshold=self.settings.get("confidence_threshold", 0.7)
            )
        except (ImportError, Exception):
            pass  # Fallback to keyword search

        # Fallback: Simple keyword search
        if not memories:
            memories = frappe.get_list(
                "AI Memory",
                filters={
                    "user": self.user,
                    "content": ["like", f"%{query}%"]
                },
                fields=["name", "content", "importance", "importance_score", "source", "creation"],
                order_by="importance_score desc, creation desc",
                limit=limit
            )

        # Add citations to each memory
        for mem in memories:
            mem["citation"] = self._format_citation(mem)

        return memories

    def _format_citation(self, memory: Dict) -> str:
        """Format memory as a citation"""
        date = ""
        if memory.get("creation"):
            try:
                dt = memory["creation"]
                date = f" ({dt.strftime('%Y-%m-%d') if hasattr(dt, 'strftime') else str(dt)[:10]})"
            except:
                pass

        source = memory.get("source", "Conversation")
        importance = memory.get("importance", "Normal")
        score = memory.get("importance_score", 0.5)

        return f"[{source}{date}, {importance} ({score:.0%})]"

    def tattoo_fact(self, content: str, importance: str = "Normal", source: str = None, auto_analyze: bool = True):
        """
        Memento Protocol: Store important fact with auto-extracted metadata
        If auto_analyze=True (default), uses LLM to extract:
        - Importance score (0-1)
        - Entities (people, places, organizations)
        - Topics/themes
        """
        # Auto-analyze content if enabled
        entities = None
        topics = None
        importance_score = 0.5

        if auto_analyze:
            try:
                analysis = self._analyze_memory_content(content)
                importance_score = analysis.get("importance_score", 0.5)
                entities = analysis.get("entities", "")
                topics = analysis.get("topics", "")
                # Auto-upgrade importance if score is high
                if importance_score >= 0.8:
                    importance = "Critical"
                elif importance_score >= 0.6:
                    importance = "High"
                elif importance_score <= 0.2:
                    importance = "Low"
            except Exception:
                pass  # Fallback to basic storage

        # Try vector-enhanced storage first
        try:
            from raven_ai_agent.utils.vector_store import VectorStore
            vector_store = VectorStore()
            return vector_store.store_memory_with_embedding(
                user=self.user,
                content=content,
                importance=importance,
                source=source,
                importance_score=importance_score,
                entities=entities,
                topics=topics
            )
        except (ImportError, Exception):
            pass  # Fallback to basic storage

        # Fallback: Store without embedding
        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": self.user,
            "content": content,
            "importance": importance,
            "importance_score": importance_score,
            "entities": entities,
            "topics": topics,
            "memory_type": "Fact",
            "source": source or "Conversation"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return doc.name

    def _analyze_memory_content(self, content: str) -> dict:
        """
        Analyze memory content to extract metadata using LLM
        Returns: {importance_score, entities, topics}
        """
        analysis_prompt = f"""Analyze this memory and extract structured information.

Memory: {content}

Respond with JSON only (no other text):
{{
    "importance_score": <float 0-1>,
    "entities": "<comma-separated list of named entities (people, places, organizations)>",
    "topics": "<comma-separated list of topics/themes>",
    "reason": "<1 sentence why this is important>
}}

Importance scoring guide:
- 0.9-1.0: Critical decisions, personal info, errors to avoid
- 0.7-0.89: Important facts, preferences, commitments
- 0.4-0.69: General information, context
- 0.1-0.39: Minor details, casual mentions
"""

        import json
        messages = [
            {"role": "system", "content": "You are a memory analysis system. Extract structured metadata from memory content."},
            {"role": "user", "content": analysis_prompt}
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=300,
            temperature=0.3
        )

        result_text = response.choices[0].message.content

        # Parse JSON response
        try:
            # Try to extract JSON from response
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(result_text[json_start:json_end])
                return {
                    "importance_score": float(result.get("importance_score", 0.5)),
                    "entities": result.get("entities", ""),
                    "topics": result.get("topics", "")
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback
        return {"importance_score": 0.5, "entities": "", "topics": ""}

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
