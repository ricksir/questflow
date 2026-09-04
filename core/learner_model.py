from __future__ import annotations

"""Modelo de aprendizagem QuestFlow 6.0.

Combina três sinais complementares:
- FSRS (existente no repositório): quando revisar / retenção.
- Knowledge Tracing Bayesiano (BKT): probabilidade de domínio por conceito.
- IRT online conservadora: habilidade por matéria e parâmetros pessoais do item.

A camada IRT é deliberadamente regularizada porque o QuestFlow é um sistema
pessoal e não dispõe, por padrão, de uma população de milhares de candidatos.
Ela nunca se apresenta como calibração psicométrica populacional.
"""

import math
from dataclasses import dataclass

MODEL_VERSION = "qf-learner-2"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def sigmoid(value: float) -> float:
    value = clamp(value, -35.0, 35.0)
    return 1.0 / (1.0 + math.exp(-value))


def logit(probability: float) -> float:
    p = clamp(probability, 1e-5, 1.0 - 1e-5)
    return math.log(p / (1.0 - p))


@dataclass(frozen=True, slots=True)
class KnowledgeUpdate:
    prior: float
    posterior_observation: float
    mastery: float
    slip: float
    guess: float
    learn: float


def update_bkt(
    prior: float,
    correct: bool,
    *,
    slip: float = 0.10,
    guess: float = 0.20,
    learn: float = 0.14,
) -> KnowledgeUpdate:
    """Uma atualização BKT estável e interpretável.

    ``prior`` representa P(domínio antes da resposta). A resposta primeiro
    atualiza a crença via Bayes e depois aplica a transição de aprendizagem.
    """
    p = clamp(prior, 0.02, 0.98)
    slip = clamp(slip, 0.02, 0.35)
    guess = clamp(guess, 0.02, 0.45)
    learn = clamp(learn, 0.01, 0.45)
    if correct:
        numerator = p * (1.0 - slip)
        denominator = numerator + (1.0 - p) * guess
    else:
        numerator = p * slip
        denominator = numerator + (1.0 - p) * (1.0 - guess)
    posterior = numerator / denominator if denominator > 1e-12 else p
    mastery = posterior + (1.0 - posterior) * learn
    return KnowledgeUpdate(p, clamp(posterior, 0.0, 1.0), clamp(mastery, 0.02, 0.995), slip, guess, learn)


def mastery_confidence(exposures: int) -> float:
    """Confiança cresce suavemente com a quantidade de evidências."""
    n = max(0, int(exposures))
    return clamp(1.0 - math.exp(-n / 7.0), 0.0, 0.98)


def mastery_label(mastery: float, confidence: float = 1.0) -> str:
    if confidence < 0.22:
        return "Pouca evidência"
    value = clamp(mastery, 0.0, 1.0)
    if value >= 0.85:
        return "Domínio forte"
    if value >= 0.70:
        return "Domínio bom"
    if value >= 0.50:
        return "Em consolidação"
    return "Lacuna provável"


@dataclass(frozen=True, slots=True)
class IrtUpdate:
    theta: float
    difficulty: float
    discrimination: float
    probability: float
    information: float
    standard_error: float


def update_irt_online(
    theta: float,
    difficulty: float,
    discrimination: float,
    correct: bool,
    *,
    ability_attempts: int = 0,
    item_attempts: int = 0,
) -> IrtUpdate:
    """Atualização 2PL online fortemente regularizada para uso pessoal.

    O parâmetro ``a`` (discriminação) só se move depois de várias exposições e
    com passo pequeno. Isso evita que uma única pessoa produza falsa precisão.
    """
    theta = clamp(theta, -4.0, 4.0)
    b = clamp(difficulty, -3.5, 3.5)
    a = clamp(discrimination, 0.55, 2.20)
    p = sigmoid(a * (theta - b))
    y = 1.0 if correct else 0.0
    residual = y - p

    # Decaimento de passo: aprende rápido no início, estabiliza com histórico.
    lr_theta = 0.34 / math.sqrt(1.0 + max(0, ability_attempts) / 8.0)
    lr_b = 0.11 / math.sqrt(1.0 + max(0, item_attempts) / 4.0)
    theta_new = clamp(theta + lr_theta * a * residual, -4.0, 4.0)
    b_new = clamp(b - lr_b * a * residual, -3.5, 3.5)

    a_new = a
    if item_attempts >= 5:
        lr_a = 0.012 / math.sqrt(1.0 + item_attempts / 10.0)
        a_new = clamp(a + lr_a * residual * (theta - b), 0.55, 2.20)

    p_new = sigmoid(a_new * (theta_new - b_new))
    information = max(1e-6, (a_new * a_new) * p_new * (1.0 - p_new))
    # SE aqui é indicador local de incerteza, não erro-padrão populacional.
    accumulated_information = max(0.08, information * max(1.0, min(ability_attempts + 1, 30)))
    standard_error = clamp(1.0 / math.sqrt(accumulated_information), 0.12, 3.5)
    return IrtUpdate(theta_new, b_new, a_new, p_new, information, standard_error)


