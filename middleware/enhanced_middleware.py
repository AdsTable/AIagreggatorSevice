# middleware/enhanced_middleware.py - Production-ready middleware with security and performance
from __future__ import annotations

import time
import json
import logging
from typing import Callable, Optional, Dict, Any
from uuid import uuid4

from fastapi import Request, Response, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import jwt
from datetime import datetime, timedelta

from config.settings import settings

logger = logging.getLogger(__name__)

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Add request context and tracing"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Generate request ID for tracing
        request_id = str(uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.time()
        
        # Add request ID to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        # Log request completion
        duration = time.time() - request.state.start_time
        logger.info(
            f"Request completed: {request.method} {request.url.path} "
            f"[{response.status_code}] {duration:.3f}s",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_seconds": duration,
                "user_agent": request.headers.get("user-agent"),
                "ip_address": request.client.host if request.client else None
            }
        )
        
        return response

class SecurityMiddleware(BaseHTTPMiddleware):
    """Enhanced security middleware with multiple protection layers"""
    
    def __init__(self, app, api_keys: Optional[Dict[str, str]] = None):
        super().__init__(app)
        self.api_keys = api_keys or {}
        self.security = HTTPBearer(auto_error=False)
        
        # Security headers
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip security for health checks and docs
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            response = await call_next(request)
            return self._add_security_headers(response)
        
        # Check API key authentication
        api_key = request.headers.get(settings.security.api_key_header)
        if api_key and api_key in self.api_keys:
            request.state.user_id = self.api_keys[api_key]
            request.state.auth_method = "api_key"
        else:
            # Check JWT token
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
                try:
                    payload = jwt.decode(
                        token, 
                        settings.security.secret_key, 
                        algorithms=[settings.security.jwt_algorithm]
                    )
                    request.state.user_id = payload.get("sub")
                    request.state.auth_method = "jwt"
                except jwt.PyJWTError:
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Invalid authentication token"}
                    )
        
        # Rate limiting check (basic implementation)
        if hasattr(request.state, 'user_id'):
            # TODO: Implement Redis-based rate limiting
            pass
        
        response = await call_next(request)
        return self._add_security_headers(response)
    
    def _add_security_headers(self, response: Response) -> Response:
        """Add security headers to response"""
        for header, value in self.security_headers.items():
            response.headers[header] = value
        return response

class PerformanceMiddleware(BaseHTTPMiddleware):
    """Performance monitoring and optimization middleware"""
    
    def __init__(self, app, slow_request_threshold: float = 2.0):
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold
        
    async def dispatch(self, request: Request, call_next: Callable):
        start_time = time.time()
        
        # Add performance headers
        response = await call_next(request)
        
        duration = time.time() - start_time
        response.headers["X-Response-Time"] = f"{duration:.3f}s"
        
        # Log slow requests
        if duration > self.slow_request_threshold:
            logger.warning(
                f"Slow request detected: {request.method} {request.url.path} took {duration:.3f}s",
                extra={
                    "request_id": getattr(request.state, 'request_id', 'unknown'),
                    "duration_seconds": duration,
                    "threshold": self.slow_request_threshold
                }
            )
        
        # Update metrics if available
        if settings.monitoring.enable_metrics:
            from prometheus_client import Histogram
            REQUEST_DURATION = Histogram('http_request_duration_seconds', 'HTTP request duration')
            REQUEST_DURATION.observe(duration)
        
        return response

class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Global error handling and logging"""
    
    async def dispatch(self, request: Request, call_next: Callable):
        try:
            response = await call_next(request)
            return response
        except HTTPException:
            # Re-raise HTTP exceptions (they're handled by FastAPI)
            raise
        except Exception as e:
            # Log unexpected errors
            request_id = getattr(request.state, 'request_id', 'unknown')
            logger.error(
                f"Unhandled exception in request {request_id}: {str(e)}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error_type": type(e).__name__
                }
            )
            
            # Return generic error response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

class CacheControlMiddleware(BaseHTTPMiddleware):
    """Intelligent cache control for API responses"""
    
    def __init__(self, app):
        super().__init__(app)
        self.cache_rules = {
            "/health": {"max_age": 60, "public": True},
            "/api/products": {"max_age": 300, "public": True},
            "/admin": {"max_age": 0, "private": True},
        }
    
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Apply cache control rules
        path = request.url.path
        for pattern, rules in self.cache_rules.items():
            if path.startswith(pattern):
                cache_control = []
                
                if rules.get("public"):
                    cache_control.append("public")
                elif rules.get("private"):
                    cache_control.append("private")
                
                max_age = rules.get("max_age", 0)
                cache_control.append(f"max-age={max_age}")
                
                response.headers["Cache-Control"] = ", ".join(cache_control)
                break
        
        return response