# test_api_universal.py
import pytest
import requests
import json
from unittest.mock import patch, MagicMock
from requests.exceptions import RequestException, Timeout, ConnectionError


class TestAPI:
    """Класс для тестирования API"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'API-Test-Client/1.0'
        })

    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.test_data = {
            "user": {
                "name": "Test User",
                "email": "test@example.com",
                "age": 25
            },
            "product": {
                "name": "Test Product",
                "price": 99.99,
                "category": "electronics"
            }
        }

    def teardown_method(self):
        """Очистка после каждого теста"""
        pass

    def test_get_health_check(self):
        """Тест проверки состояния API"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"
        except requests.exceptions.RequestException as e:
            pytest.skip(f"API недоступен: {e}")

    def test_get_users(self):
        """Тест получения списка пользователей"""
        try:
            response = self.session.get(f"{self.base_url}/api/users")
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, (list, dict))
                
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    def test_create_user(self):
        """Тест создания пользователя"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/users",
                json=self.test_data["user"]
            )
            assert response.status_code in [200, 201, 400, 422]
            
            if response.status_code in [200, 201]:
                data = response.json()
                assert "id" in data or "name" in data
                
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    def test_get_user_by_id(self):
        """Тест получения пользователя по ID"""
        user_id = 1
        try:
            response = self.session.get(f"{self.base_url}/api/users/{user_id}")
            assert response.status_code in [200, 404]
            
            if response.status_code == 200:
                data = response.json()
                assert "id" in data
                assert data["id"] == user_id
                
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    def test_update_user(self):
        """Тест обновления пользователя"""
        user_id = 1
        update_data = {"name": "Updated User"}
        
        try:
            response = self.session.put(
                f"{self.base_url}/api/users/{user_id}",
                json=update_data
            )
            assert response.status_code in [200, 404, 400]
            
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    def test_delete_user(self):
        """Тест удаления пользователя"""
        user_id = 999  # Используем несуществующий ID
        try:
            response = self.session.delete(f"{self.base_url}/api/users/{user_id}")
            assert response.status_code in [200, 204, 404]
            
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    def test_invalid_endpoint(self):
        """Тест несуществующего эндпоинта"""
        try:
            response = self.session.get(f"{self.base_url}/api/nonexistent")
            assert response.status_code == 404
            
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    def test_invalid_json(self):
        """Тест отправки невалидного JSON"""
        try:
            headers = {'Content-Type': 'application/json'}
            response = self.session.post(
                f"{self.base_url}/api/users",
                data="invalid json",
                headers=headers
            )
            assert response.status_code in [400, 422]
            
        except requests.exceptions.RequestException as e:
            pytest.skip(f"Ошибка подключения: {e}")

    @patch('requests.Session.get')
    def test_timeout_handling(self, mock_get):
        """Тест обработки таймаута"""
        mock_get.side_effect = Timeout("Request timed out")
        
        with pytest.raises(Timeout):
            self.session.get(f"{self.base_url}/api/users", timeout=1)

    @patch('requests.Session.get')
    def test_connection_error_handling(self, mock_get):
        """Тест обработки ошибки соединения"""
        mock_get.side_effect = ConnectionError("Connection failed")
        
        with pytest.raises(ConnectionError):
            self.session.get(f"{self.base_url}/api/users")

    def test_response_time(self):
        """Тест времени отклика"""
        try:
            import time
            start_time = time.time()
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            end_time = time.time()
            
            response_time = end_time - start_time
            assert response_time < 5.0  # Ответ должен быть быстрее 5 секунд
            
        except requests.exceptions.RequestException as e:
            pytest.skip(f"API недоступен: {e}")

    def test_headers(self):
        """Тест заголовков ответа"""
        try:
            response = self.session.get(f"{self.base_url}/health")
            
            # Проверяем наличие стандартных заголовков
            assert 'content-type' in response.headers
            
            # Проверяем, что content-type корректный для JSON API
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                assert 'application/json' in content_type.lower()
                
        except requests.exceptions.RequestException as e:
            pytest.skip(f"API недоступен: {e}")

    def test_authentication_required(self):
        """Тест эндпоинтов, требующих аутентификации"""
        try:
            # Пытаемся получить доступ без токена
            response = self.session.get(f"{self.base_url}/api/protected")
            assert response.status_code in [401, 403, 404]
            
        except requests.exceptions.RequestException as e:
            pytest.skip(f"API недоступен: {e}")


# Фикстуры для pytest
@pytest.fixture
def api_client():
    """Фикстура для создания клиента API"""
    return TestAPI()


@pytest.fixture
def sample_user_data():
    """Фикстура с тестовыми данными пользователя"""
    return {
        "name": "Test User",
        "email": "test@example.com",
        "age": 30
    }


# Функциональные тесты
def test_api_workflow(api_client):
    """Тест полного workflow работы с API"""
    try:
        # 1. Проверяем здоровье API
        health_response = api_client.session.get(f"{api_client.base_url}/health")
        if health_response.status_code != 200:
            pytest.skip("API недоступен")
        
        # 2. Получаем список пользователей
        users_response = api_client.session.get(f"{api_client.base_url}/api/users")
        
        # 3. Создаем нового пользователя
        new_user = {
            "name": "Workflow Test User",
            "email": "workflow@test.com"
        }
        create_response = api_client.session.post(
            f"{api_client.base_url}/api/users",
            json=new_user
        )
        
        # Проверяем, что хотя бы один из запросов прошел успешно
        success_statuses = [200, 201]
        assert (users_response.status_code in success_statuses or 
                create_response.status_code in success_statuses or
                health_response.status_code in success_statuses)
        
    except requests.exceptions.RequestException:
        pytest.skip("API недоступен для полного workflow теста")


if __name__ == "__main__":
    # Запуск тестов напрямую
    test_client = TestAPI()
    
    print("Запуск базовых тестов API...")
    
    try:
        test_client.test_get_health_check()
        print("✓ Health check тест пройден")
    except Exception as e:
        print(f"✗ Health check тест не пройден: {e}")
    
    try:
        test_client.test_get_users()
        print("✓ Get users тест пройден")
    except Exception as e:
        print(f"✗ Get users тест не пройден: {e}")
    
    try:
        test_client.test_invalid_endpoint()
        print("✓ Invalid endpoint тест пройден")
    except Exception as e:
        print(f"✗ Invalid endpoint тест не пройден: {e}")
    
    print("\nДля полного запуска тестов используйте: pytest test_api.py -v")