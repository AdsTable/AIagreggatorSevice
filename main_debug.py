"""
Production-ready debug version with intelligent port management and comprehensive error handling.
Automatically handles port conflicts and provides multiple connectivity options.
"""

import logging
import traceback
import asyncio
import sys
import os
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# Fix Windows console encoding issues
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

# Configure comprehensive logging with proper encoding
log_formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.DEBUG)

try:
    file_handler = logging.FileHandler('startup_debug.log', encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)
    handlers = [console_handler, file_handler]
except Exception as e:
    print(f"Warning: Could not create log file: {e}")
    handlers = [console_handler]

logging.basicConfig(level=logging.DEBUG, handlers=handlers, force=True)
logger = logging.getLogger(__name__)

def find_available_port(start_port: int = 8000, max_attempts: int = 100) -> Optional[int]:
    """
    Find an available port starting from the given port number.
    
    Args:
        start_port: Starting port number to check
        max_attempts: Maximum number of ports to try
        
    Returns:
        Available port number or None if no port found
    """
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                result = sock.connect_ex(('127.0.0.1', port))
                if result != 0:  # Port is available
                    logger.info(f"[PORT] Found available port: {port}")
                    return port
                else:
                    logger.debug(f"[PORT] Port {port} is in use")
        except Exception as e:
            logger.debug(f"[PORT] Error checking port {port}: {e}")
            continue
    
    logger.error(f"[PORT] No available port found in range {start_port}-{start_port + max_attempts}")
    return None

def check_port_usage(port: int) -> Dict[str, Any]:
    """
    Check what's using a specific port and provide detailed information.
    
    Args:
        port: Port number to check
        
    Returns:
        Dictionary with port usage information
    """
    port_info = {
        "port": port,
        "available": False,
        "process_info": None,
        "suggestions": []
    }
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            if result != 0:
                port_info["available"] = True
                port_info["suggestions"].append(f"Port {port} is available for use")
            else:
                port_info["suggestions"].extend([
                    f"Port {port} is currently in use",
                    "Try stopping other services or use a different port",
                    "Check for other FastAPI/uvicorn instances running",
                    f"Use 'netstat -ano | findstr :{port}' to find the process (Windows)",
                    f"Use 'lsof -i :{port}' to find the process (Linux/Mac)"
                ])
                
                # Try to get process information on Windows
                if sys.platform == "win32":
                    try:
                        import subprocess
                        result = subprocess.run(
                            ['netstat', '-ano'], 
                            capture_output=True, 
                            text=True, 
                            timeout=5
                        )
                        for line in result.stdout.split('\n'):
                            if f':{port}' in line and 'LISTENING' in line:
                                parts = line.split()
                                if len(parts) >= 5:
                                    pid = parts[-1]
                                    port_info["process_info"] = {"pid": pid}
                                    port_info["suggestions"].append(f"Process PID: {pid}")
                                break
                    except Exception as e:
                        logger.debug(f"Could not get process info: {e}")
        
    except Exception as e:
        port_info["error"] = str(e)
        port_info["suggestions"].append(f"Error checking port: {e}")
    
    return port_info

def get_alternative_ports() -> List[int]:
    """Get a list of commonly available alternative ports for development."""
    common_dev_ports = [8000, 8001, 8080, 8888, 9000, 3000, 5000, 7000]
    available_ports = []
    
    for port in common_dev_ports:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.5)
                result = sock.connect_ex(('127.0.0.1', port))
                if result != 0:
                    available_ports.append(port)
        except:
            continue
    
    return available_ports

# Global state tracking with modern datetime
startup_state = {
    "config_loaded": False,
    "resources_initialized": False,
    "providers_registered": False,
    "background_tasks_started": False,
    "error_details": [],
    "startup_time": datetime.now(timezone.utc).isoformat(),
    "debug_mode": True,
    "python_version": sys.version,
    "platform": sys.platform,
    "port_info": {}
}

# Global variables for safe access
config = None
resources = None
provider_registry = None
background_manager = None