def theta_percentile(theta: float) -> float:
    """Escala visual 0–100; não representa percentil populacional real."""
    return clamp(sigmoid(float(theta) / 1.35) * 100.0, 0.0, 100.0)


def item_difficulty_label(difficulty: float) -> str:
    b = float(difficulty)
    if b <= -1.0:
        return "Fácil"
    if b >= 1.0:
        return "Difícil"
    return "Média"


def fusion_priority(
    *,
    mastery: float | None,
    mastery_confidence_value: float,
    retrievability: float | None,
    irt_information: float | None,
    overdue: bool,
    editorial_priority: float = 0.0,
) -> float:
    """Prioridade explicável 0–100 para seleção futura.

    Não substitui o scheduler FSRS; serve como camada de ordenação/diagnóstico.
    """
    score = 0.0
    if mastery is not None:
        score += (1.0 - clamp(mastery, 0.0, 1.0)) * (35.0 + 10.0 * clamp(mastery_confidence_value, 0.0, 1.0))
    else:
        score += 18.0
    if retrievability is not None:
        score += (1.0 - clamp(retrievability, 0.0, 1.0)) * 28.0
    if irt_information is not None:
        # valor máximo útil perto da habilidade atual
        score += min(14.0, 10.0 * max(0.0, float(irt_information)))
    if overdue:
        score += 14.0
    score += clamp(editorial_priority, 0.0, 100.0) * 0.09
    return round(clamp(score, 0.0, 100.0), 2)


@dataclass(frozen=True, slots=True)
class SelectivePrediction:
    probability: float
    confidence: float
    interval_low: float
    interval_high: float
    status: str
    abstain: bool
    reasons: tuple[str, ...]
    components: dict[str, float]
    version: str = MODEL_VERSION


def evidence_status(*, confidence: float, exposures: int, standard_error: float | None = None) -> dict:
    """Classifica a suficiência da evidência sem inventar precisão.

    ``abstain`` significa que o QuestFlow deve priorizar coleta diagnóstica em
    vez de rotular o conceito como dominado/fraco com falsa segurança.
    """
    conf = clamp(confidence, 0.0, 1.0)
    n = max(0, int(exposures))
    se = None if standard_error is None else max(0.0, float(standard_error))
    se_penalty = 0.0 if se is None else clamp((se - 0.75) / 2.25, 0.0, 1.0)
    effective = clamp(conf * (1.0 - 0.35 * se_penalty), 0.0, 1.0)
    reasons: list[str] = []
    if n < 3:
        reasons.append(f"apenas {n} evidência(s)")
    if conf < 0.35:
        reasons.append("confiança do Knowledge Tracing baixa")
    if se is not None and se > 1.45:
        reasons.append("incerteza IRT elevada")
    abstain = n < 3 or effective < 0.34
    if abstain:
        status = "evidencia_insuficiente"
        label = "Evidência insuficiente"
    elif effective < 0.60:
        status = "estimativa_cautelosa"
        label = "Estimativa cautelosa"
    else:
        status = "estimativa_confiavel"
        label = "Estimativa confiável"
    return {
        "status": status,
        "label": label,
        "abstain": abstain,
        "effective_confidence": round(effective, 4),
        "reasons": reasons or ["amostra e incerteza compatíveis com estimativa"],
    }


