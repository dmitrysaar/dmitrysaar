"""
Автотесты для Bet Manager API.
Покрывают основные позитивные и негативные сценарии.
"""
import os
import sys
import tempfile
import sqlite3
import pytest
from fastapi.testclient import TestClient

# Добавляем корень проекта в sys.path, чтобы импортировать main.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Создаём временную БД ДО импорта main.py,
# чтобы приложение подключилось именно к ней
TEMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
TEMP_DB.close()
os.environ["BET_DB_PATH"] = TEMP_DB.name

# Теперь импортируем приложение — оно увидит BET_DB_PATH
import main
from main import app


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """
    Готовит тестовую БД: применяет schema.sql и наполняет тестовыми данными.
    Выполняется один раз на весь модуль.
    """
    conn = sqlite3.connect(TEMP_DB.name)
    cursor = conn.cursor()

    # Применяем схему из schema.sql
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "schema.sql"
    )
    with open(schema_path, "r", encoding="utf-8") as f:
        cursor.executescript(f.read())

    # Добавляем тестового беттора и матч
    cursor.execute("INSERT INTO bettor (nickname) VALUES (?)", ("TestBettor",))
    cursor.execute("""
        INSERT INTO matches (match_date, tournament, team1, team2)
        VALUES (?, ?, ?, ?)
    """, ("2026-01-15", "Test Cup", "Team A", "Team B"))

    conn.commit()
    conn.close()

    yield  # здесь выполняются все тесты

    # Чистим после тестов
    if os.path.exists(TEMP_DB.name):
        os.unlink(TEMP_DB.name)


@pytest.fixture
def client():
    """FastAPI TestClient — эмулирует HTTP-запросы без запуска сервера."""
    return TestClient(app)


# ============================================
# ТЕСТЫ: MATCHES
# ============================================

def test_get_matches_returns_200(client):
    """GET /matches возвращает 200 и список матчей."""
    response = client.get("/matches")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_match_by_id_not_found(client):
    """GET /matches/{id} с несуществующим ID возвращает 404."""
    response = client.get("/matches/99999")
    assert response.status_code == 404


# ============================================
# ТЕСТЫ: BETS — ВАЛИДАЦИЯ КОЭФФИЦИЕНТА
# ============================================

def _valid_bet_payload(**overrides):
    """Базовый валидный payload для создания ставки."""
    payload = {
        "match_id": 1,
        "bet_type": "Победа Team A",
        "bet_amount": 1000.0,
        "coefficient": 1.95,
        "win_or_loss": 0.0,
        "bettor_id": 3,
    }
    payload.update(overrides)
    return payload


def test_create_bet_with_valid_coefficient(client):
    """POST /bets с coefficient = 1.95 — ставка создаётся (200)."""
    response = client.post("/bets", json=_valid_bet_payload())
    assert response.status_code == 200
    assert "id" in response.json()


@pytest.mark.parametrize("invalid_coefficient", [
    -1,      # отрицательный
    0,       # ноль
    0.99,    # чуть меньше границы
    1.0,     # ровно граница (должна быть отклонена)
])
def test_create_bet_with_invalid_coefficient(client, invalid_coefficient):
    """POST /bets с невалидным coefficient возвращает 400."""
    response = client.post(
        "/bets",
        json=_valid_bet_payload(coefficient=invalid_coefficient)
    )
    assert response.status_code == 400


def test_create_bet_with_nonexistent_match(client):
    """POST /bets с несуществующим match_id возвращает 404."""
    response = client.post(
        "/bets",
        json=_valid_bet_payload(match_id=99999)
    )
    assert response.status_code == 404