"""
Enhanced Search - Phase 5
Semantic similarity scoring, confidence thresholds, relevance ranking

Phase 5 of Memory Enhancement Project
"""
import frappe
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class EnhancedSearch:
    """
    Enhanced memory search with scoring and ranking
    
    Features:
    - Semantic similarity scoring
    - Confidence thresholds
    - Relevance ranking
    - Time-based boosting
    - Entity matching boost
    """
    
    def __init__(self, user: str = None):
        self.user = user
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize LLM client"""
        try:
            from openai import OpenAI
            settings = frappe.get_doc("AI Agent Settings")
            api_key = settings.get_password("api_key")
            base_url = settings.get("base_url") or "https://api.openai.com/v1"
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        except Exception:
            pass
    
    def search_with_scoring(self, query: str, limit: int = 10, 
                           min_confidence: float = 0.3) -> List[Dict]:
        """
        Search memories with relevance scoring
        
        Args:
            query: Search query
            limit: Max results
            min_confidence: Minimum confidence score (0-1)
        
        Returns:
            List of memories with scores and rankings
        """
        # Get base memories
        memories = frappe.get_list(
            "AI Memory",
            filters={"user": self.user},
            fields=["name", "content", "importance", "importance_score",
                   "entities", "topics", "source", "creation", "memory_type"],
            order_by="creation desc",
            limit=limit * 3  # Get more for re-ranking
        )
        
        if not memories:
            return []
        
        # Score each memory
        scored_memories = []
        for mem in memories:
            score = self._calculate_relevance_score(query, mem)
            if score >= min_confidence:
                mem["relevance_score"] = score
                mem["citation"] = self._format_citation(mem)
                scored_memories.append(mem)
        
        # Sort by score
        scored_memories.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        # Apply time decay boost
        scored_memories = self._apply_time_boost(scored_memories)
        
        # Return top results
        return scored_memories[:limit]
    
    def _calculate_relevance_score(self, query: str, memory: Dict) -> float:
        """
        Calculate relevance score for a memory
        
        Score factors:
        - Keyword matching (0-0.3)
        - Entity matching (0-0.3)
        - Topic matching (0-0.2)
        - Importance score (0-0.2)
        """
        score = 0.0
        query_lower = query.lower()
        
        # 1. Keyword matching (0-0.3)
        content_lower = memory.get("content", "").lower()
        query_words = set(query_lower.split())
        content_words = set(content_lower.split())
        
        # Exact phrase match
        if query_lower in content_lower:
            score += 0.3
        # Word overlap
        elif query_words & content_words:
            overlap = len(query_words & content_words) / len(query_words)
            score += overlap * 0.2
        
        # 2. Entity matching (0-0.3)
        entities = memory.get("entities", "")
        if entities:
            entities_lower = entities.lower()
            for word in query_words:
                if word in entities_lower:
                    score += 0.1
            # Full entity phrase
            if query_lower in entities_lower:
                score += 0.2
        
        # 3. Topic matching (0-0.2)
        topics = memory.get("topics", "")
        if topics:
            topics_lower = topics.lower()
            for word in query_words:
                if word in topics_lower:
                    score += 0.05
            if query_lower in topics_lower:
                score += 0.15
        
        # 4. Importance boost (0-0.2)
        importance_score = memory.get("importance_score", 0.5)
        importance_map = {"Critical": 0.2, "High": 0.15, "Normal": 0.1, "Low": 0.05}
        importance = memory.get("importance", "Normal")
        score += importance_map.get(importance, 0.1) * importance_score
        
        # Cap at 1.0
        return min(score, 1.0)
    
    def _apply_time_boost(self, memories: List[Dict], decay_days: int = 30) -> List[Dict]:
        """
        Apply time-based boost - recent memories get higher scores
        
        Memories from last 'decay_days' get a boost that decreases over time
        """
        now = frappe.utils.now()
        
        for mem in memories:
            creation = mem.get("creation")
            if not creation:
                continue
            
            try:
                # Parse date
                if isinstance(creation, str):
                    creation_dt = frappe.utils.datetime_from_str(creation)
                else:
                    creation_dt = creation
                
                days_ago = (frappe.utils.now_datetime() - creation_dt).days
                
                if days_ago < decay_days:
                    # Linear decay: 10% boost for today, 0% after decay_days
                    boost = 0.1 * (1 - days_ago / decay_days)
                    mem["relevance_score"] = mem.get("relevance_score", 0) + boost
                    
            except Exception:
                pass
        
        # Re-sort after boosting
        memories.sort(key=lambda x: x["relevance_score"], reverse=True)
        return memories
    
    def _format_citation(self, memory: Dict) -> str:
        """Format memory as a citation with score"""
        date = ""
        if memory.get("creation"):
            try:
                dt = memory["creation"]
                if isinstance(dt, str):
                    date = f" ({dt[:10]})"
                else:
                    date = f" ({dt.strftime('%Y-%m-%d')})"
            except:
                pass
        
        source = memory.get("source", "Conversation")
        importance = memory.get("importance", "Normal")
        score = memory.get("relevance_score", memory.get("importance_score", 0.5))
        
        return f"[{source}{date}, {importance} ({score:.0%})]"
    
    def semantic_search(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Semantic search using embeddings (if available)
        
        Falls back to keyword search if no vector store
        """
        # Try vector search first
        try:
            from raven_ai_agent.utils.vector_store import VectorStore
            vector_store = VectorStore()
            
            results = vector_store.search_similar(
                user=self.user,
                query=query,
                limit=limit,
                similarity_threshold=0.3
            )
            
            # Add citations
            for r in results:
                r["citation"] = self._format_citation(r)
                r["relevance_score"] = r.get("similarity_score", 0)
            
            return results
            
        except (ImportError, Exception):
            # Fallback to scoring-based search
            return self.search_with_scoring(query, limit)
    
    def get_search_suggestions(self, partial_query: str) -> List[str]:
        """
        Get search suggestions based on partial query
        
        Returns list of suggested queries
        """
        # Get recent topics and entities for suggestions
        memories = frappe.get_list(
            "AI Memory",
            filters={"user": self.user},
            fields=["topics", "entities"],
            limit=20
        )
        
        suggestions = set()
        
        for mem in memories:
            # Add topics as suggestions
            topics = mem.get("topics", "")
            if topics:
                for topic in topics.split(","):
                    topic = topic.strip()
                    if topic and partial_query.lower() in topic.lower():
                        suggestions.add(topic)
            
            # Add entities as suggestions
            entities = mem.get("entities", "")
            if entities:
                for entity in entities.split(","):
                    entity = entity.strip()
                    if entity and partial_query.lower() in entity.lower():
                        suggestions.add(entity)
        
        return list(suggestions)[:10]
    
    def search_by_entity(self, entity: str, limit: int = 10) -> List[Dict]:
        """
        Search memories by specific entity
        """
        memories = frappe.get_list(
            "AI Memory",
            filters={
                "user": self.user,
                "entities": ["like", f"%{entity}%"]
            },
            fields=["name", "content", "importance", "importance_score",
                   "entities", "topics", "source", "creation"],
            order_by="importance_score desc, creation desc",
            limit=limit
        )
        
        for mem in memories:
            mem["citation"] = self._format_citation(mem)
            mem["relevance_score"] = mem.get("importance_score", 0.5)
        
        return memories
    
    def search_by_topic(self, topic: str, limit: int = 10) -> List[Dict]:
        """
        Search memories by topic
        """
        memories = frappe.get_list(
            "AI Memory",
            filters={
                "user": self.user,
                "topics": ["like", f"%{topic}%"]
            },
            fields=["name", "content", "importance", "importance_score",
                   "entities", "topics", "source", "creation"],
            order_by="importance_score desc, creation desc",
            limit=limit
        )
        
        for mem in memories:
            mem["citation"] = self._format_citation(mem)
            mem["relevance_score"] = mem.get("importance_score", 0.5)
        
        return memories


@frappe.whitelist()
def enhanced_search(user: str, query: str, limit: int = 10, 
                   min_confidence: float = 0.3) -> List[Dict]:
    """
    API endpoint for enhanced search
    """
    search = EnhancedSearch(user=user)
    return search.search_with_scoring(query, limit, min_confidence)


@frappe.whitelist()
def semantic_search_api(user: str, query: str, limit: int = 5) -> List[Dict]:
    """
    API endpoint for semantic search
    """
    search = EnhancedSearch(user=user)
    return search.semantic_search(query, limit)
