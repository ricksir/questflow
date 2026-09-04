"""Motores de domínio históricos e extensões registradas em runtime.

Não existe mais uma quantidade fixa de motores. Estes imports são mantidos por
compatibilidade com o código anterior à arquitetura modular.
"""

from .registry import EngineRegistry
from .ai_engine import AIEngine, TUTOR_MODES, ERROR_LABELS
from .evaluation_governance import EvaluationGovernanceEngine
from .editorial_bank import EditorialBankEngine
from .learner_model_engine import LearnerModelEngine
from .learning_engine import LearningEngine
from .knowledge_engine import KnowledgeEngine

__all__ = [
    "EngineRegistry", "AIEngine", "TUTOR_MODES", "ERROR_LABELS", "EvaluationGovernanceEngine",
    "EditorialBankEngine", "LearnerModelEngine", "LearningEngine", "KnowledgeEngine",
]
