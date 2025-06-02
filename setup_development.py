#!/usr/bin/env python3
# setup_development.py - Automated development environment setup
import os
import sys
import subprocess
import time
import requests
from pathlib import Path

def check_command_exists(command):
    """Check if a command exists in PATH"""
    try:
        subprocess.run([command, '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def install_redis():
    """Install and start Redis"""
    print("🔧 Setting up Redis...")
    
    if sys.platform == "win32":
        print("On Windows, please install Redis manually or use Docker:")
        print("docker run -d -p 6379:6379 redis:alpine")
        return False
    elif sys.platform == "darwin":  # macOS
        try:
            subprocess.run(["brew", "install", "redis"], check=True)
            subprocess.run(["brew", "services", "start", "redis"], check=True)
            print("✅ Redis installed and started via Homebrew")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install Redis via Homebrew")
            return False
    else:  # Linux
        try:
            subprocess.run(["sudo", "apt-get", "update"], check=True)
            subprocess.run(["sudo", "apt-get", "install", "-y", "redis-server"], check=True)
            subprocess.run(["sudo", "systemctl", "start", "redis"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", "redis"], check=True)
            print("✅ Redis installed and started via apt")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install Redis via apt")
            return False

def install_ollama():
    """Install Ollama for local AI"""
    print("🤖 Setting up Ollama...")
    
    try:
        if sys.platform == "win32":
            print("Please download Ollama from: https://ollama.ai/download/windows")
            return False
        elif sys.platform == "darwin":
            print("Please download Ollama from: https://ollama.ai/download/mac")
            return False
        else:  # Linux
            subprocess.run(["curl", "-fsSL", "https://ollama.ai/install.sh"], 
                         stdout=subprocess.PIPE, check=True)
            subprocess.run(["sh", "-"], input=b"curl -fsSL https://ollama.ai/install.sh", check=True)
            
            # Pull a small model for testing
            subprocess.run(["ollama", "pull", "tinyllama"], check=True)
            print("✅ Ollama installed with TinyLlama model")
            return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install Ollama")
        return False

def create_env_file():
    """Create .env file with development settings"""
    print("📝 Creating .env file...")
    
    env_content = """# Development Environment Configuration
# Database
DATABASE_URL=sqlite+aiosqlite:///./app.db

# Redis
REDIS_URL=redis://localhost:6379/0
ENABLE_CACHE=true

# AI Providers (add your API keys here)
# OPENAI_API_KEY=your_openai_key_here
# HUGGINGFACE_API_KEY=your_huggingface_key_here
# ANTHROPIC_API_KEY=your_anthropic_key_here
# TOGETHER_API_KEY=your_together_key_here
# MOONSHOT_API_KEY=your_moonshot_key_here

# Application Settings
ENVIRONMENT=development
DEBUG=true
ENABLE_METRICS=true
ENABLE_COMPRESSION=true

# Security (for development only)
SECRET_KEY=dev-secret-key-change-in-production
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000

# AI Configuration
AI_DEFAULT_PROVIDER=ollama
MAX_CONCURRENT_AI_REQUESTS=10
AI_REQUEST_TIMEOUT=60

# Logging
LOG_LEVEL=INFO
"""
    
    with open('.env', 'w') as f:
        f.write(env_content)
    
    print("✅ .env file created")

def create_ai_config():
    """Create AI integrations config file"""
    print("🔧 Creating AI configuration...")
    
    config_content = """# AI Integrations Configuration
ollama:
  base_url: "http://localhost:11434"
  model: "tinyllama"
  priority: 90
  timeout: 60
  supports_streaming: true
  is_free: true

huggingface:
  api_key: "${HUGGINGFACE_API_KEY}"
  model: "microsoft/DialoGPT-medium"
  priority: 80
  timeout: 30
  supports_streaming: false
  is_free: true

openai:
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-3.5-turbo"
  priority: 70
  timeout: 30
  cost_per_1k_tokens: 0.002
  supports_streaming: true

together:
  api_key: "${TOGETHER_API_KEY}"
  base_url: "https://api.together.xyz/v1"
  model: "meta-llama/Llama-2-7b-chat-hf"
  priority: 75
  timeout: 30
  cost_per_1k_tokens: 0.0008
  supports_streaming: true

moonshot:
  api_key: "${MOONSHOT_API_KEY}"
  base_url: "https://api.moonshot.cn/v1"
  model: "moonshot-v1-8k"
  priority: 65
  timeout: 30
  cost_per_1k_tokens: 0.012

mock:
  priority: 10
  timeout: 5
  supports_streaming: true
  is_free: true
"""
    
    with open('ai_integrations.yaml', 'w') as f:
        f.write(config_content)
    
    print("✅ AI configuration created")

def test_services():
    """Test that services are working"""
    print("🧪 Testing services...")
    
    # Test Redis
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        print("✅ Redis is working")
    except Exception as e:
        print(f"❌ Redis test failed: {e}")
    
    # Test Ollama
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            print("✅ Ollama is working")
        else:
            print(f"❌ Ollama returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Ollama test failed: {e}")

def install_python_dependencies():
    """Install required Python packages"""
    print("📦 Installing Python dependencies...")
    
    requirements = [
        "fastapi>=0.104.0",
        "uvicorn[standard]>=0.24.0",
        "redis>=5.0.0",
        "aioredis>=2.0.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "sqlalchemy[asyncio]>=2.0.0",
        "aiosqlite>=0.19.0",
        "aiofiles>=23.0.0",
        "aiohttp>=3.9.0",
        "slowapi>=0.1.9",
        "prometheus-client>=0.19.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "requests>=2.31.0"
    ]
    
    try:
        for requirement in requirements:
            subprocess.run([sys.executable, "-m", "pip", "install", requirement], check=True)
        print("✅ Python dependencies installed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Setting up AI Aggregator Development Environment")
    print("=" * 50)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8+ is required")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Install Python dependencies
    if not install_python_dependencies():
        print("⚠️  Some dependencies failed to install, continuing...")
    
    # Create configuration files
    create_env_file()
    create_ai_config()
    
    # Setup services
    redis_ok = False
    if not check_command_exists("redis-server"):
        print("Redis not found, attempting installation...")
        redis_ok = install_redis()
    else:
        print("✅ Redis already installed")
        redis_ok = True
    
    # Setup Ollama
    ollama_ok = False
    if not check_command_exists("ollama"):
        print("Ollama not found, attempting installation...")
        ollama_ok = install_ollama()
    else:
        print("✅ Ollama already installed")
        ollama_ok = True
    
    # Wait a moment for services to start
    if redis_ok or ollama_ok:
        print("⏳ Waiting for services to start...")
        time.sleep(3)
    
    # Test services
    test_services()
    
    print("\n" + "=" * 50)
    print("🎉 Development environment setup complete!")
    print("\nNext steps:")
    print("1. Add your API keys to .env file")
    print("2. Run: python main.py")
    print("3. Visit: http://localhost:8000/docs")
    print("\nFor Ollama models, run: ollama pull <model-name>")
    print("Popular models: tinyllama, llama2, codellama")

if __name__ == "__main__":
    main()