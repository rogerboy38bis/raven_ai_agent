# Raven AI Agent - Documentation

This folder contains project documentation, specifications, and architectural plans.

## Documents

### Core Specifications

| Document | Description | Status |
|----------|-------------|--------|
| [00_ORCHESTRATOR_PROJECT_PLAN.md](./00_ORCHESTRATOR_PROJECT_PLAN.md) | Alexa → Raven → ERPNext voice integration (6-phase plan) | ✅ Active |
| [AGENTS.md](./AGENTS.md) | Agent configuration and prompt templates | ✅ Active |
| [FORMULATION_ORCHESTRATOR_SPEC_V4.pdf](./FORMULATION_ORCHESTRATOR_SPEC_V4.pdf) | Aloe powder formulation orchestrator specification | ✅ Active |

### Phase 6 - Deployment & Operations

| Document | Description | Status |
|----------|-------------|--------|
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Deployment procedures for dev/staging/production environments, rollout strategy, rollback procedures | ✅ Active |
| [MONITORING_ALERTING.md](./MONITORING_ALERTING.md) | Monitoring setup, alert thresholds, troubleshooting guide, known issues | ✅ Active |
| [FEEDBACK_IMPROVEMENT.md](./FEEDBACK_IMPROVEMENT.md) | Feedback capture, monthly review process, governance structure, continuous improvement | ✅ Active |

### Phase 7 - Intent Resolver

| Document | Description | Status |
|----------|-------------|--------|
| [INTENT_RESOLVER_SPEC.md](./INTENT_RESOLVER_SPEC.md) | NL→command resolution, confidence thresholds, router integration | ✅ Active |

### Phase 8A - Anti-Hallucination

| Document | Description | Status |
|----------|-------------|--------|
| [ANTI_HALLUCINATION_SPEC.md](./ANTI_HALLUCINATION_SPEC.md) | Response validation, fact-checking against ground truth, confidence scoring | ✅ Active |

### Phase 8B - Multi-Agent Orchestration

| Document | Description | Status |
|----------|-------------|--------|
| [MULTI_AGENT_SPEC.md](./MULTI_AGENT_SPEC.md) | Session context, inter-agent event bus, pipeline execution, workflow commands | ✅ Active |

### Implementation Roadmaps

| Document | Description | Status |
|----------|-------------|--------|
| `IMPLEMENTATION_ROADMAP_Aloe_Optimization.md` | Implementation roadmap for aloe optimization | 📝 Pending |
| `MULTI_AGENT_CONNECTIVITY_ANALYSIS.md` | Multi-agent connectivity analysis | 📝 Pending |

## Project Structure

```
docs/
├── README.md                              # This file
├── 00_ORCHESTRATOR_PROJECT_PLAN.md        # Voice assistant integration plan
├── AGENTS.md                              # Agent configurations
├── FORMULATION_ORCHESTRATOR_SPEC_V4.pdf   # Formulation spec (PDF)
├── IMPLEMENTATION_ROADMAP_Aloe_Optimization.md   # (To be added)
└── MULTI_AGENT_CONNECTIVITY_ANALYSIS.md          # (To be added)
```

## Related Skills Documentation

Each skill has its own `SKILL.md` file:

- `raven_ai_agent/skills/formulation_reader/SKILL.md` - Phase 1: Read-only formulation data
- `raven_ai_agent/skills/formulation_advisor/SKILL.md` - Basic formulation advisor
- `raven_ai_agent/skills/skill_creator/SKILL.md` - Skill creation helper
- `raven_ai_agent/skills/migration_fixer/SKILL.md` - Migration utilities
- `raven_ai_agent/skills/skill_sync/SKILL.md` - Skill synchronization

## Adding New Documents

1. Create or export your document as Markdown (`.md`)
2. Place it in this `docs/` folder
3. Update this README with the document details
4. Commit and push to the repository

```bash
git add docs/
git commit -m "docs: Add [document name]"
git push
```
