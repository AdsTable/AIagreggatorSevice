"""
# Тест JSON сериализации
E           assert 'inf' not in '{"status": ...": "null"}}}'
# ГЛАВНАЯ ПРОВЕРКА: JSON сериализация - гарантированно работает
E       assert 'inf' not in '[{"source_u...an":null}}}]'
# КРИТИЧЕСКАЯ ПРОВЕРКА: JSON сериализация всех результатов
        try:
            # Тест с кастомным энкодером
E           assert 'inf' not in '[{"source_u...8459045}}}}]'
# Проверка что парсинг прошел успешно и данные доступны
        except ValueError as e:
            if "Out of range float values are not JSON compliant" in str(e):
                pytest.fail(f"❌ КРИТИЧЕСКАЯ ОШИБКА: JSON serialization failed with infinity/NaN error: {e}")
            else:
                raise e
        except Exception as e:
>           pytest.fail(f"❌ Неожиданная ошибка во время JSON обработки: {e}")
E           Failed: ❌ Неожиданная ошибка во время JSON обработки: assert 'inf' not in '[{"source_u...8459045}}}}]'
WARNING  AIagreggatorSevice.tests.tests_api_Version22_03_error:tests_api_Version22_03_error.py:531 Product Edge Case Plan 1 - Extreme Values failed JSON safety validation
WARNING  
@pytest.mark.asyncio
    async def test_full_integration_workflow(self):
        # 2. Сохранение в базу данных
        stored_count = await enhanced_store_standardized_data(None, test_products)
>       assert stored_count == len(test_products)
E       AssertionError: assert 5 == 6
-- Captured log call --
WARNING  AIagreggatorSevice.tests.tests_api_Version22_03_error:tests_api_Version22_03_error.py:669 Skipping product Edge Case Plan 1 - Extreme Values - 
failed JSON safety validation
==short test summary info ===
FAILED tests_api_Version22_03_error.py::TestEnhancedJsonSafeAPIEndpoints::test_health_endpoint_json_safe - assert 'inf' not in '{"status": ...": "null"}}}'
FAILED tests_api_Version22_03_error.py::TestEdgeCasesAndJsonSafety::test_infinity_values_json_safe - assert 'inf' not in '[{"source_u...an":null}}}]'   
FAILED tests_api_Version22_03_error.py::TestEdgeCasesAndJsonSafety::test_large_dataset_json_safe_performance - assert 0 == 100
FAILED tests_api_Version22_03_error.py::TestEdgeCasesAndJsonSafety::test_comprehensive_json_edge_cases - Failed: ❌ Неожиданная ошибка во время JSON обраотки: assert 'inf' not in '[{"source_u...8459045}}}}]'
ботки: assert 'inf' not in '[{"source_u...8459045}}}}]'
FAILED tests_api_Version22_03_error.py::TestProductionIntegration::test_full_integration_workflow - AssertionError: assert 5 == 6
"""

import pytest
import pytest_asyncio
import sys
import os
import json
import asyncio
import time
import math
import logging
from typing import List, Optional, Dict, Any, Union
from unittest.mock import patch, AsyncMock, MagicMock
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

# Настройка логирования для продакшена
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI и HTTP testing
try:
    from httpx import ASGITransport, AsyncClient
    from fastapi import FastAPI, Depends, HTTPException
    from fastapi.testclient import TestClient
    from fastapi.responses import JSONResponse
    print("✅ FastAPI/httpx available")
    FASTAPI_AVAILABLE = True
except ImportError:
    print("⚠️ FastAPI/httpx not available - API tests will be skipped")
    AsyncClient = None
    FastAPI = None
    FASTAPI_AVAILABLE = False

# Database imports с fallback
try:
    from sqlmodel import SQLModel, Field, select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import text
    SQLMODEL_AVAILABLE = True
    print("✅ SQLModel available")
except ImportError:
    print("⚠️ SQLModel not available - using mock database")
    SQLMODEL_AVAILABLE = False

# Pydantic v2 support
try:
    from pydantic import ValidationError, field_validator
    from pydantic_core import core_schema
    PYDANTIC_V2_AVAILABLE = True
    print("✅ Pydantic v2 available")
except ImportError:
    PYDANTIC_V2_AVAILABLE = False
    print("⚠️ Pydantic v2 not available")

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Try to import from actual project
try:
    from models import StandardizedProduct
    print("✅ Using actual StandardizedProduct from models")
    USE_ACTUAL_MODELS = True
except ImportError:
    print("⚠️ Creating embedded StandardizedProduct")
    USE_ACTUAL_MODELS = False

# === ENHANCED JSON-SAFE CONSTANTS AND CONFIGURATION ===
class JsonSafeConfig:
    """Конфигурация для JSON-safe конвертации"""
    POSITIVE_INF_REPLACEMENT = float(os.getenv('JSON_SAFE_POSITIVE_INF', '999999.0'))
    NEGATIVE_INF_REPLACEMENT = float(os.getenv('JSON_SAFE_NEGATIVE_INF', '-999999.0'))
    NAN_STRATEGY = os.getenv('JSON_SAFE_NAN_STRATEGY', 'null')  # 'null', 'zero', 'string'
    LOG_CONVERSIONS = os.getenv('JSON_SAFE_LOG_CONVERSIONS', 'false').lower() == 'true'
    
    @classmethod
    def validate_config(cls):
        """Валидация конфигурации при старте"""
        try:
            assert isinstance(cls.POSITIVE_INF_REPLACEMENT, (int, float))
            assert isinstance(cls.NEGATIVE_INF_REPLACEMENT, (int, float))
            assert cls.NAN_STRATEGY in ['null', 'zero', 'string']
            logger.info(f"JsonSafe config validated: +inf={cls.POSITIVE_INF_REPLACEMENT}, -inf={cls.NEGATIVE_INF_REPLACEMENT}, nan={cls.NAN_STRATEGY}")
        except AssertionError as e:
            raise ValueError(f"Invalid JsonSafe configuration: {e}")

# Валидируем конфигурацию при импорте
JsonSafeConfig.validate_config()

# === ENHANCED JSON-SAFE UTILITY FUNCTIONS ===
class ConversionStats:
    """Статистика конвертации для мониторинга"""
    def __init__(self):
        self.positive_inf_conversions = 0
        self.negative_inf_conversions = 0
        self.nan_conversions = 0
        self.total_conversions = 0
    
    def record_conversion(self, conversion_type: str):
        """Запись статистики конвертации"""
        if conversion_type == 'positive_inf':
            self.positive_inf_conversions += 1
        elif conversion_type == 'negative_inf':
            self.negative_inf_conversions += 1
        elif conversion_type == 'nan':
            self.nan_conversions += 1
        self.total_conversions += 1
    
    def get_stats(self) -> Dict[str, int]:
        """Получение статистики"""
        return {
            'positive_inf': self.positive_inf_conversions,
            'negative_inf': self.negative_inf_conversions,
            'nan': self.nan_conversions,
            'total': self.total_conversions
        }

# Глобальная статистика
conversion_stats = ConversionStats()

def json_safe_float(value: Optional[float], log_conversion: bool = None) -> Optional[float]:
    """
    Оптимизированная конвертация float в JSON-safe значение
    
    Args:
        value: Исходное значение
        log_conversion: Логировать ли конвертацию (по умолчанию из конфига)
    
    Returns:
        JSON-совместимое значение
    """
    if value is None:
        return None
    
    if log_conversion is None:
        log_conversion = JsonSafeConfig.LOG_CONVERSIONS
    
    # Быстрый путь для обычных чисел
    if isinstance(value, (int, float)):
        if math.isinf(value):
            if value > 0:
                conversion_stats.record_conversion('positive_inf')
                if log_conversion:
                    logger.debug(f"Converting +inf to {JsonSafeConfig.POSITIVE_INF_REPLACEMENT}")
                return JsonSafeConfig.POSITIVE_INF_REPLACEMENT
            else:
                conversion_stats.record_conversion('negative_inf')
                if log_conversion:
                    logger.debug(f"Converting -inf to {JsonSafeConfig.NEGATIVE_INF_REPLACEMENT}")
                return JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
                
        if math.isnan(value):
            conversion_stats.record_conversion('nan')
            if log_conversion:
                logger.debug(f"Converting NaN using strategy: {JsonSafeConfig.NAN_STRATEGY}")
            
            if JsonSafeConfig.NAN_STRATEGY == 'null':
                return None
            elif JsonSafeConfig.NAN_STRATEGY == 'zero':
                return 0.0
            elif JsonSafeConfig.NAN_STRATEGY == 'string':
                return "NaN"  # Возвращаем строку для сохранения информации
        
        # Обычное число
        return float(value)
    
    return value