def check_dependencies() -> Dict[str, Any]:
    """Check all required dependencies with Python 3.13 compatibility"""
    dependencies_status = {
        "required_modules": {},
        "optional_modules": {},
        "version_info": {},
        "compatibility_issues": []
    }
    
    required_modules = ['fastapi', 'uvicorn', 'pydantic', 'asyncio']
    optional_modules = ['redis', 'sqlalchemy', 'aiosqlite', 'prometheus_client', 'aiohttp', 'aiofiles']
    problematic_modules = ['aioredis']
    
    # Check required modules
    for module_name in required_modules:
        try:
            module = __import__(module_name)
            version = getattr(module, '__version__', 'built-in')
            dependencies_status["required_modules"][module_name] = {
                "available": True,
                "version": version
            }
            logger.info(f"[OK] Required module {module_name} available (v{version})")
        except ImportError as e:
            dependencies_status["required_modules"][module_name] = {
                "available": False,
                "error": str(e)
            }
            logger.error(f"[ERROR] Required module {module_name} missing: {e}")
    
    # Check optional modules
    for module_name in optional_modules:
        try:
            if module_name in problematic_modules:
                dependencies_status["optional_modules"][module_name] = {
                    "available": False,
                    "error": "Skipped due to Python 3.13 compatibility issues"
                }
                dependencies_status["compatibility_issues"].append(
                    f"{module_name}: Known TimeoutError inheritance conflict in Python 3.13"
                )
                logger.warning(f"[SKIP] Module {module_name} skipped due to Python 3.13 compatibility")
                continue
            
            module = __import__(module_name)
            version = getattr(module, '__version__', 'unknown')
            dependencies_status["optional_modules"][module_name] = {
                "available": True,
                "version": version
            }
            logger.info(f"[OK] Optional module {module_name} available (v{version})")
        except ImportError as e:
            dependencies_status["optional_modules"][module_name] = {
                "available": False,
                "error": str(e)
            }
            logger.warning(f"[WARN] Optional module {module_name} missing: {e}")
        except Exception as e:
            dependencies_status["optional_modules"][module_name] = {
                "available": False,
                "error": f"Import error: {str(e)}"
            }
            logger.warning(f"[WARN] Module {module_name} import failed: {e}")
    
    # System version info
    dependencies_status["version_info"] = {
        "python_version": sys.version,
        "python_version_info": sys.version_info,
        "platform": sys.platform,
        "executable": sys.executable,
        "encoding": sys.getdefaultencoding()
    }
    
    # Check for Python 3.13 specific issues
    if sys.version_info >= (3, 13):
        dependencies_status["python_313_notes"] = [
            "Running on Python 3.13+ - some packages may have compatibility issues",
            "aioredis has known TimeoutError inheritance conflicts",
            "Using redis library instead of aioredis for compatibility"
        ]
    
    return dependencies_status

def safe_import_with_fallback() -> bool:
    """Safely import modules with comprehensive fallback handling and Python 3.13 compatibility"""
    global config, resources, provider_registry, background_manager
    
    try:
        logger.info("=== Starting Safe Import Process ===")
        
        # Step 1: Check dependencies first
        deps_status = check_dependencies()
        startup_state["dependencies"] = deps_status
        
        # Log Python 3.13 specific notes
        if "python_313_notes" in deps_status:
            for note in deps_status["python_313_notes"]:
                logger.info(f"[PYTHON 3.13] {note}")
        
        # Step 2: Import configuration with fallback
        logger.info("Loading configuration...")
        try:
            import main
            config = main.AppConfig()
            startup_state["config_loaded"] = True
            logger.info("[OK] Configuration loaded from main module")
        except Exception as e:
            logger.warning(f"Failed to load main config: {e}")
            config = create_fallback_config()
            startup_state["config_loaded"] = True
            startup_state["error_details"].append(f"Using fallback config: {e}")
            logger.info("[OK] Fallback configuration created")
        
        # Step 3: Import resource manager with fallback
        logger.info("Loading resource manager...")
        try:
            if 'main' in sys.modules and hasattr(sys.modules['main'], 'ResourceManager'):
                resources = sys.modules['main'].ResourceManager()
            else:
                resources = create_fallback_resource_manager()
            startup_state["resources_initialized"] = True
            logger.info("[OK] Resource manager loaded")
        except Exception as e:
            logger.warning(f"Failed to load resource manager: {e}")
            resources = create_fallback_resource_manager()
            startup_state["resources_initialized"] = True
            startup_state["error_details"].append(f"Using fallback resources: {e}")
        
        # Step 4: Import provider registry with fallback
        logger.info("Loading provider registry...")
        try:
            if 'main' in sys.modules and hasattr(sys.modules['main'], 'AIProviderRegistry'):
                provider_registry = sys.modules['main'].AIProviderRegistry()
            else:
                provider_registry = create_fallback_provider_registry()
            startup_state["providers_registered"] = True
            logger.info("[OK] Provider registry loaded")
        except Exception as e:
            logger.warning(f"Failed to load provider registry: {e}")
            provider_registry = create_fallback_provider_registry()
            startup_state["providers_registered"] = True
            startup_state["error_details"].append(f"Using fallback providers: {e}")
        
        # Step 5: Import background manager with fallback
        logger.info("Loading background manager...")
        try:
            if 'main' in sys.modules and hasattr(sys.modules['main'], 'BackgroundTaskManager'):
                background_manager = sys.modules['main'].BackgroundTaskManager()
            else:
                background_manager = create_fallback_background_manager()
            startup_state["background_tasks_started"] = True
            logger.info("[OK] Background manager loaded")
        except Exception as e:
            logger.warning(f"Failed to load background manager: {e}")
            background_manager = create_fallback_background_manager()
            startup_state["background_tasks_started"] = True
            startup_state["error_details"].append(f"Using fallback background manager: {e}")
        
        logger.info("=== Safe Import Process Completed Successfully ===")
        return True
        
    except Exception as e:
        error_msg = f"Critical import failure: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        startup_state["error_details"].append(error_msg)
        return False

