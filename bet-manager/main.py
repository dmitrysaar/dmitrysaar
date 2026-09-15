# --- ИМПОРТЫ ---
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import os
import sqlite3
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

# --- ИНИЦИАЛИЗАЦИЯ ---
app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Разрешаем CORS для всех источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК ---
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Преобразуем ошибки в сериализуемый формат
    errors = []
    for error in exc.errors():
        # Создаём копию ошибки без несериализуемых объектов
        error_dict = {
            "type": error.get("type"),
            "loc": error.get("loc"),
            "msg": error.get("msg"),
            "input": error.get("input")
        }
        # Если есть ctx — добавляем только текст ошибки
        if "ctx" in error and "error" in error["ctx"]:
            error_dict["ctx"] = {"error": str(error["ctx"]["error"])}
        errors.append(error_dict)
    
    return JSONResponse(
        status_code=400,
        content={"detail": "Validation error", "errors": errors}
    )

    
# --- ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("BET_DB_PATH", os.path.join(BASE_DIR, "bet_base.db"))

def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn

def parse_number(value):
    """Преобразует строку с запятой в число с плавающей точкой"""
    if isinstance(value, str):
        value = value.replace(',', '.')
    return float(value)

# --- МОДЕЛИ ДЛЯ ОТВЕТОВ ---
class MatchResponse(BaseModel):
    id: int
    match_date: str
    tournament: str
    team1: str
    team2: str
    match_result: Optional[str] = None  # теперь может быть NULL

class BetResponse(BaseModel):
    id: int
    match_id: int
    bet_type: str
    bet_amount: float
    coefficient: float
    win_or_loss: float
    bettor_id: int

class BettorResponse(BaseModel):
    id: int
    nickname: str

# --- МОДЕЛИ ДЛЯ СОЗДАНИЯ ---
from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class MatchCreate(BaseModel):
    match_date: str = Field(..., min_length=8, max_length=10)

    @field_validator('match_date')
    def validate_match_date(cls, value):
        # Проверяем, что value — строка и не пустая
        if not isinstance(value, str) or not value.strip():
            raise ValueError('match_date must be a non-empty string')
        
        # Проверяем формат
        try:
            datetime.strptime(value, '%d.%m.%Y')
        except ValueError:
            raise ValueError('match_date must be a valid date in DD.MM.YYYY format (e.g., 31.12.2026)')
        
        return value

    tournament: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Za-zА-Яа-я0-9\s\-]+$")
    team1: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Za-zА-Яа-я0-9\s\-]+$")
    team2: str = Field(..., min_length=2, max_length=30, pattern=r"^[A-Za-zА-Яа-я0-9\s\-]+$")

#изменения тут
from pydantic import BaseModel, Field, validator
from typing import Optional

class BetCreate(BaseModel):
    match_id: int = Field(..., gt=0)
    
    bet_type: str = Field(
        ...,
        min_length=2,
        max_length=100,
        pattern=r"^[A-Za-zА-Яа-я0-9\s><+\-\.]+$"
    )
    
    bet_amount: float = Field(..., gt=0)
    coefficient: float = Field(..., gt=1.0)
    win_or_loss: float = Field(..., ge=-1000000, le=1000000)
    bettor_id: int = Field(..., gt=0)


class BettorCreate(BaseModel):
    nickname: str = Field(..., min_length=2, max_length=50, pattern=r"^\S.*\S$|^\S$")

# --- МОДЕЛИ ДЛЯ ОБНОВЛЕНИЯ ---
class MatchResultUpdate(BaseModel):
    match_result: str = Field(..., pattern=r"^\d+:\d+$")

class BetResultUpdate(BaseModel):
    win_or_loss: float = Field(..., ge=-1000000, le=1000000)

class BettorUpdate(BaseModel):
    nickname: Optional[str] = Field(None, min_length=2, max_length=50, pattern=r"^\S.*\S$|^\S$")

# ============================================
# ЭНДПОИНТЫ ДЛЯ МАТЧЕЙ
# ============================================

