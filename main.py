from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, List, Optional
from contextlib import asynccontextmanager
import httpx, os, json, asyncio, aiosqlite, uuid, jwt
from datetime import date
from dotenv import load_dotenv
from google import genai
from google.genai import types
import uvicorn

load_dotenv(override=True)

DB_FILE = "teamsync.db"

# ── Schema ─────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS teams (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id         TEXT NOT NULL,
                team_id    TEXT NOT NULL,
                title      TEXT NOT NULL,
                tag        TEXT DEFAULT 'general',
                assignee   TEXT,
                status     TEXT DEFAULT 'todo',
                deadline   TEXT,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (id, team_id)
            );
            CREATE TABLE IF NOT EXISTS members (
                id         TEXT PRIMARY KEY,
                team_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                role       TEXT NOT NULL,
                joined_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(team_id, name)
            );
            CREATE TABLE IF NOT EXISTS failure_patterns (
                id            TEXT PRIMARY KEY,
                team_id       TEXT NOT NULL,
                assignee      TEXT NOT NULL,
                tag           TEXT NOT NULL,
                failure_count INTEGER DEFAULT 1,
                last_seen     TEXT DEFAULT (datetime('now')),
                UNIQUE(team_id, assignee, tag)
            );
        """)
        await db.commit()
    print("✅ SQLite ready - Student Edition")
    yield

app = FastAPI(title="TeamSync AI - Student Edition", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── Clients ────────────────────────────────────
gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
HINDSIGHT_HEADERS = {
    "Authorization": f'Bearer {os.getenv("HINDSIGHT_API_KEY")}',
    "Content-Type": "application/json",
}
PROJECT_ID = os.getenv("HINDSIGHT_PROJECT_ID")
JWT_SECRET  = os.getenv("JWT_SECRET", "teamsync-2026")

# ── WebSocket manager ──────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, List[WebSocket]] = {}

    async def connect(self, ws: WebSocket, team_id: str):
        await ws.accept()
        self.active.setdefault(team_id, []).append(ws)

    def disconnect(self, ws: WebSocket, team_id: str):
        try:
            self.active.get(team_id, []).remove(ws)
        except ValueError:
            pass

    async def broadcast(self, team_id: str, payload: dict):
        dead = []
        for ws in self.active.get(team_id, []):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, team_id)

    def online_count(self, team_id: str) -> int:
        return len(self.active.get(team_id, []))

manager = ConnectionManager()

# ── STUDENT DEMO SEED DATA ──────────────────────────────
DEFAULT_TASKS = [
    ("TSK-101", "Write Literature Review", "research", "Sarah", "done", "2026-03-15"),
    ("TSK-102", "Setup Node.js Backend", "backend", "Alex", "inProgress", "2026-03-21"),
    ("TSK-103", "Design Figma Mockups", "design", "Priya", "todo", "2026-03-22"),
    ("TSK-104", "Final Presentation Deck", "presentation", "Unassigned", "todo", "2026-03-24"),
    ("TSK-105", "Record Demo Video", "media", "Unassigned", "todo", "2026-03-25"),
]

DEFAULT_MEMBERS = [
    ("Sarah", "Team Lead"),
    ("Alex", "Backend Dev"),
    ("Priya", "UI/UX Designer"),
    ("Chad", "Researcher"),
    ("Ananya", "Frontend Dev")
]

# Pydantic Models
class AuthRequest(BaseModel): team_code: str; user_name: str; user_role: str
class ChatRequest(BaseModel): message: str; team_id: str; session_id: str = ""; use_memory: bool; current_user: str = "User"; current_role: str = ""
class ReassignRequest(BaseModel): task_id: str; new_assignee: str; team_id: str; session_id: str = ""
class ReflectRequest(BaseModel): team_id: str; session_id: str = ""
class CreateTaskRequest(BaseModel): title: str; assignee: str; tag: str; team_id: str; deadline: str = ""
class MeetingRequest(BaseModel): notes: str; team_id: str; session_id: str = ""

# ── DB helpers ─────────────────────────────────
async def get_or_create_team(team_code: str) -> str:
    code = team_code.upper().strip()
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT id FROM teams WHERE code=?", (code,))
        if rows:
            return rows[0]["id"]
        
        team_id = str(uuid.uuid4())
        await db.execute("INSERT INTO teams (id,name,code) VALUES (?,?,?)", (team_id, f"Project {code}", code))
        
        # Insert Default Tasks
        for t in DEFAULT_TASKS:
            await db.execute(
                "INSERT OR IGNORE INTO tasks (id,team_id,title,tag,assignee,status,deadline) VALUES (?,?,?,?,?,?,?)",
                (t[0], team_id, t[1], t[2], t[3], t[4], t[5])
            )
        
        # Insert Default Team Members so the sidebar is populated immediately
        for m in DEFAULT_MEMBERS:
            await db.execute(
                "INSERT OR IGNORE INTO members (id, team_id, name, role) VALUES (?,?,?,?)",
                (str(uuid.uuid4()), team_id, m[0], m[1])
            )
        
        # DEMO MAGIC: Pre-load Chad's failure so the intervention card works perfectly
        await db.execute("""
            INSERT OR IGNORE INTO failure_patterns (id, team_id, assignee, tag, failure_count, last_seen)
            VALUES (?, ?, ?, ?, 3, datetime('now'))
        """, (str(uuid.uuid4()), team_id, "chad", "presentation"))
        
        await db.commit()
        return team_id

async def upsert_member(team_id: str, name: str, role: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO members (id,team_id,name,role) VALUES (?,?,?,?) "
            "ON CONFLICT(team_id,name) DO UPDATE SET role=excluded.role, joined_at=datetime('now')",
            (str(uuid.uuid4()), team_id, name, role)
        )
        await db.commit()

async def get_members(team_id: str) -> list:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT name, role, joined_at FROM members WHERE team_id=? ORDER BY joined_at ASC", (team_id,))
    return [dict(r) for r in rows]

async def get_board(team_id: str) -> dict:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT id,title,tag,assignee,status,deadline FROM tasks WHERE team_id=? ORDER BY rowid ASC", (team_id,))
    board: dict = {"todo": [], "inProgress": [], "done": []}
    for r in rows:
        board[r["status"]].append(dict(r))
    return board

# ── Hindsight & Failures ──────────────────────────
async def retain_memory(team_id: str, text: str, event_type: str = "general"):
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.hindsight.vectorize.io/v1/default/banks/{PROJECT_ID}/memories"
            await client.post(url, headers=HINDSIGHT_HEADERS, json={"items": [{"content": f"[Team {team_id}] [{event_type.upper()}] {text}"}]})
        except Exception as e:
            print(f"Hindsight retain error: {e}")

async def recall_memory(team_id: str, query: str) -> tuple[str, int]:
    async with httpx.AsyncClient() as client:
        try:
            url = f"https://api.hindsight.vectorize.io/v1/default/banks/{PROJECT_ID}/memories/recall"
            resp = await client.post(url, headers=HINDSIGHT_HEADERS, json={"query": f"[Team {team_id}] {query}", "budget": "high"})
            results = resp.json().get("results", resp.json().get("items", []))
            seen, deduped = set(), []
            for m in results:
                text = m.get("text", "").replace(f"[Team {team_id}]", "").strip()
                if text and text not in seen:
                    seen.add(text)
                    deduped.append(text)
            return " | ".join(deduped[:12]), len(deduped)
        except Exception as e:
            return "", 0

async def get_failure_count(team_id: str, assignee: str, tag: str) -> int:
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT failure_count FROM failure_patterns WHERE team_id=? AND assignee=? AND tag=?", 
            (team_id, assignee.lower(), tag.lower())
        )
        return rows[0]["failure_count"] if rows else 0

async def record_failure(team_id: str, assignee: str, tag: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            INSERT INTO failure_patterns (id, team_id, assignee, tag, failure_count, last_seen)
            VALUES (?, ?, ?, ?, 1, datetime('now'))
            ON CONFLICT(team_id, assignee, tag) DO UPDATE SET failure_count = failure_count + 1, last_seen = datetime('now')
        """, (str(uuid.uuid4()), team_id, assignee.lower(), tag.lower()))
        await db.commit()

