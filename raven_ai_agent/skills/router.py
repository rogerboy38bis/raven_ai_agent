"""
Skill Router for Raven AI Agent
================================
Routes incoming messages to appropriate skills based on triggers and patterns.
"""

import re
import frappe
from typing import Dict, List, Optional, Any


class SkillRouter:
    """
    Routes incoming queries to the appropriate skill handler.
    
    Skills register themselves with triggers (keywords) and patterns (regex).
    The router matches incoming queries and delegates to the best matching skill.
    """
    
    def __init__(self):
        self.skills: Dict[str, Any] = {}
        self._load_skills()
    
    def _load_skills(self):
        """Auto-discover and load available skills."""
        # Load Formulation Orchestrator
        try:
            from raven_ai_agent.skills.formulation_orchestrator.skill import FormulationOrchestratorSkill
            skill = FormulationOrchestratorSkill()
            self.skills[skill.name] = skill
        except Exception as e:
            print(f"Warning: Could not load FormulationOrchestratorSkill: {e}")
        
        # Load Data Quality Scanner (high priority - runs before operations)
        try:
            from raven_ai_agent.skills.data_quality_scanner.skill import DataQualityScannerSkill
            skill = DataQualityScannerSkill()
            self.skills[skill.name] = skill
        except Exception as e:
            print(f"Warning: Could not load DataQualityScannerSkill: {e}")

        # Load IoT Sensor Manager (handles temperature/humidity/motion/light + L01-L30 bots)
        try:
            from raven_ai_agent.skills.iot_sensor_manager.skill import IoTSensorManagerSkill
            skill = IoTSensorManagerSkill()
            self.skills[skill.name] = skill
        except Exception as e:
            print(f"Warning: Could not load IoTSensorManagerSkill: {e}")
    
    def register_skill(self, skill):
        """Manually register a skill."""
        self.skills[skill.name] = skill
    
    def get_skill(self, name: str):
        """Get a skill by name."""
        return self.skills.get(name)
    
    def list_skills(self) -> List[Dict]:
        """List all registered skills."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "priority": getattr(s, 'priority', 50)
            }
            for s in self.skills.values()
        ]
    
    def route(self, query: str, context: Dict = None) -> Optional[Dict]:
        """
        Route a query to the best matching skill.
        
        Args:
            query: User's input query
            context: Session context
            
        Returns:
            Response dict from the handling skill, or None if no match
        """
        context = context or {}
        query_lower = query.lower()
        
        # Find matching skills
        matches = []
        
        for skill in self.skills.values():
            score = 0
            
            # Check triggers
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    score += 10
            
            # Check patterns
            if hasattr(skill, 'patterns'):
                for pattern in skill.patterns:
                    if re.search(pattern, query, re.IGNORECASE):
                        score += 20
            
            if score > 0:
                matches.append((skill, score))
        
        if not matches:
            return None
        
        # Sort by score (and priority as tiebreaker)
        matches.sort(key=lambda x: (x[1], getattr(x[0], 'priority', 50)), reverse=True)
        
        # Execute best match
        best_skill = matches[0][0]
        frappe.logger().info(f"[SkillRouter] Calling skill: {best_skill.name}")
        try:
            result = best_skill.handle(query, context)
            frappe.logger().info(f"[SkillRouter] Skill result: {result}")
            return result
        except Exception as e:
            frappe.logger().error(f"[SkillRouter] Error in skill {best_skill.name}: {e}")
            return None
    
    def can_handle(self, query: str) -> bool:
        """Check if any skill can handle this query."""
        query_lower = query.lower()
        
        for skill in self.skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in query_lower:
                    return True
            
            if hasattr(skill, 'patterns'):
                for pattern in skill.patterns:
                    if re.search(pattern, query, re.IGNORECASE):
                        return True
        
        return False