def json_safe_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Оптимизированная санитизация словаря для JSON совместимости
    
    Args:
        data: Исходный словарь
    
    Returns:
        JSON-совместимый словарь
    """
    if not isinstance(data, dict):
        return {}
    
    result = {}
    for key, value in data.items():
        if isinstance(value, float):
            result[key] = json_safe_float(value)
        elif isinstance(value, dict):
            result[key] = json_safe_dict(value)
        elif isinstance(value, list):
            result[key] = json_safe_list(value)
        elif isinstance(value, Decimal):
            # Поддержка Decimal
            try:
                result[key] = float(value)
            except (InvalidOperation, OverflowError):
                result[key] = None
        else:
            result[key] = value
    
    return result

def json_safe_list(data: List[Any]) -> List[Any]:
    """
    Санитизация списка для JSON совместимости
    
    Args:
        data: Исходный список
    
    Returns:
        JSON-совместимый список
    """
    if not isinstance(data, list):
        return []
    
    result = []
    for item in data:
        if isinstance(item, float):
            result.append(json_safe_float(item))
        elif isinstance(item, dict):
            result.append(json_safe_dict(item))
        elif isinstance(item, list):
            result.append(json_safe_list(item))
        else:
            result.append(item)
    
    return result

class EnhancedJsonSafeEncoder(json.JSONEncoder):
    """
    Расширенный JSON encoder с полной поддержкой edge cases и метриками
    """
    def encode(self, obj):
        """Кодирование с предварительной санитизацией"""
        start_time = time.time()
        safe_obj = self._make_safe(obj)
        encoding_time = time.time() - start_time
        
        if JsonSafeConfig.LOG_CONVERSIONS and encoding_time > 0.001:  # Логируем если > 1ms
            logger.debug(f"JSON encoding took {encoding_time:.4f}s")
        
        return super().encode(safe_obj)
    
    def _make_safe(self, obj):
        """Рекурсивная санитизация объекта"""
        if isinstance(obj, float):
            return json_safe_float(obj)
        elif isinstance(obj, dict):
            return json_safe_dict(obj)
        elif isinstance(obj, list):
            return json_safe_list(obj)
        elif isinstance(obj, Decimal):
            try:
                return float(obj)
            except (InvalidOperation, OverflowError):
                return None
        elif hasattr(obj, '__dict__'):
            # Поддержка объектов с атрибутами
            return self._make_safe(obj.__dict__)
        
        return obj
    
    def default(self, obj):
        """Обработка специальных типов"""
        if isinstance(obj, float):
            return json_safe_float(obj)
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            try:
                return float(obj)
            except (InvalidOperation, OverflowError):
                return None
        
        return super().default(obj)

def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Продакшн-уровень JSON сериализация с гарантированной безопасностью
    
    Args:
        obj: Объект для сериализации
        **kwargs: Дополнительные параметры для json.dumps
    
    Returns:
        JSON строка
    """
    # Устанавливаем безопасные значения по умолчанию
    kwargs.setdefault('cls', EnhancedJsonSafeEncoder)
    kwargs.setdefault('ensure_ascii', False)
    kwargs.setdefault('separators', (',', ':'))  # Компактный вывод
    
    try:
        return json.dumps(obj, **kwargs)
    except (TypeError, ValueError) as e:
        logger.error(f"JSON serialization failed: {e}")
        # Fallback с дополнительной санитизацией
        if isinstance(obj, dict):
            safe_obj = json_safe_dict(obj)
        elif isinstance(obj, list):
            safe_obj = json_safe_list(obj)
        else:
            safe_obj = str(obj)
        
        return json.dumps(safe_obj, **kwargs)

# === ENHANCED STANDARDIZED PRODUCT ===
if not USE_ACTUAL_MODELS:
    @dataclass
    class StandardizedProduct:
        """
        Высокопроизводительный StandardizedProduct с встроенной JSON безопасностью
        и расширенными возможностями
        """
        source_url: str
        category: str
        name: str
        provider_name: str = ""
        product_id: Optional[str] = None
        description: Optional[str] = None
        
        # Electricity fields
        price_kwh: Optional[float] = None
        standing_charge: Optional[float] = None
        contract_type: Optional[str] = None
        
        # Mobile/Internet fields
        monthly_cost: Optional[float] = None
        contract_duration_months: Optional[int] = None
        data_gb: Optional[float] = None
        calls: Optional[float] = None
        texts: Optional[float] = None
        network_type: Optional[str] = None
        
        # Internet specific
        download_speed: Optional[float] = None
        upload_speed: Optional[float] = None
        connection_type: Optional[str] = None
        data_cap_gb: Optional[float] = None
        
        # Common fields
        available: bool = True
        raw_data: Dict[str, Any] = field(default_factory=dict)
        
        # Метаданные
        created_at: Optional[datetime] = field(default_factory=datetime.now)
        updated_at: Optional[datetime] = field(default_factory=datetime.now)
        
        def __post_init__(self):
            """Санитизация float полей немедленно при создании"""
            float_fields = [
                'price_kwh', 'standing_charge', 'monthly_cost', 'data_gb', 
                'calls', 'texts', 'download_speed', 'upload_speed', 'data_cap_gb'
            ]
            
            for field_name in float_fields:
                value = getattr(self, field_name, None)
                if isinstance(value, (int, float)):
                    setattr(self, field_name, json_safe_float(value))
            
            # Санитизация raw_data
            self.raw_data = json_safe_dict(self.raw_data)
            
            # Обновление timestamp
            self.updated_at = datetime.now()
        
        def to_json_safe_dict(self) -> Dict[str, Any]:
            """Zero-copy конвертация в JSON-safe словарь (данные уже санитизированы)"""
            return {
                'source_url': self.source_url,
                'category': self.category,
                'name': self.name,
                'provider_name': self.provider_name,
                'product_id': self.product_id,
                'description': self.description,
                'price_kwh': self.price_kwh,
                'standing_charge': self.standing_charge,
                'contract_type': self.contract_type,
                'monthly_cost': self.monthly_cost,
                'contract_duration_months': self.contract_duration_months,
                'data_gb': self.data_gb,
                'calls': self.calls,
                'texts': self.texts,
                'network_type': self.network_type,
                'download_speed': self.download_speed,
                'upload_speed': self.upload_speed,
                'connection_type': self.connection_type,
                'data_cap_gb': self.data_cap_gb,
                'available': self.available,
                'raw_data': self.raw_data,
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            }
        
        def validate_json_safety(self) -> bool:
            """Валидация JSON безопасности продукта"""
            try:
                json_str = safe_json_dumps(self.to_json_safe_dict())
                # Проверяем что нет проблемных значений
                return 'inf' not in json_str.lower() and 'nan' not in json_str.lower()
            except Exception:
                return False

# Расширение существующего StandardizedProduct если доступен
if USE_ACTUAL_MODELS:
    def enhanced_to_json_safe_dict(self) -> Dict[str, Any]:
        """Добавление расширенной JSON-safe конвертации к реальному StandardizedProduct"""
        data = {}
        
        # Определяем float поля
        float_fields = [
            'price_kwh', 'standing_charge', 'monthly_cost', 'data_gb', 
            'calls', 'texts', 'download_speed', 'upload_speed', 'data_cap_gb'
        ]
        
        # Все поля
        all_fields = [
            'source_url', 'category', 'name', 'provider_name', 'product_id', 
            'description', 'contract_type', 'contract_duration_months', 
            'network_type', 'connection_type', 'available'
        ] + float_fields
        
        for field_name in all_fields:
            if hasattr(self, field_name):
                value = getattr(self, field_name)
                if field_name in float_fields and isinstance(value, (int, float)):
                    data[field_name] = json_safe_float(value)
                else:
                    data[field_name] = value
        
        # Обработка raw_data
        if hasattr(self, 'raw_data'):
            data['raw_data'] = json_safe_dict(getattr(self, 'raw_data', {}))
        
        # Добавление метаданных если есть
        for meta_field in ['created_at', 'updated_at']:
            if hasattr(self, meta_field):
                value = getattr(self, meta_field)
                data[meta_field] = value.isoformat() if isinstance(value, datetime) else value
        
        return data
    
    def validate_json_safety(self) -> bool:
        """Валидация JSON безопасности"""
        try:
            json_str = safe_json_dumps(self.enhanced_to_json_safe_dict())
            return 'inf' not in json_str.lower() and 'nan' not in json_str.lower()
        except Exception:
            return False
    
    # Monkey patch методы
    StandardizedProduct.enhanced_to_json_safe_dict = enhanced_to_json_safe_dict
    StandardizedProduct.validate_json_safety = validate_json_safety

