"""
Consolidation Agent - Google Always-On Memory Inspired
Run periodically to find connections between memories and generate insights

Phase 2 of Memory Enhancement Project
"""
import frappe
import json
from typing import Dict, List
from datetime import datetime, timedelta


class ConsolidationAgent:
    """
    Consolidation Agent - Reviews memories, finds connections, generates insights
    
    Runs on timer (default: every 30 minutes)
    - Reviews unconsolidated memories
    - Finds connections between memories
    - Generates cross-cutting insights
    - Compresses redundant information
    """

    def __init__(self, user: str = None, model: str = None):
        self.user = user
        self.model = model or "gpt-4o"
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
        except Exception as e:
            frappe.logger().error(f"ConsolidationAgent: Failed to init client: {e}")

    def run_consolidation(self, user: str = None, limit: int = 50):
        """
        Main consolidation job - call this on timer
        
        Args:
            user: Specific user to consolidate (None = all users)
            limit: Max memories to process per run
        """
        self.user = user

        # Get unconsolidated memories
        filters = {"consolidated": 0}
        if user:
            filters["user"] = user

        memories = frappe.get_list(
            "AI Memory",
            filters=filters,
            fields=["name", "user", "content", "importance", "importance_score", 
                    "entities", "topics", "memory_type", "source", "creation"],
            order_by="importance_score desc, creation desc",
            limit=limit
        )

        if not memories:
            return {"status": "no_memories", "processed": 0}

        # Group by user
        by_user = {}
        for mem in memories:
            u = mem.get("user")
            if u not in by_user:
                by_user[u] = []
            by_user[u].append(mem)

        total_insights = 0

        # Process each user
        for user_id, user_memories in by_user.items():
            self.user = user_id
            try:
                insights = self._consolidate_user_memories(user_memories)
                total_insights += insights
            except Exception as e:
                frappe.logger().error(f"ConsolidationAgent: Error for {user_id}: {e}")

        return {
            "status": "completed",
            "users_processed": len(by_user),
            "memories_processed": len(memories),
            "insights_generated": total_insights
        }

    def _consolidate_user_memories(self, memories: List[Dict]) -> int:
        """Consolidate memories for a single user"""
        
        # Step 1: Find connections
        connections = self._find_connections(memories)

        # Step 2: Generate insights
        insights = self._generate_insights(memories, connections)

        # Step 3: Mark memories as consolidated
        for mem in memories:
            try:
                doc = frappe.get_doc("AI Memory", mem["name"])
                doc.consolidated = 1
                doc.consolidation_refs = json.dumps(connections.get(mem["name"], []))
                doc.save(ignore_permissions=True)
            except Exception:
                pass

        frappe.db.commit()
        return len(insights)

    def _find_connections(self, memories: List[Dict]) -> Dict[str, List[str]]:
        """
        Find connections between memories based on:
        - Shared entities
        - Shared topics
        - Temporal proximity
        - Semantic similarity
        """
        connections = {mem["name"]: [] for mem in memories}

        # Build entity/topic index
        entity_index = {}
        topic_index = {}

        for mem in memories:
            # Index entities
            if mem.get("entities"):
                for entity in mem["entities"].split(","):
                    entity = entity.strip().lower()
                    if entity:
                        if entity not in entity_index:
                            entity_index[entity] = []
                        entity_index[entity].append(mem["name"])

            # Index topics
            if mem.get("topics"):
                for topic in mem["topics"].split(","):
                    topic = topic.strip().lower()
                    if topic:
                        if topic not in topic_index:
                            topic_index[topic] = []
                        topic_index[topic].append(mem["name"])

        # Build connections
        for mem in memories:
            name = mem["name"]

            # Check entity matches
            if mem.get("entities"):
                for entity in mem["entities"].split(","):
                    entity = entity.strip().lower()
                    if entity and entity in entity_index:
                        for linked in entity_index[entity]:
                            if linked != name and linked not in connections[name]:
                                connections[name].append(linked)

            # Check topic matches
            if mem.get("topics"):
                for topic in mem["topics"].split(","):
                    topic = topic.strip().lower()
                    if topic and topic in topic_index:
                        for linked in topic_index[topic]:
                            if linked != name and linked not in connections[name]:
                                connections[name].append(linked)

        return connections

    def _generate_insights(self, memories: List[Dict], connections: Dict[str, List[str]]) -> List[str]:
        """Use LLM to generate cross-cutting insights from connected memories"""
        if not self.client or len(memories) < 3:
            return []

        # Prepare memory summary for LLM
        memory_summaries = []
        for mem in memories[:20]:  # Limit for token budget
            summary = f"- [{mem.get('importance_score', 0.5):.1f}] {mem.get('content', '')[:200]}"
            if mem.get("entities"):
                summary += f" (entities: {mem.get('entities')})"
            memory_summaries.append(summary)

        prompt = f"""You are a memory consolidation system. Analyze these memories and find patterns, insights, and connections.

Memories:
{chr(10).join(memory_summaries)}

Respond with JSON only:
{{
    "insights": [
        {{
            "title": "<insight title>",
            "description": "<2-3 sentences explaining the insight>",
            "related_memories": [<indices of related memories>],
            "confidence": <float 0-1>
        }}
    ],
    "patterns": ["<pattern 1>", "<pattern 2>"],
    "recommendations": ["<actionable recommendation if any>"]
}}

Focus on:
1. Recurring themes or topics
2. Cause-effect relationships
3. User preferences or habits
4. Important decisions and their context
"""

        try:
            messages = [
                {"role": "system", "content": "You are a memory analysis assistant."},
                {"role": "user", "content": prompt}
            ]

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1000,
                temperature=0.3
            )

            result_text = response.choices[0].message.content

            # Parse JSON
            try:
                json_start = result_text.find('{')
                json_end = result_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(result_text[json_start:json_end])

                    # Store insights as consolidated memories
                    for insight in result.get("insights", []):
                        self._store_insight(insight)

                    return result.get("insights", [])

            except (json.JSONDecodeError, ValueError):
                pass

        except Exception as e:
            frappe.logger().error(f"ConsolidationAgent: LLM error: {e}")

        return []

    def _store_insight(self, insight: dict):
        """Store generated insight as a memory"""
        content = f"💡 INSIGHT: {insight.get('title', 'Generated Insight')}\n\n{insight.get('description', '')}"

        doc = frappe.get_doc({
            "doctype": "AI Memory",
            "user": self.user,
            "content": content,
            "importance": "High" if insight.get("confidence", 0) > 0.7 else "Normal",
            "importance_score": insight.get("confidence", 0.5),
            "memory_type": "Summary",
            "source": "Consolidation Agent",
            "consolidated": 1
        })
        doc.insert(ignore_permissions=True)


def run_consolidation_job():
    """Entry point for scheduled job"""
    agent = ConsolidationAgent()
    return agent.run_consolidation()


# For manual trigger via API
@frappe.whitelist()
def consolidate_all_users():
    """API endpoint to trigger consolidation for all users"""
    return run_consolidation_job()
