 """OpenAPI spec loader and operation parser."""
 
 from __future__ import annotations
 
 import logging
 import time
 from dataclasses import dataclass
 from typing import Any, Dict, Iterable, List, Optional, Tuple
 
 import httpx
 from pydantic import BaseModel, ConfigDict, Field, create_model
 
 
 logger = logging.getLogger(__name__)
 
 
 @dataclass(frozen=True)
 class OpenAPIOperation:
     operation_id: str
     method: str
     path: str
     description: str
     input_model: type[BaseModel]
 
 
 class OpenAPILoader:
     def __init__(self, cache_seconds: int = 3600) -> None:
         self.cache_seconds = cache_seconds
         self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
 
     async def load_spec(self, url: str) -> Optional[Dict[str, Any]]:
         cached = self._cache.get(url)
         if cached and time.time() - cached[0] < self.cache_seconds:
             return cached[1]
 
         async with httpx.AsyncClient(timeout=30) as client:
             response = await client.get(url)
             if response.status_code != 200:
                 logger.warning("Failed to fetch OpenAPI spec: %s (%s)", url, response.status_code)
                 return None
             data = response.json()
 
         self._cache[url] = (time.time(), data)
         return data
 
     def extract_operations(self, spec: Dict[str, Any]) -> List[OpenAPIOperation]:
         operations: List[OpenAPIOperation] = []
         paths = spec.get("paths") or {}
 
         for path, methods in paths.items():
             shared_parameters = (methods or {}).get("parameters") or []
             for method, operation in (methods or {}).items():
                 if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                     continue
                 operation_id = operation.get("operationId") or self._fallback_operation_id(
                     method, path
                 )
                 description = operation.get("description") or operation.get("summary") or ""
                 input_model = self._build_input_model(operation, operation_id, shared_parameters)
 
                 operations.append(
                     OpenAPIOperation(
                         operation_id=operation_id,
                         method=method.lower(),
                         path=path,
                         description=description,
                         input_model=input_model,
                     )
                 )
 
         return operations
 
     def _build_input_model(
         self, operation: Dict[str, Any], operation_id: str, shared_parameters: List[Dict[str, Any]]
     ) -> type[BaseModel]:
         fields: Dict[str, Tuple[Any, Any]] = {}
         parameters = [*shared_parameters, *(operation.get("parameters") or [])]
 
         for parameter in parameters:
             name = parameter.get("name")
             if not name:
                 continue
             schema = parameter.get("schema") or {}
             required = parameter.get("required", False)
             field_type = self._schema_to_type(schema)
             default = Field(... if required else None, description=parameter.get("description"))
             fields[name] = (field_type, default)
 
         request_body = operation.get("requestBody") or {}
         body_schema = self._extract_body_schema(request_body)
         if body_schema:
             fields["body"] = (Dict[str, Any], Field(None, description="Request body"))
 
         model_config = ConfigDict(extra="allow")
         model_name = f"{self._sanitize_name(operation_id)}Input"
         return create_model(model_name, __config__=model_config, **fields)
 
     def _extract_body_schema(self, request_body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
         content = request_body.get("content") or {}
         json_body = content.get("application/json") or {}
         return json_body.get("schema")
 
     def _schema_to_type(self, schema: Dict[str, Any]) -> Any:
         schema_type = schema.get("type")
         if schema_type == "integer":
             return int
         if schema_type == "number":
             return float
         if schema_type == "boolean":
             return bool
         if schema_type == "array":
             return List[Any]
         if schema_type == "object":
             return Dict[str, Any]
         return str
 
     def _fallback_operation_id(self, method: str, path: str) -> str:
         sanitized = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
         return f"{method}_{sanitized or 'root'}"
 
     def _sanitize_name(self, name: str) -> str:
         return "".join(ch if ch.isalnum() else "_" for ch in name)