async def ask_gemini(system: str, user: str, json_mode: bool = False) -> str:
    cfg_kwargs = {"system_instruction": system, "temperature": 0.4}
    if json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"
    resp = gemini.models.generate_content(
        model="gemini-2.5-flash", 
        contents=user, 
        config=types.GenerateContentConfig(**cfg_kwargs)
    )
    return resp.text.strip()

# ── Routes ─────────────────────────────────────
@app.get("/")
async def serve_frontend():
    return FileResponse("index.html")

@app.post("/api/auth/join")
async def join_team(req: AuthRequest):
    team_id = await get_or_create_team(req.team_code)
    await upsert_member(team_id, req.user_name, req.user_role)
    token = jwt.encode({"team_id": team_id, "user": req.user_name, "role": req.user_role, "team_code": req.team_code.upper()}, JWT_SECRET, algorithm="HS256")
    members = await get_members(team_id)
    await manager.broadcast(team_id, {"type": "members_update", "members": members})
    return {"token": token, "team_id": team_id, "team_code": req.team_code.upper()}

@app.get("/api/members/{team_id}")
async def get_team_members(team_id: str):
    return {"members": await get_members(team_id)}

@app.websocket("/ws/{team_id}")
async def websocket_endpoint(ws: WebSocket, team_id: str):
    await manager.connect(ws, team_id)
    await manager.broadcast(team_id, {"type": "presence", "online": manager.online_count(team_id)})
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                try:
                    await ws.send_json({"type": "ping"})
                except:
                    break
            except:
                break
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws, team_id)
        await manager.broadcast(team_id, {"type": "presence", "online": manager.online_count(team_id)})