def predict_success_selective(
    *,
    mastery: float | None,
    mastery_confidence_value: float,
    retrievability: float | None,
    fsrs_reviews: int,
    theta: float | None,
    difficulty: float | None,
    discrimination: float | None,
    ability_standard_error: float | None,
    ability_attempts: int,
    item_attempts: int,
    historical_accuracy: float | None,
    history_attempts: int,
) -> SelectivePrediction:
    """Predição pré-resposta com abstenção seletiva e intervalo explícito.

    Os sinais são combinados somente na proporção da evidência disponível.
    Mesmo quando a função devolve uma probabilidade, ``abstain=True`` indica
    que ela não deve ser apresentada como conclusão confiável ao usuário.
    """
    components: dict[str, float] = {}
    weighted: list[tuple[float, float, str]] = []

    kt_conf = clamp(mastery_confidence_value, 0.0, 1.0)
    if mastery is not None:
        value = clamp(mastery, 0.0, 1.0)
        weight = 0.38 * kt_conf
        components["kt"] = value
        if weight > 0:
            weighted.append((value, weight, "kt"))

    if retrievability is not None and fsrs_reviews > 0:
        fsrs_conf = clamp(0.30 + 0.70 * (1.0 - math.exp(-max(0, fsrs_reviews) / 5.0)), 0.0, 1.0)
        value = clamp(retrievability, 0.0, 1.0)
        components["fsrs"] = value
        weighted.append((value, 0.34 * fsrs_conf, "fsrs"))

    if theta is not None and difficulty is not None:
        a = clamp(discrimination if discrimination is not None else 1.0, 0.55, 2.20)
        irt_value = sigmoid(a * (float(theta) - float(difficulty)))
        se = 2.5 if ability_standard_error is None else max(0.12, float(ability_standard_error))
        se_conf = clamp(1.0 - (se - 0.25) / 2.75, 0.0, 1.0)
        sample_conf = min(1.0, max(0, ability_attempts) / 20.0) * min(1.0, max(0, item_attempts) / 5.0)
        irt_conf = math.sqrt(max(0.0, se_conf * sample_conf))
        components["irt"] = irt_value
        if irt_conf > 0:
            weighted.append((irt_value, 0.20 * irt_conf, "irt"))

    hist_n = max(0, int(history_attempts))
    if historical_accuracy is not None:
        hist_value = clamp(historical_accuracy, 0.0, 1.0)
        hist_conf = clamp(1.0 - math.exp(-hist_n / 10.0), 0.0, 1.0)
        components["historico"] = hist_value
        if hist_conf > 0:
            weighted.append((hist_value, 0.08 * hist_conf, "historico"))

    if weighted:
        total_weight = sum(item[1] for item in weighted)
        probability = sum(item[0] * item[1] for item in weighted) / max(1e-9, total_weight)
        values = [item[0] for item in weighted]
        agreement = 1.0 if len(values) <= 1 else clamp(1.0 - (max(values) - min(values)) / 0.55, 0.0, 1.0)
        evidence_strength = clamp(total_weight / 0.72, 0.0, 1.0)
        confidence = clamp(0.72 * evidence_strength + 0.28 * agreement, 0.0, 0.98)
    else:
        probability = 0.50
        confidence = 0.0
        agreement = 0.0

    reasons: list[str] = []
    if history_attempts < 3:
        reasons.append("histórico ainda muito pequeno")
    if mastery is None or kt_conf < 0.35:
        reasons.append("KT ainda sem evidência suficiente")
    if ability_attempts < 5 or item_attempts < 2:
        reasons.append("IRT ainda pouco informativa")
    if fsrs_reviews <= 0:
        reasons.append("FSRS ainda sem revisão anterior")
    if len(weighted) >= 2 and agreement < 0.45:
        reasons.append("os sinais do modelo discordam entre si")

    abstain = confidence < 0.38 or history_attempts < 2
    if abstain:
        status = "evidencia_insuficiente"
    elif confidence < 0.62:
        status = "estimativa_cautelosa"
    else:
        status = "estimativa_confiavel"
    radius = clamp(0.07 + 0.30 * (1.0 - confidence), 0.07, 0.36)
    return SelectivePrediction(
        probability=round(clamp(probability, 0.0, 1.0), 6),
        confidence=round(confidence, 6),
        interval_low=round(clamp(probability - radius, 0.0, 1.0), 6),
        interval_high=round(clamp(probability + radius, 0.0, 1.0), 6),
        status=status,
        abstain=abstain,
        reasons=tuple(reasons or ["evidência consistente entre os sinais disponíveis"]),
        components={key: round(value, 6) for key, value in components.items()},
    )


def counterfactual_practice_plan(
    *,
    mastery: float,
    confidence: float,
    exposures: int,
    target_mastery: float = 0.80,
    max_successes: int = 12,
    slip: float = 0.10,
    guess: float = 0.20,
    learn: float = 0.14,
) -> dict:
    """Plano contrafactual conservador baseado na dinâmica do BKT.

    O número calculado é uma *estimativa de práticas corretas necessárias* sob
    os parâmetros atuais, não uma promessa causal de que o domínio real atingirá
    o valor-alvo. Quando a evidência é fraca, o plano começa por diagnóstico.
    """
    current = clamp(mastery, 0.02, 0.995)
    target = clamp(target_mastery, 0.55, 0.95)
    status = evidence_status(confidence=confidence, exposures=exposures)
    diagnostic = max(0, 3 - max(0, int(exposures))) if status["abstain"] else 0
    simulated = current
    successes = 0
    while simulated < target and successes < max(1, int(max_successes)):
        simulated = update_bkt(simulated, True, slip=slip, guess=guess, learn=learn).mastery
        successes += 1
    reached = simulated >= target
    if status["abstain"]:
        action = "coletar_evidencia"
    elif current >= target:
        action = "manter"
    else:
        action = "consolidar"
    return {
        "action": action,
        "current_mastery": round(current, 4),
        "target_mastery": round(target, 4),
        "confidence": round(clamp(confidence, 0.0, 1.0), 4),
        "evidence_status": status,
        "diagnostic_questions_first": diagnostic,
        "estimated_successful_practices": successes if reached else None,
        "simulated_mastery_after": round(simulated, 4),
        "target_reached_in_simulation": reached,
        "caveat": "Estimativa contrafactual do BKT; serve para planejar prática, não garante causalmente o domínio real.",
        "version": MODEL_VERSION,
    }