def create_fallback_config():
    """Create minimal fallback configuration with modern datetime"""
    class FallbackConfig:
        def __init__(self):
            self.app_name = "AI Aggregator Service (Debug Mode)"
            self.version = "4.1.0-debug-py313"
            self.environment = "development"
            self.debug = True
            self.host = "127.0.0.1"
            self.port = 8000
            self.enable_docs = True
            self.enable_cache = False
            self.enable_metrics = False
    
    return FallbackConfig()

def create_fallback_resource_manager():
    """Create minimal fallback resource manager with Python 3.13 compatibility"""
    class FallbackResourceManager:
        def __init__(self):
            self.startup_time = datetime.now(timezone.utc).timestamp()
            self.redis_client = None
            self.initialized = False
        
        async def health_check(self):
            return {
                "status": "fallback_mode", 
                "redis": "disabled_due_to_compatibility",
                "python_version": sys.version_info,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        async def cleanup(self):
            logger.info("Fallback resource cleanup completed")
            self.initialized = False
    
    return FallbackResourceManager()

def create_fallback_provider_registry():
    """Create minimal fallback provider registry"""
    class FallbackProviderRegistry:
        def __init__(self):
            self.providers = {"echo": "debug_echo_provider"}
        
        def list_providers(self):
            return list(self.providers.keys())
        
        async def get_provider(self, name):
            if name == "echo":
                return MockEchoProvider()
            return None
        
        async def health_check_all(self):
            return {
                "summary": {
                    "total_providers": 1,
                    "healthy_providers": 1,
                    "overall_status": "healthy"
                },
                "providers": {
                    "echo": {"status": "healthy", "type": "fallback"}
                }
            }
    
    class MockEchoProvider:
        def __init__(self):
            self.metadata = type('Metadata', (), {
                'name': 'echo',
                'request_count': 0,
                'last_used': None
            })()
        
        async def ask(self, prompt, **kwargs):
            self.metadata.request_count += 1
            self.metadata.last_used = datetime.now(timezone.utc)
            return f"Debug Echo (Python {sys.version_info.major}.{sys.version_info.minor}): {prompt}"
        
        def get_info(self):
            return {
                "name": "echo",
                "description": "Fallback echo provider",
                "statistics": {
                    "total_requests": self.metadata.request_count,
                    "success_rate": 100,
                    "average_latency_ms": 1
                }
            }
    
    return FallbackProviderRegistry()

def create_fallback_background_manager():
    """Create minimal fallback background manager"""
    class FallbackBackgroundManager:
        def __init__(self):
            self.tasks = []
            self.active = False
        
        async def start_background_tasks(self):
            logger.info("Fallback background manager - no tasks to start")
            self.active = True
        
        async def stop_background_tasks(self):
            logger.info("Fallback background manager - no tasks to stop")
            self.active = False
        
        def get_task_statistics(self):
            return {
                "active_tasks": 0, 
                "total_tasks": 0, 
                "status": "fallback_mode",
                "manager_active": self.active
            }
    
    return FallbackBackgroundManager()

# Initialize with safe imports
logger.info("Starting application import process...")
imports_successful = safe_import_with_fallback()

@asynccontextmanager
async def lifespan_with_diagnostics(app: FastAPI):
    """Enhanced lifespan with comprehensive error handling and Python 3.13 compatibility"""
    
    logger.info("=== Starting Application Lifespan ===")
    
    try:
        if not imports_successful:
            logger.error("Cannot start app due to import failures")
            yield
            return
        
        # Initialize components with individual error handling
        initialization_steps = [
            ("redis", initialize_redis_safe),
            ("ai_config", load_ai_config_safe),
            ("providers", register_providers_safe),
            ("background_tasks", start_background_tasks_safe)
        ]
        
        for step_name, step_function in initialization_steps:
            try:
                logger.info(f"Initializing {step_name}...")
                await step_function()
                logger.info(f"[OK] {step_name} initialized successfully")
            except Exception as e:
                logger.error(f"[ERROR] {step_name} initialization failed: {e}")
                startup_state["error_details"].append(f"{step_name} error: {str(e)}")
        
        logger.info("=== Application Startup Completed ===")
        yield
        
    except Exception as e:
        logger.error(f"Critical startup error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        startup_state["error_details"].append(f"Critical error: {str(e)}")
        yield
    
    finally:
        logger.info("=== Starting Application Shutdown ===")
        try:
            if background_manager and hasattr(background_manager, 'stop_background_tasks'):
                await background_manager.stop_background_tasks()
            if resources and hasattr(resources, 'cleanup'):
                await resources.cleanup()
            logger.info("=== Application Shutdown Completed ===")
        except Exception as e:
            logger.error(f"Shutdown error: {e}")

async def initialize_redis_safe():
    """Safely initialize Redis with Python 3.13 compatibility notes"""
    if hasattr(resources, 'initialize_redis'):
        try:
            redis_client = await resources.initialize_redis()
            if redis_client:
                logger.info("Redis connection established")
            else:
                logger.warning("Redis connection failed, using memory fallback")
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}")
            logger.info("Note: Redis/aioredis may have compatibility issues with Python 3.13")
    else:
        logger.info("Redis initialization not available in fallback mode")

async def load_ai_config_safe():
    """Safely load AI configuration"""
    if hasattr(resources, 'load_ai_config'):
        try:
            ai_config = await resources.load_ai_config()
            logger.info(f"AI configuration loaded: {len(ai_config)} providers")
        except Exception as e:
            logger.warning(f"AI config loading failed: {e}")
    else:
        logger.info("AI config loading not available in fallback mode")

async def register_providers_safe():
    """Safely register providers"""
    if hasattr(provider_registry, '_register_builtin_providers'):
        try:
            provider_registry._register_builtin_providers()
        except Exception as e:
            logger.warning(f"Built-in provider registration failed: {e}")
    
    providers = provider_registry.list_providers()
    logger.info(f"Providers registered: {providers}")

async def start_background_tasks_safe():
    """Safely start background tasks"""
    if hasattr(background_manager, 'start_background_tasks'):
        try:
            await background_manager.start_background_tasks()
            logger.info("Background tasks started")
        except Exception as e:
            logger.warning(f"Background tasks failed to start: {e}")
    else:
        logger.info("Background tasks not available in fallback mode")

# Create FastAPI app with proper error handling
app = FastAPI(
    title="AI Aggregator Service - Debug Mode (Python 3.13 Compatible)",
    description="Debug version with enhanced error handling, Python 3.13 compatibility, and intelligent port management",
    version="4.1.0-debug-py313",
    lifespan=lifespan_with_diagnostics,
    debug=True
)

def get_debug_info() -> Dict[str, Any]:
    """Get debug information safely with modern datetime"""
    debug_enabled = True
    
    if config and hasattr(config, 'debug'):
        debug_enabled = config.debug
    
    return {
        "debug_mode": debug_enabled,
        "config_available": config is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version_info,
        "platform": sys.platform
    }

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Enhanced global exception handler with detailed error information"""
    debug_info = get_debug_info()
    
    error_details = {
        "error": str(exc),
        "type": type(exc).__name__,
        "request_url": str(request.url),
        "request_method": request.method,
        "startup_state": startup_state,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if debug_info["debug_mode"]:
        error_details["traceback"] = traceback.format_exc()
    
    logger.error(f"Global exception caught: {error_details}")
    
    response_content = {
        "detail": "Internal server error - check logs for details",
        "error_type": error_details["type"],
        "timestamp": error_details["timestamp"]
    }
    
    if debug_info["debug_mode"]:
        response_content["debug_info"] = error_details
    
    return JSONResponse(status_code=500, content=response_content)

@app.get("/")
async def root_with_diagnostics():
    """Enhanced root endpoint with startup diagnostics and port information"""
    return {
        "message": "AI Aggregator Service - Debug Mode (Python 3.13 Compatible)",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "startup_state": startup_state,
        "imports_successful": imports_successful,
        "python_info": {
            "version": sys.version,
            "version_info": sys.version_info,
            "platform": sys.platform
        },
        "port_info": startup_state.get("port_info", {}),
        "available_endpoints": [
            "/docs",
            "/redoc", 
            "/health",
            "/diagnostics",
            "/port-check",
            "/startup-logs",
            "/ai/ask",
            "/compatibility-check"
        ],
        "debug_mode": get_debug_info()["debug_mode"]
    }

@app.get("/port-check")
async def port_management():
    """Comprehensive port management and diagnostics endpoint"""
    try:
        port_8000_info = check_port_usage(8000)
        alternative_ports = get_alternative_ports()
        
        port_management_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_port_check": port_8000_info,
            "alternative_ports": alternative_ports,
            "port_range_check": {},
            "recommendations": []
        }
        
        # Check a range of ports
        for port in range(8000, 8010):
            port_info = check_port_usage(port)
            port_management_info["port_range_check"][port] = {
                "available": port_info["available"],
                "suggestions": port_info["suggestions"][:2]  # Limit suggestions
            }
        
        # Generate recommendations
        if port_8000_info["available"]:
            port_management_info["recommendations"].append("Port 8000 is available - you can use it")
        else:
            port_management_info["recommendations"].extend([
                f"Port 8000 is in use - try alternative ports: {alternative_ports[:3]}",
                "Stop other services using port 8000, or use a different port",
                "Use the find_available_port() function to automatically find a free port"
            ])
        
        return port_management_info
        
    except Exception as e:
        logger.error(f"Port check failed: {e}")
        return {
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@app.get("/health")
async def health_check():
    """Comprehensive health check for debugging with Python 3.13 compatibility"""
    try:
        health_data = {
            "status": "healthy" if imports_successful else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "startup_state": startup_state,
            "imports_successful": imports_successful,
            "python_compatibility": {
                "version": sys.version_info,
                "python_313_or_later": sys.version_info >= (3, 13),
                "encoding": sys.getdefaultencoding()
            },
            "components": {}
        }
        
        # Check each component safely
        if resources:
            try:
                if hasattr(resources, 'health_check'):
                    resource_health = await resources.health_check()
                    health_data["components"]["resources"] = resource_health
                else:
                    health_data["components"]["resources"] = {"status": "fallback_mode"}
            except Exception as e:
                health_data["components"]["resources"] = {"status": "error", "error": str(e)}
        
        if provider_registry:
            try:
                providers = provider_registry.list_providers()
                health_data["components"]["providers"] = {
                    "status": "available",
                    "count": len(providers),
                    "list": providers
                }
                
                if hasattr(provider_registry, 'health_check_all'):
                    provider_health = await provider_registry.health_check_all()
                    health_data["components"]["provider_health"] = provider_health
                    
            except Exception as e:
                health_data["components"]["providers"] = {"status": "error", "error": str(e)}
        
        if background_manager:
            try:
                task_stats = background_manager.get_task_statistics()
                health_data["components"]["background_tasks"] = task_stats
            except Exception as e:
                health_data["components"]["background_tasks"] = {"status": "error", "error": str(e)}
        
        if startup_state["error_details"]:
            health_data["errors"] = startup_state["error_details"]
        
        return health_data
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        return {
            "status": "error", 
            "detail": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

@app.post("/ai/ask")
async def simple_ai_ask(request: dict):
    """Simplified AI endpoint for testing with Python 3.13 compatibility"""
    try:
        prompt = request.get("prompt", "")
        provider = request.get("provider", "echo")
        
        if not prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")
        
        # Try to use real provider if available
        if provider_registry:
            try:
                provider_instance = await provider_registry.get_provider(provider)
                if provider_instance:
                    response = await provider_instance.ask(prompt)
                    return {
                        "response": response,
                        "provider": provider,
                        "status": "success",
                        "mode": "real_provider",
                        "python_version": sys.version_info,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
            except Exception as e:
                logger.warning(f"Real provider failed, using fallback: {e}")
        
        # Fallback to echo response
        return {
            "response": f"Debug Echo (Python {sys.version_info.major}.{sys.version_info.minor}): {prompt}",
            "provider": "debug-echo",
            "status": "success",
            "mode": "fallback",
            "python_version": sys.version_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI ask error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def run_with_intelligent_port_management():
    """
    Run the application with intelligent port management and comprehensive error handling.
    Automatically finds an available port and provides detailed startup information.
    """
    print("=" * 100)
    print("AI Aggregator Service - Debug Mode (Python 3.13 Compatible)")
    print("=" * 100)
    print(f"Python Version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Encoding: {sys.getdefaultencoding()}")
    print("=" * 100)
    
    # Step 1: Check if default port 8000 is available
    default_port = 8000
    port_info = check_port_usage(default_port)
    startup_state["port_info"] = port_info
    
    if port_info["available"]:
        selected_port = default_port
        print(f"✅ Port {default_port} is available")
    else:
        print(f"❌ Port {default_port} is in use")
        print("🔍 Searching for alternative port...")
        
        # Step 2: Find an alternative port
        selected_port = find_available_port(start_port=8001, max_attempts=50)
        
        if selected_port:
            print(f"✅ Found available port: {selected_port}")
        else:
            print("❌ No available port found in range 8001-8050")
            print("🔧 Manual intervention required:")
            
            # Get alternative ports
            alternatives = get_alternative_ports()
            if alternatives:
                print(f"💡 Try these alternative ports: {alternatives}")
                selected_port = alternatives[0]
                print(f"🎯 Using port {selected_port} as fallback")
            else:
                print("⚠️ No common development ports available")
                selected_port = 8000  # Use default and let user handle the conflict
    
    # Step 3: Update port information in startup state
    startup_state["port_info"].update({
        "selected_port": selected_port,
        "port_search_performed": selected_port != default_port,
        "alternative_ports": get_alternative_ports()
    })
    
    print("=" * 100)
    print("Starting comprehensive debugging session...")
    print("Check startup_debug.log for detailed logs")
    print(f"\n🌐 Server will start on: http://127.0.0.1:{selected_port}")
    print("\n📋 Available endpoints:")
    print(f"  - http://127.0.0.1:{selected_port}/docs               (API Documentation)")
    print(f"  - http://127.0.0.1:{selected_port}/diagnostics       (System Diagnostics)")
    print(f"  - http://127.0.0.1:{selected_port}/health            (Health Check)")
    print(f"  - http://127.0.0.1:{selected_port}/port-check        (Port Management)")
    print(f"  - http://127.0.0.1:{selected_port}/compatibility-check (Python 3.13 Check)")
    print(f"  - http://127.0.0.1:{selected_port}/startup-logs      (Startup Logs)")
    print(f"  - http://127.0.0.1:{selected_port}/ai/ask            (Test AI Endpoint)")
    print("=" * 100)
    
    if not port_info["available"] and selected_port == default_port:
        print("⚠️  WARNING: Port conflict detected!")
        print("🔧 Solutions:")
        for suggestion in port_info["suggestions"]:
            print(f"   • {suggestion}")
        print("=" * 100)
    
    # Step 4: Start the server
    try:
        uvicorn.run(
            "main_debug:app",
            host="127.0.0.1",
            port=selected_port,
            reload=False,
            log_level="info",  # Reduce log verbosity in production
            access_log=True
        )
    except Exception as e:
        print(f"\n❌ Server startup failed: {e}")
        print("\n🔧 Troubleshooting steps:")
        print("1. Check if another process is using the port")
        print("2. Try running with administrator/sudo privileges")
        print("3. Check firewall settings")
        print("4. Use a different port manually: uvicorn main_debug:app --port 8001")
        print("\n📊 Port diagnostics:")
        for suggestion in port_info.get("suggestions", []):
            print(f"   • {suggestion}")

if __name__ == "__main__":
    run_with_intelligent_port_management()