@app.get("/api/board")
async def api_get_board(team_id: str):
    return await get_board(team_id)

@app.get("/api/memory/startup/{team_id}")
async def startup_memory(team_id: str, user_name: str = "User", user_role: str = ""):
    if user_name == "User" and not user_role:
        return {"memory_count": 0, "welcome": ""}
    try:
        memory_context, memory_count = await recall_memory(team_id, "group project grades free riders deadlines procrastination")
        board = await get_board(team_id)
        
        system = (
            f"You are TeamSync AI, a brutally honest group project manager for university students. "
            f"Greet {user_name} ({user_role}). Give a 2-sentence status of the CS Final Project. "
            f"Mention any major red flags from historical memory. Remind them grades are on the line."
        )
        context = f"Board: {len(board['todo'])} ToDo, {len(board['inProgress'])} Active. History: {memory_context}"
        result = await ask_gemini(system=system, user=context)
        return {"memory_count": memory_count, "welcome": result}
    except Exception as e:
        return {"memory_count": 0, "welcome": f"Welcome, {user_name}! Let's get this project done."}

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        if request.use_memory:
            memory_context, _ = await recall_memory(request.team_id, request.message)
        else:
            memory_context, _ = ("", 0)
            
        board = await get_board(request.team_id)
        
        system = f"""You are TeamSync AI, a brutally honest AI Group Project Manager.
CURRENT USER: {request.current_user} | Role: {request.current_role}
FULL BOARD: {json.dumps(board)}

PAST PROJECT PATTERNS (HINDSIGHT):
{memory_context}
"""
        # Inject deterministic failure data
        all_assignees = list({t["assignee"] for col in board.values() for t in col})
        all_tags = ["backend", "frontend", "design", "presentation", "research", "media"]
        failure_lines = []
        
        # Explicitly check Chad for the demo, plus anyone else on the board
        for a in all_assignees + ["chad", "Chad"]:
            for tg in all_tags:
                count = await get_failure_count(request.team_id, a, tg)
                if count > 0:
                    failure_lines.append(f"  - {a} has GHOSTED/FAILED {tg} tasks {count} times.")
        
        if failure_lines:
            system += "\nCONFIRMED FAILURE RECORDS (DO NOT ASSIGN THESE):\n" + "\n".join(failure_lines)
            system += "\nIf user tries to assign a matching task type to a failing user, you MUST return an 'intervention' action_card to protect the team's grade.\n"

        system += """
Respond ONLY in valid JSON:
{"reply":"your response","extracted_fact":"project fact or NONE","action_card":null}

For REASSIGNMENT: 
{"reply":"...","extracted_fact":"...","action_card":{"type":"reassign","task_id":"TSK-XXX","task_title":"...","from_assignee":"...","to_assignee":"..."}}

For CREATION: 
{"reply":"...","extracted_fact":"...","action_card":{"type":"create","task_title":"...","assignee":"...","tag":"backend|design|presentation","deadline":""}}

For INTERVENTION (Stop a bad assignment to a free-rider): 
{"reply":"...","extracted_fact":"...","action_card":{"type":"intervention","warning":"[Name] has ghosted past tasks.","recommendation":"Assign to [Better Person] instead to save your grade.","suggested_assignee":"[Better Person]","task_title":"[exact title]","tag":"[tag]"}}
"""
        result = await ask_gemini(system=system, user=request.message, json_mode=True)
        data = json.loads(result)
        
        if data.get("extracted_fact", "NONE") != "NONE":
            asyncio.create_task(retain_memory(request.team_id, data["extracted_fact"], "decision"))
            
        return {"reply": data.get("reply", ""), "memories_used": bool(memory_context), "action_card": data.get("action_card")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/create")
async def create_task(request: CreateTaskRequest):
    task_id = f"TSK-{uuid.uuid4().hex[:3].upper()}"
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO tasks (id,team_id,title,tag,assignee,status,deadline) VALUES (?,?,?,?,?,?,?)",
            (task_id, request.team_id, request.title, request.tag, request.assignee, "todo", request.deadline or None)
        )
        await db.commit()
        
    await retain_memory(request.team_id, f"TASK CREATED: {task_id} — '{request.title}' assigned to {request.assignee}", "decision")
    
    board = await get_board(request.team_id)
    await manager.broadcast(request.team_id, {"type": "board_update", "board": board, "message": f"Task {task_id} created for {request.assignee}"})
    return {"success": True, "task_id": task_id}

