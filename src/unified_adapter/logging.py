 """Logging helpers with redaction."""
 
 from __future__ import annotations
 
 import logging
 import re
 from typing import Any, Dict
 
 
 _SENSITIVE_KEYS = re.compile(r"(token|secret|api[_-]?key|password)", re.IGNORECASE)
 
 
 def configure_logging(level: str) -> None:
     logging.basicConfig(
         level=level,
         format="%(asctime)s %(levelname)s %(name)s %(message)s",
     )
 
 
 def redact_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
     redacted: Dict[str, Any] = {}
     for key, value in payload.items():
         if _SENSITIVE_KEYS.search(key):
             redacted[key] = "***REDACTED***"
         elif isinstance(value, dict):
             redacted[key] = redact_payload(value)
         else:
             redacted[key] = value
     return redacted