@app.get("/matches", response_model=List[MatchResponse])
def get_matches():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches")
    rows = cursor.fetchall()
    conn.close()
    return [MatchResponse(id=row[0], match_date=row[1], tournament=row[2], team1=row[3], team2=row[4], match_result=row[5]) for row in rows]

@app.get("/matches/{match_id}")
def get_match_by_id(match_id: int):
    if match_id <= 0:
        return JSONResponse(status_code=400, content={"error": "ID must be a positive integer"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM matches WHERE id = ?", (match_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "Match not found"})
    return JSONResponse(status_code=200, content={
        "id": row[0], "match_date": row[1], "tournament": row[2],
        "team1": row[3], "team2": row[4], "match_result": row[5]
    })

@app.post("/matches")
def create_match(match: MatchCreate):
    # Преобразуем дату из ДД.ММ.ГГГГ в ГГГГ-ММ-ДД
    try:
        dt = datetime.strptime(match.match_date, '%d.%m.%Y')
        match_date_sql = dt.strftime('%Y-%m-%d')
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid date format. Use DD.MM.YYYY"}
        )
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO matches (match_date, tournament, team1, team2)
        VALUES (?, ?, ?, ?)
    """, (match_date_sql, match.tournament, match.team1, match.team2))
    
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    return {"message": "Match added successfully", "id": new_id}

@app.patch("/matches/{match_id}")
def update_match_result(match_id: int, update: MatchResultUpdate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM matches WHERE id = ?", (match_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"error": "Match not found"})
    cursor.execute("UPDATE matches SET match_result = ? WHERE id = ?", (update.match_result, match_id))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=200, content={"message": "Match result updated successfully", "id": match_id, "new_result": update.match_result})

@app.delete("/matches/{match_id}")
def delete_match(match_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM matches WHERE id = ?", (match_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"error": "Match not found"})
    cursor.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=200, content={"message": f"Match with ID {match_id} deleted successfully"})

# ============================================
# ЭНДПОИНТЫ ДЛЯ СТАВОК
# ============================================

@app.get("/bets")
def get_all_bets():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets")
    rows = cursor.fetchall()
    conn.close()
    bets = []
    for row in rows:
        bets.append({
            "id": row[0], "match_id": row[1], "bet_type": row[2],
            "bet_amount": parse_number(row[3]), "coefficient": parse_number(row[4]),
            "win_or_loss": parse_number(row[5]), "bettor_id": row[6]
        })
    return bets

@app.get("/bets/{bet_id}")
def get_bet_by_id(bet_id: int):
    if bet_id <= 0:
        return JSONResponse(status_code=400, content={"error": "ID must be a positive integer"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bets WHERE id = ?", (bet_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "Bet not found"})
    return JSONResponse(status_code=200, content={
        "id": row[0], "match_id": row[1], "bet_type": row[2],
        "bet_amount": parse_number(row[3]), "coefficient": parse_number(row[4]),
        "win_or_loss": parse_number(row[5]), "bettor_id": row[6]
    })

@app.post("/bets")
def create_bet(bet: BetCreate):
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем, существует ли матч с таким ID
    cursor.execute("SELECT id FROM matches WHERE id = ?", (bet.match_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(
            status_code=404,
            content={"detail": f"Match with ID {bet.match_id} not found"}
        )
    
    # Если матч существует — вставляем ставку
    cursor.execute("""
        INSERT INTO bets (match_id, bet_type, bet_amount, coefficient, win_or_loss, bettor_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (bet.match_id, bet.bet_type, bet.bet_amount, bet.coefficient, bet.win_or_loss, bet.bettor_id))
    
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    return {"message": "Bet created successfully", "id": new_id}

@app.patch("/bets/{bet_id}")
def update_bet_result(bet_id: int, update: BetResultUpdate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bets WHERE id = ?", (bet_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"error": "Bet not found"})
    cursor.execute("UPDATE bets SET win_or_loss = ? WHERE id = ?", (update.win_or_loss, bet_id))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=200, content={"message": "Bet result updated successfully", "id": bet_id, "new_win_or_loss": update.win_or_loss})

@app.delete("/bets/{bet_id}")
def delete_bet(bet_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bets WHERE id = ?", (bet_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"error": "Bet not found"})
    cursor.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=200, content={"message": f"Bet with ID {bet_id} deleted successfully"})

# ============================================
# ЭНДПОИНТЫ ДЛЯ БЕТТОРОВ
# ============================================

@app.get("/bettor")
def get_all_bettors():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bettor")
    rows = cursor.fetchall()
    conn.close()
    return [{"id": row[0], "nickname": row[1]} for row in rows]

@app.get("/bettor/{bettor_id}")
def get_bettor_by_id(bettor_id: int):
    if bettor_id <= 0:
        return JSONResponse(status_code=400, content={"error": "ID must be a positive integer"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM bettor WHERE id = ?", (bettor_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return JSONResponse(status_code=404, content={"error": "Bettor not found"})
    return JSONResponse(status_code=200, content={"id": row[0], "nickname": row[1]})

@app.post("/bettor")
def create_bettor(bettor: BettorCreate):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bettor (nickname) VALUES (?)", (bettor.nickname,))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return {"message": "Bettor added successfully", "id": new_id}

@app.patch("/bettor/{bettor_id}")
def update_bettor(bettor_id: int, update: BettorUpdate):
    if bettor_id <= 0:
        return JSONResponse(status_code=400, content={"error": "ID must be a positive integer"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bettor WHERE id = ?", (bettor_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"error": "Bettor not found"})
    if update.nickname is not None:
        cursor.execute("UPDATE bettor SET nickname = ? WHERE id = ?", (update.nickname, bettor_id))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=200, content={"message": "Bettor updated successfully", "id": bettor_id})

@app.delete("/bettor/{bettor_id}")
def delete_bettor(bettor_id: int):
    if bettor_id <= 0:
        return JSONResponse(status_code=400, content={"error": "ID must be a positive integer"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bettor WHERE id = ?", (bettor_id,))
    if cursor.fetchone() is None:
        conn.close()
        return JSONResponse(status_code=404, content={"error": "Bettor not found"})
    cursor.execute("DELETE FROM bettor WHERE id = ?", (bettor_id,))
    conn.commit()
    conn.close()
    return JSONResponse(status_code=200, content={"message": f"Bettor with ID {bettor_id} deleted successfully"})

# ============================================
# ДОПОЛНИТЕЛЬНЫЕ ЭНДПОИНТЫ
# ============================================

@app.get("/tournaments")
def get_tournaments():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT tournament FROM matches WHERE tournament != 'ЧМ2026' ORDER BY tournament")
    rows = cursor.fetchall()
    conn.close()
    return {"tournaments": [row[0] for row in rows]}

@app.get("/teams")
def get_teams():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT team1 AS team FROM matches
        UNION
        SELECT DISTINCT team2 FROM matches
        ORDER BY team
    """)
    rows = cursor.fetchall()
    conn.close()
    return {"teams": [row[0] for row in rows if row[0] is not None and row[0] != ""]}
#эндпоинт для расчёта результата по периоду
from datetime import datetime

@app.get("/profit")
def get_profit(nickname: str, date_from: str, date_to: str):
    # Преобразуем даты из ДД.ММ.ГГГГ в ГГГГ-ММ-ДД
    def convert_date(d: str) -> str:
        try:
            dt = datetime.strptime(d, '%d.%m.%Y')
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            return None
    
    date_from_sql = convert_date(date_from)
    date_to_sql = convert_date(date_to)
    
    if date_from_sql is None or date_to_sql is None:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid date format. Use DD.MM.YYYY"}
        )
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT SUM(b.win_or_loss) AS total_profit
        FROM bets b
        JOIN matches m ON b.match_id = m.id
        JOIN bettor btr ON b.bettor_id = btr.id
        WHERE btr.nickname = ?
          AND m.match_date BETWEEN ? AND ?
    """, (nickname, date_from_sql, date_to_sql))
    
    result = cursor.fetchone()
    conn.close()
    
    total = result[0] if result and result[0] is not None else 0
    
    return {
        "nickname": nickname,
        "date_from": date_from,
        "date_to": date_to,
        "profit": total
    }

# ============================================
# ЗАПУСК (для локального тестирования)
# ============================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)