@app.post("/api/tasks/reassign")
async def reassign_task(request: ReassignRequest):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE tasks SET assignee=?,updated_at=datetime('now') WHERE id=? AND team_id=?", 
            (request.new_assignee, request.task_id, request.team_id)
        )
        await db.commit()
        
    await retain_memory(request.team_id, f"Task {request.task_id} reassigned to {request.new_assignee}", "reassignment")
    
    board = await get_board(request.team_id)
    await manager.broadcast(request.team_id, {"type": "board_update", "board": board, "message": f"{request.task_id} reassigned to {request.new_assignee}"})
    return {"success": True}

@app.post("/api/tasks/mark_failed")
async def mark_task_failed(task_id: str, team_id: str):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT assignee, tag, title FROM tasks WHERE id=? AND team_id=?", (task_id, team_id))
        if not rows:
            raise HTTPException(status_code=404, detail="Task not found")
        assignee, tag, title = rows[0]["assignee"], rows[0]["tag"], rows[0]["title"]
        
    await record_failure(team_id, assignee, tag)
    await retain_memory(team_id, f"FREE-RIDER RECORDED: {assignee} failed/ghosted {tag} task {task_id}. Do NOT assign {tag} tasks to {assignee}.", "failure")
    return {"success": True, "message": f"Recorded: {assignee} ghosted on {tag}"}

