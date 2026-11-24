"""Per-job connection profiles. No credentials or automatic provider fallback."""
from dataclasses import dataclass

from webapp.api import BASE_URL, MODEL, DEPARTMENT_MODEL


@dataclass(frozen=True)
class LlmConnection:
    provider: str
    label: str
    base_url: str
    model: str
    department_model: str
    token_field: str


def resolve_connection(provider='openai'):
    if provider == 'openai':
        return LlmConnection(provider, 'OpenAI', BASE_URL, MODEL, DEPARTMENT_MODEL, 'max_completion_tokens')
    raise ValueError('OpenAI API 키만 사용할 수 있습니다.')
