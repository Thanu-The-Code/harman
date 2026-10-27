"""
Global error handling middleware and exception handlers.
"""
import traceback
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from loguru import logger
from datetime import datetime

from ..utils.logging_config import log_security_event


class ErrorHandler:
    """
    Global error handler for the application.
    """
    
    @staticmethod
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """
        Handle HTTP exceptions with user-friendly messages.
        
        Args:
            request: FastAPI request object
            exc: HTTP exception
            
        Returns:
            JSON response with error details
        """
        # Log the error with full details for 500 errors
        if exc.status_code == 500:
            logger.error(
                f"HTTP 500 error on {request.method} {request.url.path}",
                status_code=exc.status_code,
                detail=exc.detail,
                headers=dict(request.headers) if hasattr(request, 'headers') else {},
                exc_info=True  # This will log the full traceback
            )
        else:
            logger.error(
                f"HTTP {exc.status_code} error on {request.method} {request.url.path}",
                status_code=exc.status_code,
                detail=exc.detail,
                headers=dict(request.headers) if hasattr(request, 'headers') else {}
            )
        
        # Log security events for certain status codes
        if exc.status_code in [401, 403, 429]:
            log_security_event(
                event_type=f"http_error_{exc.status_code}",
                ip_address=request.client.host if hasattr(request, 'client') and request.client else None,
                user_agent=request.headers.get("user-agent"),
                details={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": exc.status_code,
                    "detail": str(exc.detail)
                }
            )
        
        # Create user-friendly error messages
        user_messages = {
            400: "Bad Request - The request contains invalid data.",
            401: "Authentication Required - Please log in to access this resource.",
            403: "Access Forbidden - You don't have permission to access this resource.",
            404: "Not Found - The requested resource could not be found.",
            405: "Method Not Allowed - This HTTP method is not allowed for this endpoint.",
            409: "Conflict - The request conflicts with the current state of the resource.",
            422: "Validation Error - The submitted data contains errors.",
            429: "Too Many Requests - Please slow down and try again later.",
            500: "Internal Server Error - Something went wrong on our end.",
            502: "Bad Gateway - The server received an invalid response.",
            503: "Service Unavailable - The service is temporarily unavailable.",
            504: "Gateway Timeout - The server took too long to respond."
        }
        
        user_message = user_messages.get(exc.status_code, "An error occurred while processing your request.")
        
        # Include original detail for debugging in non-production
        error_response = {
            "error": {
                "status_code": exc.status_code,
                "message": user_message,
                "detail": exc.detail if exc.status_code != 500 else "Internal server error",
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response,
            headers=getattr(exc, 'headers', None)
        )
    
    @staticmethod
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        """
        Handle Pydantic validation errors with detailed field information.
        
        Args:
            request: FastAPI request object
            exc: Validation exception
            
        Returns:
            JSON response with validation error details
        """
        # Logged without the body or the inputs: a sign-in or a new user's form carries a password
        logger.warning(
            f"Validation error on {request.method} {request.url.path}",
            errors=[{"loc": e.get("loc"), "type": e.get("type")} for e in exc.errors()],
        )

        # Format validation errors for user
        formatted_errors = []
        for error in exc.errors():
            field_path = " -> ".join(str(x) for x in error["loc"])
            formatted_errors.append({
                "field": field_path,
                # "Value error, The password must ..." reads as "The password must ..."
                "message": str(error["msg"]).removeprefix("Value error, "),
                "type": error["type"],
                "input": _shown_input(error),
            })
        
        error_response = {
            "error": {
                "status_code": 422,
                "message": "Validation failed for the submitted data.",
                "detail": "Please check the highlighted fields and try again.",
                "validation_errors": formatted_errors,
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_response
        )
    
    @staticmethod
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        Handle unexpected exceptions with proper logging and user-friendly messages.
        
        Args:
            request: FastAPI request object
            exc: General exception
            
        Returns:
            JSON response with error information
        """
        # Log the full exception with traceback
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            traceback=traceback.format_exc(),
            request_headers=dict(request.headers) if hasattr(request, 'headers') else {}
        )
        
        # Log as security event (potential attack or system issue)
        log_security_event(
            event_type="unhandled_exception",
            ip_address=request.client.host if hasattr(request, 'client') and request.client else None,
            user_agent=request.headers.get("user-agent"),
            details={
                "path": request.url.path,
                "method": request.method,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc)[:500]  # Truncate for security
            }
        )
        
        error_response = {
            "error": {
                "status_code": 500,
                "message": "An unexpected error occurred while processing your request.",
                "detail": "Please check the server logs for more information.",
                "error_id": datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response
        )
    
    @staticmethod
    async def starlette_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """
        Always return JSON for API responses.

        This backend is API-only, so even framework or middleware HTTP errors must
        be serialized as JSON to keep clients consistent.
        """
        logger.error(
            f"Starlette HTTP {exc.status_code} error on {request.method} {request.url.path}",
            status_code=exc.status_code,
            detail=exc.detail,
        )

        error_response = {
            "error": {
                "status_code": exc.status_code,
                "message": "An error occurred while processing your request.",
                "detail": exc.detail,
                "path": request.url.path,
                "method": request.method,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }

        return JSONResponse(
            status_code=exc.status_code,
            content=error_response,
        )


# Custom exception classes
class DocumentNotFoundError(HTTPException):
    """Exception for when a document is not found"""
    def __init__(self, document_id: str):
        super().__init__(
            status_code=404,
            detail=f"Document with ID '{document_id}' not found"
        )


class InsufficientPermissionsError(HTTPException):
    """Exception for insufficient permissions"""
    def __init__(self, required_permission: str):
        super().__init__(
            status_code=403,
            detail=f"Insufficient permissions. Required: {required_permission}"
        )




class ConfigurationError(HTTPException):
    """Exception for configuration errors"""
    def __init__(self, message: str):
        super().__init__(
            status_code=500,
            detail=f"Configuration error: {message}"
        )


class ServiceUnavailableError(HTTPException):
    """Exception for when a service is unavailable"""
    def __init__(self, service_name: str):
        super().__init__(
            status_code=503,
            detail=f"Service '{service_name}' is currently unavailable"
        )


def _shown_input(error: dict):
    """What was sent, echoed back only when it is short plain data and not a secret
    (raw bytes - a body that was not JSON - cannot be put in a JSON answer at all)."""
    if any("password" in str(part).lower() or "secret" in str(part).lower() for part in error.get("loc") or ()):
        return None
    value = error.get("input")
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 200 else value[:200] + "…"
    return None