# ── NEW: PANIC MODE / TRIAGE ─────────────────────
@app.get("/api/project/panic/{team_id}")
async def panic_mode(team_id: str):
    history, _ = await recall_memory(team_id, "capacity deadlines overload speed free riders failures")
    board = await get_board(team_id)
    system = """You are TeamSync AI in PANIC MODE. The deadline is tomorrow. 
Look at the board and the team's history. 
Suggest ONE feature to completely cut/drop to save the project. Reassign tasks from slow people to reliable people. 
Be brutal. Grades are on the line. Output valid JSON: {"reply":"brutal text response","action_card":{"type":"reassign","task_id":"...","task_title":"...","from_assignee":"...","to_assignee":"..."}}"""
    try:
        result = await ask_gemini(system=system, user=f"Board: {json.dumps(board)}\nHistory: {history}", json_mode=True)
        data = json.loads(result)
        return {"reply": data.get("reply"), "action_card": data.get("action_card")}
    except Exception as e:
        return {"reply": "Panic mode failed to compute. Just start coding.", "action_card": None}

@app.post("/api/meeting/summary")
async def meeting_summary(request: MeetingRequest):
    try:
        result = await ask_gemini(
            system=(
                "Extract grading rules, professor requirements, decisions, and action items from these notes. "
                'Respond ONLY in valid JSON: {"summary":"...","decisions":["..."],'
                '"action_items":[{"task":"...","owner":"..."}],"blockers":["..."],"capacity_concerns":["..."]}'
            ),
            user=request.notes, json_mode=True
        )
        data  = json.loads(result)
        tasks = []
        for d in data.get("decisions", []):
            tasks.append(retain_memory(request.team_id, f"REQUIREMENT: {d}", "meeting"))
        for item in data.get("action_items", []):
            tasks.append(retain_memory(request.team_id, f"ACTION ITEM: {item.get('task','')} -> {item.get('owner','TBD')}", "meeting"))
        for b in data.get("blockers", []):
            tasks.append(retain_memory(request.team_id, f"BLOCKER: {b}", "blocker"))
        for c in data.get("capacity_concerns", []):
            tasks.append(retain_memory(request.team_id, f"CAPACITY CONCERN: {c}", "capacity"))
        
        await asyncio.gather(*tasks)
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/suggest/{team_id}")
async def suggest_tasks(team_id: str, user_name: str = "User", user_role: str = ""):
    if user_name == "User" and not user_role:
        return {"has_alert": False, "alert": "", "severity": "info", "pattern_detected": False}
    try:
        history, _ = await recall_memory(team_id, "overload capacity delays reassignment patterns blockers deadlines")
        board   = await get_board(team_id)
        members = await get_members(team_id)
        current_assignees = list({t["assignee"] for col in board.values() for t in col})
        
        result = await ask_gemini(
            system=(
                f"You are a PREDICTIVE AI. User: {user_name} ({user_role}). "
                f"Respond ONLY in valid JSON: "
                + '{"has_alert":true,"alert":"one specific sentence with real task IDs","severity":"warning|critical|info","pattern_detected":true}'
                + " If no genuine risk exists on the CURRENT board, set has_alert to false."
            ),
            user=f"HISTORY:\n{history or 'No history yet.'}\n\nCURRENT BOARD:\n{json.dumps(board, indent=2)}\n\nREGISTERED TEAM MEMBERS:\n{json.dumps(members)}",
            json_mode=True
        )
        return json.loads(result)
    except Exception as e:
        return {"has_alert": False, "alert": "", "severity": "info", "pattern_detected": False}

