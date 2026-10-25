from pydantic import BaseModel, Field
from typing import Dict, Any

class PersonaState(BaseModel):
    """
    Structured 5-Signal Persona Drift state.
    Restricted to 5 independent, high-value signals to maintain signal-to-noise ratio.
    """
    user_id: str
    verbosity_ratio: float = Field(default=1.0, ge=0.0, le=5.0)     # user word count / assistant word count
    rephrasing_rate: float = Field(default=0.0, ge=0.0, le=1.0)     # frequency of detected rephrasings
    formality_score: float = Field(default=0.5, ge=0.0, le=1.0)     # 0.0 (very casual) to 1.0 (academic/formal)
    question_frequency: float = Field(default=0.2, ge=0.0, le=1.0)  # proportion of user turns containing questions
    topic_return_rate: float = Field(default=0.1, ge=0.0, le=1.0)   # rate of reintroducing earlier topics

    def update_ema(self, new_metrics: Dict[str, float], alpha: float = 0.25):
        """
        Updates metrics using Exponential Moving Average (EMA).
        """
        if "verbosity_ratio" in new_metrics:
            self.verbosity_ratio = (1.0 - alpha) * self.verbosity_ratio + alpha * new_metrics["verbosity_ratio"]
        if "rephrasing_rate" in new_metrics:
            self.rephrasing_rate = (1.0 - alpha) * self.rephrasing_rate + alpha * new_metrics["rephrasing_rate"]
        if "formality_score" in new_metrics:
            self.formality_score = (1.0 - alpha) * self.formality_score + alpha * new_metrics["formality_score"]
        if "question_frequency" in new_metrics:
            self.question_frequency = (1.0 - alpha) * self.question_frequency + alpha * new_metrics["question_frequency"]
        if "topic_return_rate" in new_metrics:
            self.topic_return_rate = (1.0 - alpha) * self.topic_return_rate + alpha * new_metrics["topic_return_rate"]

    def generate_prompt_directive(self) -> str:
        """
        Translates the 5 numerical signals into concrete behavioral instructions for the LLM.
        """
        directives = []

        # 1. Verbosity Adaptation
        if self.verbosity_ratio <= 0.6:
            directives.append("- The user prefers high-density responses. Keep your answers direct, crisp, and avoid filler.")
        elif self.verbosity_ratio > 1.5:
            directives.append("- The user enjoys conversational, comprehensive explanations. Provide thorough details and conversational flow.")

        # 2. Formality Adaptation
        if self.formality_score <= 0.35:
            directives.append("- Adopt a casual, approachable, and natural tone.")
        elif self.formality_score > 0.65:
            directives.append("- Adopt a professional, technically rigorous, and structured tone.")

        # 3. Rephrasing / Frustration Adaptation
        if self.rephrasing_rate > 0.3:
            directives.append("- ATTENTION: The user frequently rephrases questions. Address their intent with utmost clarity and verify alignment.")

        # 4. Inquisitiveness Adaptation
        if self.question_frequency > 0.4:
            directives.append("- The user is exploratory and asks frequent questions. Proactively offer structured explanations and logical next steps.")

        # 5. Topic Return Adaptation
        if self.topic_return_rate > 0.3:
            directives.append("- The user frequently revisits core themes. Connect current responses to their overarching project topics.")

        if not directives:
            return "Respond in a balanced, helpful, and natural manner."

        return "PERSONA ADAPTATION DIRECTIVES:\n" + "\n".join(directives)