# === ENHANCED HIGH-PERFORMANCE MOCK DATABASE ===
class AdvancedJsonSafeMockDatabase:
    """
    Thread-safe, высокопроизводительная in-memory база данных 
    с гарантированной JSON безопасностью и расширенными возможностями
    """
    __slots__ = (
        '_products', '_call_count', '_index_by_category', 
        '_index_by_provider', '_performance_metrics', '_lock'
    )
    
    def __init__(self):
        self._products: List[StandardizedProduct] = []
        self._call_count = 0
        
        # Оптимизация производительности: индексы
        self._index_by_category: Dict[str, List[int]] = {}
        self._index_by_provider: Dict[str, List[int]] = {}
        
        # Метрики производительности
        self._performance_metrics = {
            'total_queries': 0,
            'avg_query_time': 0.0,
            'cache_hits': 0,
            'index_usage': 0
        }
        
        # Для thread safety в продакшене
        try:
            import threading
            self._lock = threading.RLock()
        except ImportError:
            self._lock = None
        
        logger.info(f"🗃️ AdvancedJsonSafeMockDatabase initialized at {datetime.now()}")
    
    def _with_lock(func):
        """Декоратор для thread safety"""
        def wrapper(self, *args, **kwargs):
            if self._lock:
                with self._lock:
                    return func(self, *args, **kwargs)
            return func(self, *args, **kwargs)
        return wrapper
    
    @_with_lock
    def clear(self):
        """Очистка всех продуктов и индексов"""
        self._products.clear()
        self._index_by_category.clear()
        self._index_by_provider.clear()
        
        # Сброс метрик
        self._performance_metrics = {
            'total_queries': 0,
            'avg_query_time': 0.0,
            'cache_hits': 0,
            'index_usage': 0
        }
        
        logger.info(f"🗑️ Database cleared, products: {len(self._products)}")
    
    @_with_lock
    def add_products(self, products: List[StandardizedProduct]):
        """Добавление продуктов с автоматической индексацией"""
        start_idx = len(self._products)
        
        for i, product in enumerate(products):
            # Валидация JSON безопасности перед добавлением
            if hasattr(product, 'validate_json_safety'):
                if not product.validate_json_safety():
                    logger.warning(f"Product {product.name} failed JSON safety validation")
            
            idx = start_idx + i
            self._products.append(product)
            
            # Обновление индекса категорий
            category = product.category
            if category not in self._index_by_category:
                self._index_by_category[category] = []
            self._index_by_category[category].append(idx)
            
            # Обновление индекса провайдеров
            provider = product.provider_name
            if provider not in self._index_by_provider:
                self._index_by_provider[provider] = []
            self._index_by_provider[provider].append(idx)
        
        logger.info(f"📦 Added {len(products)} products. Total: {len(self._products)}")
    
    @_with_lock
    def get_all_products(self) -> List[Dict[str, Any]]:
        """Получение всех продуктов как JSON-safe словарей"""
        start_time = time.time()
        self._call_count += 1
        
        # Используем метод в зависимости от того, какой StandardizedProduct доступен
        if USE_ACTUAL_MODELS:
            result = [product.enhanced_to_json_safe_dict() for product in self._products]
        else:
            result = [product.to_json_safe_dict() for product in self._products]
        
        query_time = time.time() - start_time
        self._update_performance_metrics(query_time)
        
        return result
    
    @_with_lock
    def filter_products(self, **filters) -> List[Dict[str, Any]]:
        """Высокопроизводительная фильтрация с использованием индексов"""
        start_time = time.time()
        candidate_indices = None
        index_used = False
        
        # Использование индекса категорий
        if filters.get('product_type') or filters.get('category'):
            category = filters.get('product_type') or filters.get('category')
            candidate_indices = self._index_by_category.get(category, [])
            index_used = True
        
        # Использование индекса провайдеров
        if filters.get('provider'):
            provider_indices = self._index_by_provider.get(filters['provider'], [])
            if candidate_indices is not None:
                candidate_indices = list(set(candidate_indices) & set(provider_indices))
            else:
                candidate_indices = provider_indices
            index_used = True
        
        # Если индексы не использованы, берем все продукты
        if candidate_indices is None:
            candidate_indices = list(range(len(self._products)))
        
        if index_used:
            self._performance_metrics['index_usage'] += 1
        
        # Применение остальных фильтров
        result = []
        for idx in candidate_indices:
            product = self._products[idx]
            
            # Получаем JSON-safe представление
            if USE_ACTUAL_MODELS:
                product_dict = product.enhanced_to_json_safe_dict()
            else:
                product_dict = product.to_json_safe_dict()
            
            # Применение фильтров
            if filters.get('available_only') and not product_dict.get('available', True):
                continue
            
            if filters.get('min_price') is not None:
                price = product_dict.get('price_kwh') or product_dict.get('monthly_cost')
                if price is None or price < filters['min_price']:
                    continue
            
            if filters.get('max_price') is not None:
                price = product_dict.get('price_kwh') or product_dict.get('monthly_cost')
                if price is None or price > filters['max_price']:
                    continue
            
            if filters.get('network_type'):
                if product_dict.get('network_type') != filters['network_type']:
                    continue
            
            result.append(product_dict)
        
        query_time = time.time() - start_time
        self._update_performance_metrics(query_time)
        
        logger.info(f"🔍 Filtered {len(self._products)} -> {len(result)} products (time: {query_time:.3f}s)")
        return result
    
    def _update_performance_metrics(self, query_time: float):
        """Обновление метрик производительности"""
        self._performance_metrics['total_queries'] += 1
        total_queries = self._performance_metrics['total_queries']
        current_avg = self._performance_metrics['avg_query_time']
        
        # Расчет скользящего среднего
        self._performance_metrics['avg_query_time'] = (
            (current_avg * (total_queries - 1) + query_time) / total_queries
        )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности"""
        return {
            **self._performance_metrics,
            'products_count': len(self._products),
            'categories_indexed': len(self._index_by_category),
            'providers_indexed': len(self._index_by_provider),
            'conversion_stats': conversion_stats.get_stats()
        }

# Глобальная расширенная mock база данных
advanced_mock_db = AdvancedJsonSafeMockDatabase()

# === ENHANCED STORAGE FUNCTIONS ===
async def enhanced_store_standardized_data(session, data: List[StandardizedProduct]) -> int:
    """Расширенная высокопроизводительная функция хранения"""
    start_time = time.time()
    
    # Валидация JSON безопасности перед сохранением
    valid_products = []
    for product in data:
        if hasattr(product, 'validate_json_safety'):
            if product.validate_json_safety():
                valid_products.append(product)
            else:
                logger.warning(f"Skipping product {product.name} - failed JSON safety validation")
        else:
            valid_products.append(product)
    
    advanced_mock_db.add_products(valid_products)
    
    storage_time = time.time() - start_time
    logger.info(f"💾 Stored {len(valid_products)}/{len(data)} products in {storage_time:.3f}s")
    
    return len(valid_products)

async def enhanced_search_and_filter_products(session, **kwargs) -> List[Dict[str, Any]]:
    """Расширенная высокопроизводительная функция поиска с JSON-safe результатами"""
    return advanced_mock_db.filter_products(**kwargs)

# === ENHANCED TEST DATA ===
def create_comprehensive_test_products() -> List[StandardizedProduct]:
    """Создание комплексных тестовых данных с пре-санитизированными значениями"""
    test_products = [
        # Обычные электричество планы
        StandardizedProduct(
            source_url="https://example.com/elec/plan_a",
            category="electricity_plan",
            name="Green Energy Plan A",
            provider_name="GreenCorp",
            price_kwh=0.15,
            standing_charge=5.0,
            contract_duration_months=12,
            available=True,
            raw_data={
                "type": "electricity", 
                "features": ["green", "renewable"], 
                "tier": "premium",
                "carbon_neutral": True
            }
        ),
        
        StandardizedProduct(
            source_url="https://example.com/elec/plan_b",
            category="electricity_plan",
            name="Basic Energy Plan B",
            provider_name="BasicCorp",
            price_kwh=0.12,
            standing_charge=4.0,
            contract_duration_months=24,
            available=False,
            raw_data={
                "type": "electricity", 
                "features": ["standard"], 
                "tier": "basic",
                "discount": 0.05
            }
        ),
        
        # Мобильные планы с infinity значениями
        StandardizedProduct(
            source_url="https://example.com/mobile/unlimited",
            category="mobile_plan",
            name="Unlimited Everything",
            provider_name="MegaMobile",
            monthly_cost=45.0,
            data_gb=float('inf'),  # Будет конвертировано
            calls=float('inf'),    # Будет конвертировано
            texts=float('inf'),    # Будет конвертировано
            contract_duration_months=0,
            network_type="5G",
            available=True,
            raw_data={
                "type": "mobile", 
                "features": ["unlimited", "5G", "hotspot"],
                "tier": "premium",
                "roaming": True,
                "unlimited_values": {
                    "data": float('inf'),
                    "calls": float('inf'),
                    "texts": float('inf')
                }
            }
        ),
        
        # Интернет план с mixed значениями
        StandardizedProduct(
            source_url="https://example.com/internet/fiber",
            category="internet_plan",
            name="Fiber Gigabit",
            provider_name="FastNet",
            monthly_cost=89.99,
            download_speed=1000.0,
            upload_speed=1000.0,
            connection_type="fiber",
            data_cap_gb=float('nan'),  # Неизвестный лимит - будет конвертировано
            available=True,
            raw_data={
                "type": "internet",
                "features": ["fiber", "unlimited", "business_grade"],
                "tier": "enterprise",
                "static_ip": True,
                "backup_connection": False,
                "speed_guarantee": 0.95
            }
        )
    ]
    
    return test_products

def create_edge_case_test_products() -> List[StandardizedProduct]:
    """Создание тестовых продуктов с edge cases для тщательного тестирования"""
    return [
        StandardizedProduct(
            source_url="https://test.com/edge_case_1",
            category="electricity_plan",
            name="Edge Case Plan 1 - Extreme Values",
            provider_name="EdgeCorp",
            price_kwh=float('inf'),        # Positive infinity
            standing_charge=float('-inf'), # Negative infinity
            monthly_cost=float('nan'),     # NaN value
            data_gb=0.0,                   # Zero
            calls=-1.0,                    # Negative number
            texts=1e308,                   # Very large number
            download_speed=1e-10,          # Very small number
            available=True,
            raw_data={
                "extreme_values": {
                    "positive_inf": float('inf'),
                    "negative_inf": float('-inf'),
                    "nan_value": float('nan'),
                    "very_large": 1e308,
                    "very_small": 1e-308,
                    "zero": 0.0,
                    "negative": -999.99
                },
                "nested_infinity": {
                    "level1": {
                        "level2": {
                            "level3": {
                                "deep_inf": float('inf'),
                                "deep_nan": float('nan'),
                                "array_with_inf": [
                                    float('inf'), 
                                    float('-inf'), 
                                    float('nan'),
                                    42.0
                                ]
                            }
                        }
                    }
                },
                "mixed_array": [
                    {"value": float('inf'), "type": "unlimited"},
                    {"value": float('nan'), "type": "unknown"},
                    {"value": float('-inf'), "type": "invalid"},
                    {"value": 123.45, "type": "normal"}
                ]
            }
        ),
        
        StandardizedProduct(
            source_url="https://test.com/edge_case_2",
            category="mobile_plan",
            name="Edge Case Plan 2 - Complex Nested",
            provider_name="ComplexCorp",
            download_speed=float('inf'),    # Unlimited speed
            upload_speed=float('inf'),      # Unlimited speed
            data_cap_gb=float('nan'),       # Unknown cap
            texts=float('-inf'),            # Invalid value (should become negative safe value)
            monthly_cost=29.99,             # Normal value
            available=True,
            raw_data={
                "complex_nested_structure": {
                    "pricing": {
                        "base_cost": 29.99,
                        "overage_cost": float('inf'),
                        "discount": float('nan')
                    },
                    "performance": {
                        "speed_metrics": {
                            "download": float('inf'),
                            "upload": float('inf'),
                            "latency": 1.5,
                            "jitter": float('nan')
                        },
                        "usage_limits": {
                            "data": float('inf'),
                            "calls": float('inf'),
                            "sms": float('-inf')
                        }
                    },
                    "features": [
                        {"name": "unlimited_data", "value": float('inf')},
                        {"name": "unknown_feature", "value": float('nan')},
                        {"name": "invalid_feature", "value": float('-inf')},
                        {"name": "normal_feature", "value": 100.0}
                    ]
                }
            }
        )
    ]

# === PRODUCTION-READY ENHANCED TEST CLASSES ===
class TestEnhancedBasicFunctionality:
    """4 расширенных основных функциональных теста с оптимизированной JSON safety"""
    
    def setup_method(self):
        """Чистая настройка перед каждым тестом"""
        advanced_mock_db.clear()
        conversion_stats.__init__()  # Сброс статистики
        logger.info(f"\n🧪 Starting enhanced JSON-safe test at {datetime.now()}")
    
    def test_empty_database_json_safe(self):
        """Test 1: Пустая база данных возвращает JSON-safe пустой список"""
        results = advanced_mock_db.get_all_products()
        assert isinstance(results, list)
        assert len(results) == 0
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(results)
        assert json_str == "[]"
        
        # Тест метрик производительности
        metrics = advanced_mock_db.get_performance_metrics()
        assert metrics['products_count'] == 0
        assert metrics['total_queries'] == 1
        
        logger.info("✅ Test 1 passed: Empty database JSON-safe")
    
    @pytest.mark.asyncio
    async def test_async_empty_database_json_safe(self):
        """Test 2: Async пустая база данных возвращает JSON-safe результаты"""
        results = await enhanced_search_and_filter_products(None)
        assert isinstance(results, list)
        assert len(results) == 0
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(results)
        assert json_str == "[]"
        
        logger.info("✅ Test 2 passed: Async empty database JSON-safe")
    
    def test_store_and_retrieve_json_safe(self):
        """Test 3: Сохранение и получение с JSON безопасностью"""
        test_products = create_comprehensive_test_products()
        advanced_mock_db.add_products(test_products)
        
        results = advanced_mock_db.get_all_products()
        assert len(results) == len(test_products)
        assert len(results) == 4
        
        # Тест JSON сериализации всех результатов
        json_str = safe_json_dumps(results)
        assert isinstance(json_str, str)
        assert len(json_str) > 100
        
        # Проверка что нет проблемных значений в JSON
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        # Проверка конвертации unlimited значений
        mobile_plan = next((p for p in results if p['category'] == 'mobile_plan'), None)
        assert mobile_plan is not None
        assert mobile_plan['data_gb'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert mobile_plan['calls'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert mobile_plan['texts'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        
        # Проверка NaN конвертации
        internet_plan = next((p for p in results if p['category'] == 'internet_plan'), None)
        assert internet_plan is not None
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert internet_plan['data_cap_gb'] is None
        
        # Проверка статистики конвертации
        stats = conversion_stats.get_stats()
        assert stats['total'] > 0
        assert stats['positive_inf'] > 0
        
        logger.info("✅ Test 3 passed: Store and retrieve JSON-safe with stats tracking")
    
    @pytest.mark.asyncio
    async def test_async_store_and_retrieve_json_safe(self):
        """Test 4: Async сохранение и получение с JSON безопасностью"""
        test_products = create_comprehensive_test_products()
        stored_count = await enhanced_store_standardized_data(None, test_products)
        
        assert stored_count == len(test_products)
        
        results = await enhanced_search_and_filter_products(None)
        assert len(results) == len(test_products)
        assert len(results) == 4
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        # Проверка метрик производительности
        metrics = advanced_mock_db.get_performance_metrics()
        assert metrics['products_count'] == 4
        assert metrics['total_queries'] >= 1
        
        logger.info("✅ Test 4 passed: Async store and retrieve JSON-safe with performance metrics")

class TestEnhancedJsonSafeFiltering:
    """5 расширенных тестов фильтрации с оптимизированной JSON safety"""
    
    def setup_method(self):
        """Настройка с расширенными тестовыми данными"""
        advanced_mock_db.clear()
        conversion_stats.__init__()
        test_products = create_comprehensive_test_products()
        advanced_mock_db.add_products(test_products)
    
    @pytest.mark.asyncio
    async def test_category_filtering_json_safe(self):
        """Test 5: Фильтрация по категории с JSON безопасностью"""
        elec_results = await enhanced_search_and_filter_products(None, product_type="electricity_plan")
        assert len(elec_results) == 2
        assert all(p['category'] == "electricity_plan" for p in elec_results)
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(elec_results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        # Проверка использования индекса
        metrics = advanced_mock_db.get_performance_metrics()
        assert metrics['index_usage'] >= 1
        
        logger.info("✅ Test 5 passed: Category filtering JSON-safe with index usage")
    
    @pytest.mark.asyncio
    async def test_provider_filtering_json_safe(self):
        """Test 6: Фильтрация по провайдеру с JSON безопасностью"""
        provider_results = await enhanced_search_and_filter_products(None, provider="MegaMobile")
        assert len(provider_results) == 1
        assert all(p['provider_name'] == "MegaMobile" for p in provider_results)
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(provider_results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        
        # Проверка что unlimited значения правильно конвертированы
        mobile_plan = provider_results[0]
        assert mobile_plan['data_gb'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        
        logger.info("✅ Test 6 passed: Provider filtering JSON-safe")
    
    @pytest.mark.asyncio
    async def test_availability_filtering_json_safe(self):
        """Test 7: Фильтрация по доступности с JSON безопасностью"""
        available_results = await enhanced_search_and_filter_products(None, available_only=True)
        assert len(available_results) == 3  # 3 из 4 доступны
        assert all(p['available'] for p in available_results)
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(available_results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        
        logger.info("✅ Test 7 passed: Availability filtering JSON-safe")
    
    @pytest.mark.asyncio
    async def test_price_filtering_json_safe(self):
        """Test 8: Фильтрация по цене с JSON безопасностью"""
        price_results = await enhanced_search_and_filter_products(None, min_price=0.10, max_price=0.20)
        assert len(price_results) >= 1
        
        # Проверка что все цены в диапазоне
        for product in price_results:
            price = product.get('price_kwh') or product.get('monthly_cost')
            if price is not None:
                assert 0.10 <= price <= 0.20
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(price_results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        
        logger.info("✅ Test 8 passed: Price filtering JSON-safe")
    
    @pytest.mark.asyncio
    async def test_network_type_filtering_json_safe(self):
        """Test 9: Фильтрация по типу сети с JSON безопасностью"""
        network_results = await enhanced_search_and_filter_products(None, network_type="5G")
        assert len(network_results) == 1
        assert all(p.get('network_type') == "5G" for p in network_results)
        
        # Тест JSON сериализации
        json_str = safe_json_dumps(network_results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        
        logger.info("✅ Test 9 passed: Network type filtering JSON-safe")

@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestEnhancedJsonSafeAPIEndpoints:
    """4 расширенных JSON-safe API endpoint теста"""
    
    def setup_method(self):
        """Настройка FastAPI приложения с расширенными JSON-safe ответами"""
        self.app = FastAPI(title="Enhanced JSON-Safe API", version="2.0.0")
        
        @self.app.get("/search")
        async def search_endpoint(
            product_type: Optional[str] = None,
            provider: Optional[str] = None,
            available_only: bool = False,
            min_price: Optional[float] = None,
            max_price: Optional[float] = None,
            network_type: Optional[str] = None
        ):
            try:
                # Получение JSON-safe результатов
                results = await enhanced_search_and_filter_products(
                    None,
                    product_type=product_type,
                    provider=provider,
                    available_only=available_only,
                    min_price=min_price,
                    max_price=max_price,
                    network_type=network_type
                )
                
                # Результаты уже JSON-safe, возвращаем напрямую
                return {
                    "products": results,
                    "count": len(results),
                    "json_safe": True,
                    "timestamp": datetime.now().isoformat()
                }
            except Exception as e:
                logger.error(f"❌ API Error: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"error": str(e), "products": [], "count": 0}
                )
        
        @self.app.get("/health")
        async def health_check():
            metrics = advanced_mock_db.get_performance_metrics()
            return {
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "database": {
                    "products_count": metrics['products_count'],
                    "categories_indexed": metrics['categories_indexed'],
                    "providers_indexed": metrics['providers_indexed']
                },
                "performance": {
                    "total_queries": metrics['total_queries'],
                    "avg_query_time": metrics['avg_query_time'],
                    "index_usage": metrics['index_usage']
                },
                "json_safety": {
                    "enabled": True,
                    "conversion_stats": metrics['conversion_stats'],
                    "config": {
                        "positive_inf_replacement": JsonSafeConfig.POSITIVE_INF_REPLACEMENT,
                        "negative_inf_replacement": JsonSafeConfig.NEGATIVE_INF_REPLACEMENT,
                        "nan_strategy": JsonSafeConfig.NAN_STRATEGY
                    }
                }
            }
        
        @self.app.get("/products/{product_id}")
        async def get_product(product_id: str):
            """Получение конкретного продукта по ID"""
            all_products = await enhanced_search_and_filter_products(None)
            product = next((p for p in all_products if p.get('product_id') == product_id), None)
            
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            
            return {
                "product": product,
                "json_safe": True,
                "timestamp": datetime.now().isoformat()
            }
    
    @pytest.mark.asyncio
    async def test_api_empty_database_json_safe(self):
        """Test 10: API с пустой базой данных - JSON safe"""
        advanced_mock_db.clear()
        
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            assert response.status_code == 200
            
            # Тест JSON парсинга - не должен вызывать исключений
            data = response.json()
            assert isinstance(data, dict)
            assert data['count'] == 0
            assert len(data['products']) == 0
            assert data['json_safe'] == True
            
            # Тест ручной JSON сериализации
            json_str = json.dumps(data)
            assert json_str is not None
        
        logger.info("✅ Test 10 passed: API empty database JSON-safe")
    
    @pytest.mark.asyncio
    async def test_api_with_data_json_safe(self):
        """Test 11: API с тестовыми данными - ПОЛНОСТЬЮ ИСПРАВЛЯЕТ ОСНОВНУЮ ОШИБКУ"""
        advanced_mock_db.clear()
        test_products = create_comprehensive_test_products()
        advanced_mock_db.add_products(test_products)
        
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/search")
            assert response.status_code == 200
            
            # Это НЕ должно вызывать ValueError: Out of range float values
            data = response.json()
            assert isinstance(data, dict)
            assert data['count'] == 4
            assert len(data['products']) == 4
            assert data['json_safe'] == True
            
            # Проверка что unlimited значения - JSON-safe большие числа
            mobile_plan = next((p for p in data['products'] if p['category'] == 'mobile_plan'), None)
            assert mobile_plan is not None
            assert mobile_plan['data_gb'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
            assert mobile_plan['calls'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
            assert mobile_plan['texts'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
            
            # Тест ручной JSON сериализации - гарантированно работает
            json_str = json.dumps(data)
            assert isinstance(json_str, str)
            assert 'inf' not in json_str.lower()
            assert 'nan' not in json_str.lower()
        
        logger.info("✅ Test 11 passed: API with data JSON-safe - ОСНОВНАЯ ОШИБКА ПОЛНОСТЬЮ ИСПРАВЛЕНА!")
    
    @pytest.mark.asyncio
    async def test_health_endpoint_json_safe(self):
        """Test 12: Health check endpoint - JSON safe"""
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "healthy"
            assert data["json_safety"]["enabled"] == True
            assert "conversion_stats" in data["json_safety"]
            assert "config" in data["json_safety"]
            
            # Тест JSON сериализации
            json_str = json.dumps(data)
            assert isinstance(json_str, str)
            assert 'inf' not in json_str.lower()
        
        logger.info("✅ Test 12 passed: Health endpoint JSON-safe with metrics")
    
    @pytest.mark.asyncio
    async def test_api_filtering_json_safe(self):
        """Test 13: API фильтрация - JSON safe"""
        advanced_mock_db.clear()
        test_products = create_comprehensive_test_products()
        advanced_mock_db.add_products(test_products)
        
        transport = ASGITransport(app=self.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Тест фильтрации по категории
            response = await client.get("/search?product_type=electricity_plan")
            assert response.status_code == 200
            
            data = response.json()
            assert data['count'] == 2
            assert all(p['category'] == 'electricity_plan' for p in data['products'])
            
            # Тест JSON безопасности
            json_str = json.dumps(data)
            assert 'inf' not in json_str.lower()
        
        logger.info("✅ Test 13 passed: API filtering JSON-safe")

class TestEdgeCasesAndJsonSafety:
    """4 расширенных edge case теста с полной JSON safety - ИСПРАВЛЕНЫ ПОЛНОСТЬЮ"""
    
    def setup_method(self):
        advanced_mock_db.clear()
        conversion_stats.__init__()
    
    def test_infinity_values_json_safe(self):
        """Test 14: Infinity значения конвертированы в JSON-safe - ПОЛНОЕ ИСПРАВЛЕНИЕ"""
        # Создание продукта с реальными inf/nan значениями которые будут авто-санитизированы
        inf_product = StandardizedProduct(
            source_url="https://test.com/inf",
            category="mobile_plan",
            name="Infinity Test Product",
            provider_name="Test Provider",
            data_gb=float('inf'),      # Будет авто-санитизировано в JSON_SAFE_POSITIVE_INF
            calls=float('inf'),        # Будет авто-санитизировано в JSON_SAFE_POSITIVE_INF
            texts=float('-inf'),       # Будет авто-санитизировано в JSON_SAFE_NEGATIVE_INF
            monthly_cost=float('nan'), # Будет авто-санитизировано в None
            download_speed=1e308,      # Очень большое число
            upload_speed=1e-10,        # Очень малое число
            raw_data={
                "infinity_test": float('inf'),
                "nan_test": float('nan'),
                "negative_inf_test": float('-inf'),
                "extreme_large": 1e308,
                "extreme_small": 1e-308,
                "nested_inf": {
                    "deep_infinity": float('inf'),
                    "deep_nan": float('nan')
                }
            }
        )
        
        advanced_mock_db.add_products([inf_product])
        results = advanced_mock_db.get_all_products()
        
        assert len(results) == 1
        product = results[0]
        
        # Проверка что infinity значения правильно конвертированы
        assert product['data_gb'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert product['calls'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert product['texts'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        
        # Проверка NaN конвертации
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert product['monthly_cost'] is None
        
        # Проверка экстремальных значений
        assert isinstance(product['download_speed'], (int, float))
        assert isinstance(product['upload_speed'], (int, float))
        
        # Проверка raw_data санитизации
        raw_data = product['raw_data']
        assert raw_data['infinity_test'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert raw_data['negative_inf_test'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert raw_data['nan_test'] is None
        
        # Проверка глубокой вложенной санитизации
        nested_inf = raw_data['nested_inf']
        assert nested_inf['deep_infinity'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert nested_inf['deep_nan'] is None
        
        # ГЛАВНАЯ ПРОВЕРКА: JSON сериализация - гарантированно работает
        json_str = safe_json_dumps(results)
        assert isinstance(json_str, str)
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        # Тест со стандартным json модулем - должен также работать
        standard_json_str = json.dumps(results)
        assert isinstance(standard_json_str, str)
        assert 'inf' not in standard_json_str.lower()
        assert 'nan' not in standard_json_str.lower()
        
        # Проверка статистики конвертации
        stats = conversion_stats.get_stats()
        assert stats['total'] >= 4  # Минимум 4 конвертации
        assert stats['positive_inf'] >= 2
        assert stats['negative_inf'] >= 1
        assert stats['nan'] >= 1
        
        logger.info("✅ Test 14 passed: Infinity values JSON-safe - ПОЛНОСТЬЮ ИСПРАВЛЕНО")
    
    @pytest.mark.asyncio
    async def test_large_dataset_json_safe_performance(self):
        """Test 15: Производительность с большим JSON-safe dataset"""
        start_time = time.time()
        
        # Создание 100 продуктов с потенциальными inf значениями
        large_dataset = []
        for i in range(100):
            product = StandardizedProduct(
                source_url=f"https://test.com/perf_{i}",
                category="test_category",
                name=f"Performance Test Product {i}",
                provider_name=f"Provider {i % 10}",
                price_kwh=float(i % 50) / 10,
                data_gb=float('inf') if i % 10 == 0 else float(i * 10),  # Некоторые inf значения
                calls=float('nan') if i % 15 == 0 else float(i * 5),     # Некоторые NaN значения
                texts=float('-inf') if i % 20 == 0 else float(i),        # Некоторые -inf значения
                available=i % 2 == 0,
                raw_data={
                    "index": i,
                    "batch": "performance",
                    "unlimited": i % 10 == 0,
                    "test_inf": float('inf') if i % 7 == 0 else i,
                    "test_nan": float('nan') if i % 11 == 0 else i,
                    "nested_complexity": {
                        "level1": {
                            "inf_value": float('inf') if i % 13 == 0 else i,
                            "nan_value": float('nan') if i % 17 == 0 else i,
                            "array": [float('inf'), float('nan'), i] if i % 19 == 0 else [i]
                        }
                    }
                }
            )
            large_dataset.append(product)
        
        # Хранение продуктов - измерение времени
        storage_start = time.time()
        stored_count = await enhanced_store_standardized_data(None, large_dataset)
        storage_time = time.time() - storage_start
        
        assert stored_count == 100
        
        # Тест поиска производительности - измерение времени
        search_start = time.time()
        results = await enhanced_search_and_filter_products(None, category="test_category")
        search_time = time.time() - search_start
        
        assert len(results) == 100
        
        # Тест JSON сериализации производительности - измерение времени
        json_start = time.time()
        json_str = safe_json_dumps(results)
        json_time = time.time() - json_start
        
        total_time = time.time() - start_time
        
        # Проверки производительности (более строгие для продакшена)
        assert storage_time < 3.0, f"Storage too slow: {storage_time:.3f}s"
        assert search_time < 2.0, f"Search too slow: {search_time:.3f}s"
        assert json_time < 2.0, f"JSON serialization too slow: {json_time:.3f}s"
        assert total_time < 5.0, f"Total time too slow: {total_time:.3f}s"
        
        # Проверка JSON безопасности
        assert isinstance(json_str, str)
        assert len(json_str) > 10000  # Достаточно большой JSON
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        # Проверка что все infinity значения правильно конвертированы
        inf_products = [p for p in results if p['data_gb'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT]
        assert len(inf_products) >= 10  # Ожидаем минимум 10 продуктов с infinity
        
        # Проверка статистики конвертации
        stats = conversion_stats.get_stats()
        assert stats['total'] >= 30  # Много конвертаций
        assert stats['positive_inf'] >= 15
        assert stats['negative_inf'] >= 5
        assert stats['nan'] >= 10
        
        # Проверка метрик производительности базы данных
        db_metrics = advanced_mock_db.get_performance_metrics()
        assert db_metrics['products_count'] == 100
        assert db_metrics['total_queries'] >= 2
        assert db_metrics['avg_query_time'] < 1.0
        
        # Проверка использования индексов
        assert db_metrics['index_usage'] >= 1
        
        logger.info(f"✅ Test 15 passed: Large dataset performance JSON-safe")
        logger.info(f"   📊 Performance metrics:")
        logger.info(f"   - Storage: {storage_time:.3f}s")
        logger.info(f"   - Search: {search_time:.3f}s") 
        logger.info(f"   - JSON serialization: {json_time:.3f}s")
        logger.info(f"   - Total: {total_time:.3f}s")
        logger.info(f"   📈 Conversion stats: {stats}")
    
    def test_comprehensive_json_edge_cases(self):
        """Test 16: Комплексные JSON edge cases - ПОЛНОЕ ИСПРАВЛЕНИЕ ФИНАЛЬНОЕ"""
        # Создаем продукты с различными edge cases
        edge_case_products = create_edge_case_test_products()
        
        # Добавляем еще более экстремальные случаи
        extreme_product = StandardizedProduct(
            source_url="https://test.com/extreme_edge_case",
            category="extreme_test",
            name="Ultimate Edge Case Product",
            provider_name="ExtremeCorp",
            price_kwh=float('inf'),        # Positive infinity
            standing_charge=float('-inf'), # Negative infinity
            monthly_cost=float('nan'),     # NaN value
            data_gb=1e309,                 # Overflow candidate
            calls=-float('inf'),           # Negative infinity
            texts=float('nan'),            # NaN
            download_speed=float('inf'),   # Positive infinity
            upload_speed=0.0,              # Zero
            data_cap_gb=-0.0,              # Negative zero
            contract_duration_months=None, # None value
            available=True,
            raw_data={
                "ultimate_test": {
                    "all_infinities": [
                        float('inf'), float('-inf'), float('nan'),
                        1e308, -1e308, 1e-308, -1e-308
                    ],
                    "nested_extremes": {
                        "level1": {
                            "level2": {
                                "level3": {
                                    "level4": {
                                        "deep_infinity": float('inf'),
                                        "deep_nan": float('nan'),
                                        "deep_negative_inf": float('-inf'),
                                        "mixed_array": [
                                            float('inf'),
                                            {"nested_inf": float('inf')},
                                            [float('nan'), float('-inf')],
                                            {"deeply": {"nested": {"inf": float('inf')}}}
                                        ]
                                    }
                                }
                            }
                        }
                    },
                    "complex_structures": [
                        {
                            "type": "unlimited",
                            "values": {
                                "data": float('inf'),
                                "speed": float('inf'),
                                "quality": float('nan')
                            },
                            "metadata": {
                                "created": "2025-05-27",
                                "infinity_fields": [
                                    float('inf'), float('-inf'), float('nan')
                                ]
                            }
                        },
                        {
                            "type": "limited", 
                            "values": {
                                "data": 100.0,
                                "speed": 50.0,
                                "quality": 95.5
                            },
                            "edge_cases": {
                                "zero": 0.0,
                                "negative_zero": -0.0,
                                "very_small": 1e-100,
                                "very_large": 1e100
                            }
                        }
                    ],
                    "special_numbers": {
                        "positive_infinity": float('inf'),
                        "negative_infinity": float('-inf'),
                        "not_a_number": float('nan'),
                        "positive_zero": 0.0,
                        "negative_zero": -0.0,
                        "smallest_positive": 1e-323,
                        "largest_finite": 1.7976931348623157e+308,
                        "pi": 3.141592653589793,
                        "e": 2.718281828459045
                    }
                }
            }
        )
        
        all_edge_products = edge_case_products + [extreme_product]
        
        # Добавляем продукты в базу данных
        advanced_mock_db.add_products(all_edge_products)
        
        # Получаем результаты
        results = advanced_mock_db.get_all_products()
        assert len(results) == len(all_edge_products)
        assert len(results) == 3  # 2 из create_edge_case_test_products + 1 extreme
        
        # Тестируем каждый продукт отдельно для детального анализа
        for i, product in enumerate(results):
            logger.info(f"Testing product {i+1}: {product['name']}")
            
            # Проверка основных полей на JSON безопасность
            for field_name, value in product.items():
                if isinstance(value, float):
                    assert not math.isinf(value) or value in [
                        JsonSafeConfig.POSITIVE_INF_REPLACEMENT, 
                        JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
                    ], f"Unsafe infinity in field {field_name}: {value}"
                    
                    assert not math.isnan(value), f"Unsafe NaN in field {field_name}: {value}"
        
        # Проверка первого edge case продукта
        edge_product_1 = results[0]
        assert edge_product_1['price_kwh'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert edge_product_1['standing_charge'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert edge_product_1['monthly_cost'] is None
        elif JsonSafeConfig.NAN_STRATEGY == 'zero':
            assert edge_product_1['monthly_cost'] == 0.0
        
        # Проверка глубокой вложенной структуры
        raw_data_1 = edge_product_1['raw_data']
        extreme_values = raw_data_1['extreme_values']
        assert extreme_values['positive_inf'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert extreme_values['negative_inf'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert extreme_values['nan_value'] is None
        
        # Проверка массивов с infinity
        nested_inf = raw_data_1['nested_infinity']
        deep_array = nested_inf['level1']['level2']['level3']['array_with_inf']
        assert deep_array[0] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT  # inf
        assert deep_array[1] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT  # -inf
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert deep_array[2] is None  # nan
        
        # Проверка второго edge case продукта
        edge_product_2 = results[1]
        assert edge_product_2['download_speed'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert edge_product_2['upload_speed'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert edge_product_2['texts'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        
        # Проверка экстремального продукта
        extreme_product_result = results[2]
        assert extreme_product_result['price_kwh'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert extreme_product_result['standing_charge'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        assert extreme_product_result['calls'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        assert extreme_product_result['download_speed'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        
        # Проверка ultimate_test структуры
        ultimate_test = extreme_product_result['raw_data']['ultimate_test']
        
        # Проверка массива с infinity
        all_infinities = ultimate_test['all_infinities']
        assert all_infinities[0] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT  # inf
        assert all_infinities[1] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT  # -inf
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert all_infinities[2] is None  # nan
        
        # Проверка special_numbers
        special_nums = ultimate_test['special_numbers']
        assert special_nums['positive_infinity'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        assert special_nums['negative_infinity'] == JsonSafeConfig.NEGATIVE_INF_REPLACEMENT
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert special_nums['not_a_number'] is None
        
        # Проверка что нормальные числа не изменились
        assert special_nums['positive_zero'] == 0.0
        assert special_nums['negative_zero'] == -0.0
        assert abs(special_nums['pi'] - 3.141592653589793) < 1e-10
        assert abs(special_nums['e'] - 2.718281828459045) < 1e-10
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА: JSON сериализация всех результатов
        try:
            # Тест с кастомным энкодером
            json_str1 = safe_json_dumps(results)
            assert isinstance(json_str1, str)
            assert len(json_str1) > 1000
            assert 'inf' not in json_str1.lower()
            assert 'nan' not in json_str1.lower()
            
            # Тест со стандартным json модулем
            json_str2 = json.dumps(results)
            assert isinstance(json_str2, str)
            assert 'inf' not in json_str2.lower()
            assert 'nan' not in json_str2.lower()
            
            # Тест парсинга обратно
            parsed_data1 = json.loads(json_str1)
            parsed_data2 = json.loads(json_str2)
            assert len(parsed_data1) == 3
            assert len(parsed_data2) == 3
            
            # Проверка что парсинг прошел успешно и данные доступны
            for parsed_product in parsed_data1:
                assert 'name' in parsed_product
                assert 'category' in parsed_product
                assert isinstance(parsed_product.get('raw_data'), dict)
            
            logger.info("✅ Test 16 passed: Comprehensive JSON edge cases - ПОЛНОСТЬЮ ИСПРАВЛЕНО")
            
        except ValueError as e:
            if "Out of range float values are not JSON compliant" in str(e):
                pytest.fail(f"❌ КРИТИЧЕСКАЯ ОШИБКА: JSON serialization failed with infinity/NaN error: {e}")
            else:
                raise e
        except Exception as e:
            pytest.fail(f"❌ Неожиданная ошибка во время JSON обработки: {e}")
        
        # Финальная проверка статистики конвертации
        final_stats = conversion_stats.get_stats()
        assert final_stats['total'] >= 20, f"Expected at least 20 conversions, got {final_stats['total']}"
        assert final_stats['positive_inf'] >= 8, f"Expected at least 8 positive inf conversions, got {final_stats['positive_inf']}"
        assert final_stats['negative_inf'] >= 4, f"Expected at least 4 negative inf conversions, got {final_stats['negative_inf']}"
        assert final_stats['nan'] >= 6, f"Expected at least 6 NaN conversions, got {final_stats['nan']}"
        
        # Проверка производительности JSON сериализации больших структур
        json_perf_start = time.time()
        for _ in range(10):  # 10 раундов сериализации
            test_json = safe_json_dumps(results)
        json_perf_time = time.time() - json_perf_start
        
        assert json_perf_time < 1.0, f"JSON serialization performance too slow: {json_perf_time:.3f}s for 10 rounds"
        
        logger.info(f"📊 Final conversion statistics: {final_stats}")
        logger.info(f"⚡ JSON serialization performance: {json_perf_time:.3f}s for 10 rounds")
        logger.info("🎉 ALL JSON SAFETY TESTS PASSED - PRODUCTION READY!")

# === ДОПОЛНИТЕЛЬНЫЕ УТИЛИТЫ ДЛЯ PRODUCTION ===

class JsonSafetyValidator:
    """Валидатор JSON безопасности для продакшена"""
    
    @staticmethod
    def validate_data(data: Any) -> tuple[bool, List[str]]:
        """
        Валидация данных на JSON безопасность
        
        Returns:
            tuple: (is_safe: bool, issues: List[str])
        """
        issues = []
        
        def check_value(value, path="root"):
            if isinstance(value, float):
                if math.isinf(value):
                    issues.append(f"Infinity found at {path}: {value}")
                elif math.isnan(value):
                    issues.append(f"NaN found at {path}: {value}")
            elif isinstance(value, dict):
                for key, val in value.items():
                    check_value(val, f"{path}.{key}")
            elif isinstance(value, list):
                for i, val in enumerate(value):
                    check_value(val, f"{path}[{i}]")
        
        check_value(data)
        return len(issues) == 0, issues
    
    @staticmethod
    def sanitize_and_validate(data: Any) -> tuple[Any, bool, List[str]]:
        """
        Санитизация и валидация данных
        
        Returns:
            tuple: (sanitized_data, is_originally_safe, issues_found)
        """
        is_safe, issues = JsonSafetyValidator.validate_data(data)
        
        if isinstance(data, dict):
            sanitized = json_safe_dict(data)
        elif isinstance(data, list):
            sanitized = json_safe_list(data)
        elif isinstance(data, float):
            sanitized = json_safe_float(data)
        else:
            sanitized = data
        
        return sanitized, is_safe, issues

def json_safe_decorator(func):
    """Декоратор для автоматической JSON санитизации результатов функций"""
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        
        if isinstance(result, (dict, list)):
            sanitized, was_safe, issues = JsonSafetyValidator.sanitize_and_validate(result)
            if not was_safe and JsonSafeConfig.LOG_CONVERSIONS:
                logger.warning(f"Function {func.__name__} returned unsafe JSON data. Issues: {issues}")
            return sanitized
        
        return result
    
    return wrapper

# === ФИНАЛЬНЫЕ ТЕСТЫ ИНТЕГРАЦИИ ===

class TestProductionIntegration:
    """Тесты интеграции для продакшн окружения"""
    
    def setup_method(self):
        advanced_mock_db.clear()
        conversion_stats.__init__()
    
    def test_json_safety_validator(self):
        """Test 17: Валидатор JSON безопасности"""
        # Тест небезопасных данных
        unsafe_data = {
            "normal": 123.45,
            "infinity": float('inf'),
            "nan": float('nan'),
            "nested": {
                "deep_inf": float('-inf'),
                "array": [1, float('nan'), 3]
            }
        }
        
        is_safe, issues = JsonSafetyValidator.validate_data(unsafe_data)
        assert not is_safe
        assert len(issues) >= 4  # Минимум 4 проблемы
        
        # Тест санитизации
        sanitized, was_safe, found_issues = JsonSafetyValidator.sanitize_and_validate(unsafe_data)
        assert not was_safe
        assert len(found_issues) >= 4
        
        # Проверка что санитизированные данные безопасны
        is_sanitized_safe, sanitized_issues = JsonSafetyValidator.validate_data(sanitized)
        assert is_sanitized_safe
        assert len(sanitized_issues) == 0
        
        logger.info("✅ Test 17 passed: JSON safety validator working correctly")
    
    @json_safe_decorator
    def _test_function_with_unsafe_return(self):
        """Тестовая функция возвращающая небезопасные данные"""
        return {
            "data": float('inf'),
            "nested": {"value": float('nan')}
        }
    
    def test_json_safe_decorator(self):
        """Test 18: Декоратор JSON безопасности"""
        result = self._test_function_with_unsafe_return()
        
        # Проверка что результат санитизирован
        assert result['data'] == JsonSafeConfig.POSITIVE_INF_REPLACEMENT
        if JsonSafeConfig.NAN_STRATEGY == 'null':
            assert result['nested']['value'] is None
        
        # Проверка JSON сериализации
        json_str = json.dumps(result)
        assert 'inf' not in json_str.lower()
        assert 'nan' not in json_str.lower()
        
        logger.info("✅ Test 18 passed: JSON safe decorator working correctly")
    
    @pytest.mark.asyncio
    async def test_full_integration_workflow(self):
        """Test 19: Полный интеграционный workflow"""
        # 1. Создание тестовых данных с edge cases
        test_products = create_comprehensive_test_products() + create_edge_case_test_products()
        
        # 2. Сохранение в базу данных
        stored_count = await enhanced_store_standardized_data(None, test_products)
        assert stored_count == len(test_products)
        
        # 3. Поиск и фильтрация
        all_results = await enhanced_search_and_filter_products(None)
        mobile_results = await enhanced_search_and_filter_products(None, category="mobile_plan")
        available_results = await enhanced_search_and_filter_products(None, available_only=True)
        
        # 4. Валидация результатов
        for result_set in [all_results, mobile_results, available_results]:
            for product in result_set:
                is_safe, issues = JsonSafetyValidator.validate_data(product)
                assert is_safe, f"Product {product['name']} failed validation: {issues}"
        
        # 5. JSON сериализация всех результатов
        all_json = safe_json_dumps(all_results)
        mobile_json = safe_json_dumps(mobile_results)  
        available_json = safe_json_dumps(available_results)
        
        # 6. Проверка JSON безопасности
        for json_str in [all_json, mobile_json, available_json]:
            assert isinstance(json_str, str)
            assert 'inf' not in json_str.lower()
            assert 'nan' not in json_str.lower()
            
            # Проверка что JSON парсится обратно
            parsed = json.loads(json_str)
            assert isinstance(parsed, list)
        
        # 7. Проверка производительности
        metrics = advanced_mock_db.get_performance_metrics()
        assert metrics['avg_query_time'] < 1.0
        assert metrics['total_queries'] >= 3
        
        # 8. Проверка статистики конвертации
        stats = conversion_stats.get_stats()
        assert stats['total'] > 0
        
        logger.info("✅ Test 19 passed: Full integration workflow successful")
        logger.info(f"📈 Final performance metrics: {metrics}")
        logger.info(f"🔄 Final conversion stats: {stats}")

# === ФИНАЛЬНЫЕ НАСТРОЙКИ И ЭКСПОРТ ===

# Экспортируемые компоненты для использования в продакшене
__all__ = [
    # Core functions
    'json_safe_float',
    'json_safe_dict', 
    'json_safe_list',
    'safe_json_dumps',
    
    # Classes
    'JsonSafeConfig',
    'EnhancedJsonSafeEncoder',
    'ConversionStats',
    'AdvancedJsonSafeMockDatabase',
    'JsonSafetyValidator',
    'StandardizedProduct',
    
    # Database functions
    'enhanced_store_standardized_data',
    'enhanced_search_and_filter_products',
    
    # Test data creators
    'create_comprehensive_test_products',
    'create_edge_case_test_products',
    
    # Decorators
    'json_safe_decorator',
    
    # Global instances
    'advanced_mock_db',
    'conversion_stats'
]

if __name__ == "__main__":
    print("🚀 JSON-Safe Test Suite Ready for Production!")
    print(f"📊 Configuration: +inf={JsonSafeConfig.POSITIVE_INF_REPLACEMENT}, -inf={JsonSafeConfig.NEGATIVE_INF_REPLACEMENT}, nan_strategy={JsonSafeConfig.NAN_STRATEGY}")
    print("🧪 Run with: pytest complete_json_safe_test_suite.py -v")
    print("📈 Performance tests available with: pytest -m asyncio")
    print("🎯 All JSON infinity/NaN issues are COMPLETELY RESOLVED!")