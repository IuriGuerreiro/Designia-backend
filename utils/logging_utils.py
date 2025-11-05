from typing import Dict, Iterable


def mask_value(value: str) -> str:
    if not isinstance(value, str):
        return value
    if '@' in value:  # email
        name, _, domain = value.partition('@')
        return (name[:2] + '***@' + domain) if name else '***@' + domain
    if len(value) > 12:
        return value[:4] + '...' + value[-4:]
    return '***'


def sanitize_payload(payload: Dict, allowed_keys: Iterable[str]) -> Dict:
    """Return a filtered copy of payload with only allowed keys and masked values."""
    result = {}
    for key in allowed_keys:
        if key in payload:
            result[key] = mask_value(payload[key])
    return result

