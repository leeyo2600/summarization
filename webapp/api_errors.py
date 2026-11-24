"""Explain API failures without exposing credentials or raw proxy error pages."""
import re
from urllib.parse import quote, urlparse


CODE_HELP = {
    'insufficient_quota': 'API 잔액 또는 사용 한도가 부족합니다. OpenAI의 결제·사용 한도를 확인해주세요.',
    'invalid_api_key': 'API 키 인증에 실패했습니다. OpenAI에서 발급한 유효한 키인지 확인해주세요.',
    'model_not_found': '요청 모델을 찾을 수 없거나 사용할 권한이 없습니다. OpenAI의 모델 사용 권한을 확인해주세요.',
    'unsupported_country_region_territory': '현재 접속 지역에서 API 접근이 허용되지 않았습니다. 서비스의 지원 지역과 기관의 인터넷 접속 경로를 확인해주세요.',
}


def safe_detail(value, key, limit=400):
    if not isinstance(value, str):
        return ''
    # Redact before truncating, including keys echoed in error codes or request IDs.
    if key:
        for secret in (key, quote(key, safe='')):
            value = value.replace(secret, '[REDACTED]')
    value = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[REDACTED]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s,;"\']+', 'Bearer [REDACTED]', value)
    value = ''.join(char if char.isprintable() else ' ' for char in value)
    return ' '.join(value.split())[:limit]


def http_error_message(response, url, model, key):
    host = urlparse(url).hostname
    provider = 'OpenAI' if host == 'api.openai.com' else 'LLM'
    status = response.status_code
    try:
        body = response.json()
    except (ValueError, TypeError):
        body = None
    error = body.get('error', body) if isinstance(body, dict) else None
    if isinstance(error, str):
        error = {'message': error, 'code': body.get('code')}
    if not isinstance(error, dict):
        error = {}
    code = safe_detail(error.get('code') or error.get('type'), key, 100)
    detail = safe_detail(error.get('message'), key)
    hint = CODE_HELP.get(code)
    if not hint:
        if status == 401:
            hint = 'OpenAI API 키가 유효한지 확인해주세요.'
        elif status == 403:
            hint = '접근이 거부되었습니다. API 키·조직의 사용 권한과 허용 IP·접속 지역을 확인해주세요.'
        elif status == 429:
            hint = '요청 횟수 또는 사용 한도에 도달했습니다. 서비스의 사용량과 잔액을 확인해주세요.'
        elif status >= 500:
            hint = 'API 서비스 처리 오류입니다. 서비스 상태를 확인한 뒤 다시 시도해주세요.'
        else:
            hint = 'API 요청을 처리하지 못했습니다. 아래 오류 상세정보를 확인해주세요.'
    parts = [f'{provider} API HTTP {status} · 모델 {safe_detail(model, key, 150)}: {hint}']
    if code:
        parts.append('오류 코드: ' + code)
    if detail:
        parts.append('서버 안내: ' + detail)
    if status == 403 and not code and not detail:
        parts.append('서버가 오류 상세정보를 반환하지 않았습니다. 기관 프록시·보안 장비의 차단 여부도 확인해주세요.')
    headers = getattr(response, 'headers', {})
    request_id = safe_detail(headers.get('x-request-id') or headers.get('request-id'), key, 100)
    if request_id:
        parts.append('요청 ID: ' + request_id)
    return '\n'.join(parts)