@app.get("/api/tasks/deadlines/{team_id}")
async def check_deadlines(team_id: str):
    board, today, alerts = await get_board(team_id), date.today(), []
    for col in ["todo", "inProgress"]:
        for task in board.get(col, []):
            dl = task.get("deadline")
            if not dl: continue
            diff = (date.fromisoformat(dl) - today).days
            if diff < 0:
                alerts.append({"task_id": task["id"], "severity": "critical", "message": f"{task['id']} — '{task['title']}' ({task['assignee']}) is {abs(diff)}d OVERDUE!"})
            elif diff == 0:
                alerts.append({"task_id": task["id"], "severity": "critical", "message": f"{task['id']} — '{task['title']}' ({task['assignee']}) is due TODAY."})
            elif diff <= 2:
                alerts.append({"task_id": task["id"], "severity": "warning", "message": f"{task['id']} — '{task['title']}' ({task['assignee']}) due in {diff}d."})
    if any(a["severity"] == "critical" for a in alerts):
        ids = [a["task_id"] for a in alerts if a["severity"] == "critical"]
        asyncio.create_task(retain_memory(team_id, f"DEADLINE ALERT {today.isoformat()}: {', '.join(ids)}", "deadline"))
    return {"alerts": alerts, "count": len(alerts)}

@app.get("/api/sprint/velocity/{team_id}")
async def sprint_velocity(team_id: str):
    history, count = await recall_memory(team_id, "reassignment overloaded delayed velocity patterns blockers")
    if not history or count < 2:
        return {"insights": [], "has_data": False, "memory_count": count, "summary": "Not enough project history yet."}
    try:
        result = await ask_gemini(
            system=(
                "Analyze this student team's history. Respond ONLY in valid JSON: "
                '{"insights":[{"type":"overload|delay|blocker|improvement|recommendation","description":"specific insight","person":"name or null","confidence":"high|medium|low"}],'
                '"summary":"2-sentence health summary","next_sprint_recommendation":"one concrete action"}'
            ),
            user=history, json_mode=True
        )
        data = json.loads(result)
        data["has_data"] = True
        data["memory_count"] = count
        return data
    except Exception as e:
        return {"insights": [], "has_data": False, "memory_count": count, "summary": str(e)}

@app.get("/api/memory/graph/{team_id}")
async def get_memory_graph(team_id: str):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.hindsight.vectorize.io/v1/default/banks/{PROJECT_ID}/memories/recall",
                headers=HINDSIGHT_HEADERS, json={"query": f"[Team {team_id}]", "budget": "high"}
            )
            results = resp.json().get("results", resp.json().get("items", []))
            
        if not results:
            return {"nodes": [{"id": 0, "label": "Team Memory", "group": "core", "title": "No memories yet"}], "edges": []}
            
        nodes = [{"id": 0, "label": "Project Memory", "group": "core", "title": "All accumulated decisions"}]
        edges, seen = [], set()
        
        for memory in reversed(results):
            text = memory.get("text", "").replace(f"[Team {team_id}]", "").strip()
            if not text or text in seen: continue
            seen.add(text)
            
            nid = len(nodes)
            u = text.upper()
            
            if "[MEETING]" in u or "REQUIREMENT" in u: group = "meeting"
            elif "[REASSIGNMENT]" in u: group = "reassignment"
            elif "[BLOCKER]" in u: group = "blocker"
            elif "[CAPACITY]" in u: group = "capacity"
            elif "[DEADLINE]" in u: group = "deadline"
            elif "DECISION" in u or "ACTION ITEM" in u: group = "decision"
            else: group = "memory"
            
            for tag in ["[MEETING]","[REASSIGNMENT]","[BLOCKER]","[CAPACITY]","[DEADLINE]","[DECISION]","[GENERAL]"]:
                text = text.replace(tag, "").strip()
                
            short = (text[:32] + "…") if len(text) > 32 else text
            nodes.append({"id": nid, "label": short, "title": text, "group": group})
            edges.append({"from": nid - 1, "to": nid})
            
        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        return {"nodes": [{"id": 0, "label": "Offline", "group": "core", "title": str(e)}], "edges": []}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)