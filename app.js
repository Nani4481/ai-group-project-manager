const API_BASE = "http://localhost:8000";

let AUTH_TOKEN   = localStorage.getItem("ts_token");
let TEAM_ID      = localStorage.getItem("ts_team_id");
let TEAM_CODE    = localStorage.getItem("ts_team_code");
let CURRENT_USER = localStorage.getItem("ts_user") || "User";
let CURRENT_ROLE = localStorage.getItem("ts_role") || "";
let WS           = null;

const textarea = document.querySelector(".chat-input-container textarea");
const sendBtn  = document.querySelector(".btn-send");

function formatMentions(t) { return t.replace(/(@\w+)/g, '<span class="mention">$1</span>'); }
function toggleSidebar() { document.querySelector(".sidebar-left").classList.toggle("open"); }
function updateToggleUI() { document.getElementById("memory-wrapper").classList.toggle("disabled", !document.getElementById("memory-toggle").checked); }

function formatAIResponse(text) {
    if (!text) return "";
    let html = text.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    html = html.replace(/\n/g, "<br>");
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
    html = html.replace(/`(.*?)`/g, "<span style='font-family:var(--font-mono);background:rgba(255,255,255,0.1);padding:2px 5px;border-radius:3px;font-size:0.9em;'>$1</span>");
    html = html.replace(/<br>[-•]\s(.+)/g, "<br><span style='display:inline-block;margin-left:10px;'>• $1</span>");
    return html;
}

function aiAvatar() {
    return `<div class="avatar ai"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg></div>`;
}

function postSystemNotice(msg) {
    const cc = document.getElementById("chat-container");
    const el = document.createElement("div");
    el.className = "system-notice";
    el.innerHTML = `⚠️ ${msg}`;
    cc.insertBefore(el, document.getElementById("chat-anchor"));
    cc.scrollTop = cc.scrollHeight;
}

function postProactiveAlert(msg, severity, patternDetected) {
    const cc = document.getElementById("chat-container");
    const el = document.createElement("div");
    const color = severity === "critical" ? "#ef4444" : "#eab308";
    el.className = "system-notice proactive-alert";
    el.style.cssText = `border-color:${color};background:${color}18;color:${color};`;
    el.innerHTML = `<strong>AI Alert:</strong> ${msg}`;
    cc.insertBefore(el, document.getElementById("chat-anchor"));
    cc.scrollTop = cc.scrollHeight;
}

async function joinTeam() {
    const code = document.getElementById("auth-team-code").value.trim().toUpperCase();
    const name = document.getElementById("auth-name").value.trim();
    const role = document.getElementById("auth-role").value.trim();
    
    if (!code || !name || !role) { 
        document.getElementById("auth-error").textContent = "All fields required."; 
        return; 
    }
    
    document.getElementById("auth-submit-btn").disabled = true;
    
    try {
        const res  = await fetch(`${API_BASE}/api/auth/join`, {
            method: "POST", 
            headers: {"Content-Type":"application/json"},
            body: JSON.stringify({team_code: code, user_name: name, user_role: role})
        });
        const data = await res.json();
        
        AUTH_TOKEN = data.token; TEAM_ID = data.team_id; TEAM_CODE = data.team_code; CURRENT_USER = name; CURRENT_ROLE = role;
        localStorage.setItem("ts_token", AUTH_TOKEN); 
        localStorage.setItem("ts_team_id", TEAM_ID);
        localStorage.setItem("ts_team_code", TEAM_CODE); 
        localStorage.setItem("ts_user", name); 
        localStorage.setItem("ts_role", role);
        
        document.getElementById("auth-modal").style.display = "none";
        await initApp();
    } catch { 
        document.getElementById("auth-error").textContent = "Connection failed. Backend running?"; 
        document.getElementById("auth-submit-btn").disabled = false; 
    }
}

function logout() { 
    ["ts_token","ts_team_id","ts_team_code","ts_user","ts_role"].forEach(k => localStorage.removeItem(k)); 
    location.reload(); 
}

function initWebSocket() {
    if (!TEAM_ID) return;
    WS = new WebSocket(API_BASE.replace("http","ws") + `/ws/${TEAM_ID}`);
    WS.onopen = () => {
        document.getElementById("ws-dot").style.cssText = "background:#22c55e;box-shadow:0 0 6px rgba(34,197,94,0.5);";
    };
    WS.onmessage = e => {
        const msg = JSON.parse(e.data);
        if (msg.type === "board_update") renderBoard(msg.board);
        else if (msg.type === "members_update") renderMembersSidebar(msg.members);
    };
    WS.onclose = () => { 
        document.getElementById("ws-dot").style.cssText = "background:#64748b;"; 
        setTimeout(initWebSocket, 3000); 
    };
}

// ── DEMO SPECIFIC: Assign realistic statuses to the preloaded members
function renderMembersSidebar(members) {
    const list = document.getElementById("team-member-list");
    if (!list) return;
    document.getElementById("member-count").textContent = members.length;
    
    // Fake status assigner to make the demo look active
    const getStatus = (name) => {
        if (name.toLowerCase() === CURRENT_USER.toLowerCase()) return "online";
        if (name === "Alex") return "away";
        if (name === "Chad") return "offline"; // Chad is slacking
        return "online";
    };

    list.innerHTML = members.map(m => `
        <div class="team-member">
            <div class="status-dot ${getStatus(m.name)}"></div>
            <div class="team-avatar" style="background:rgba(255,255,255,0.1);">${m.name.substring(0,2).toUpperCase()}</div>
            ${m.name} ${m.name.toLowerCase() === CURRENT_USER.toLowerCase() ? '<span style="font-size:0.6rem;color:var(--accent-purple);font-family:var(--font-mono);">(you)</span>' : ''}
            <span class="member-role">${m.role}</span>
        </div>`).join("");
}

async function fetchMembers() {
    try { 
        const data = await fetch(`${API_BASE}/api/members/${TEAM_ID}`).then(r=>r.json()); 
        renderMembersSidebar(data.members); 
    } catch {}
}

async function fetchStartupMemory() {
    try {
        const res = await fetch(`${API_BASE}/api/memory/startup/${TEAM_ID}?user_name=${CURRENT_USER}&user_role=${CURRENT_ROLE}`);
        const data = await res.json();
        
        if (data.memory_count > 0) {
            document.getElementById("memory-count-text").textContent = `${data.memory_count} memories`;
            document.getElementById("memory-count-badge").style.display = "inline-flex";
        }
        
        if (data.welcome) {
            const cc = document.getElementById("chat-container");
            const msg = document.createElement("div"); 
            msg.className = "message ai";
            msg.innerHTML = `${aiAvatar()}<div class="message-content"><div class="bubble">${formatAIResponse(data.welcome)}</div></div>`;
            cc.insertBefore(msg, document.getElementById("chat-anchor"));
            cc.scrollTop = cc.scrollHeight;
        }
    } catch {}
}

function getDeadlineBadge(dl) {
    if (!dl) return "";
    const diff = Math.ceil((new Date(dl) - new Date()) / 86400000);
    if (diff < 0) return `<span class="deadline-badge overdue">Overdue</span>`;
    if (diff === 0) return `<span class="deadline-badge due-today">Due today</span>`;
    return `<span class="deadline-badge">${dl}</span>`;
}

function renderBoard(db) {
    const kanban = document.getElementById("dynamic-kanban");
    if (!kanban) return;
    
    const tagColor = { backend: {bg:"rgba(59,130,246,0.15)", color:"#93c5fd"}, design: {bg:"rgba(168,85,247,0.15)", color:"#d8b4fe"} };
    const palette = ["#3b82f6","#a855f7","#ef4444","#22c55e","#eab308","#06b6d4"];
    let ci = 0; 
    const colorMap = {}; 
    const ac = a => { if (!colorMap[a]) colorMap[a] = palette[ci++ % palette.length]; return colorMap[a]; };
    
    const col = (title, items, done=false) => {
        let h = `<div class="k-column ${done?"col-done":""}"><div class="k-column-title">${title} <span class="k-count">${items.length}</span></div>`;
        items.forEach(t => {
            const ts = tagColor[t.tag] || {bg:"rgba(255,255,255,0.1)",color:"#94a3b8"};
            const ab = done ? "#22c55e" : ac(t.assignee);
            h += `<div class="k-card">
            <div class="k-card-title">${t.title} ${getDeadlineBadge(t.deadline)}</div>
            <div class="k-card-meta">
                <span class="k-tag" style="background:${ts.bg};color:${ts.color};">${t.tag}</span>
                <div style="display:flex; gap:6px; align-items:center;">
                    ${!done ? `<button onclick="markTaskFailed('${t.id}')" style="background:rgba(239,68,68,0.1);border:1px solid #ef4444;color:#fca5a5;border-radius:4px;font-size:0.65rem;padding:3px 6px;cursor:pointer;" title="Report team member as missing/ghosting">👻 Ghosted</button>` : ""}
                    <div class="k-avatar" style="background:${ab};color:#fff;">${t.assignee.substring(0,2).toUpperCase()}</div>
                </div>
            </div></div>`;
        });
        return h + `</div>`;
    };
    kanban.innerHTML = col("To Do",db.todo||[]) + col("In Progress",db.inProgress||[]) + col("Done",db.done||[],true);
}

async function fetchAndRenderBoard() { 
    try { 
        const db = await fetch(`${API_BASE}/api/board?team_id=${TEAM_ID}`).then(r=>r.json()); 
        renderBoard(db); 
    } catch {} 
}

function buildActionCard(card) {
    if (!card) return "";
    if (card.type === "intervention") {
        return `<div class="action-card intervention-card">
            <div style="font-size:1.1rem;font-weight:900;color:#ef4444;text-align:center;margin-bottom:12px;font-family:var(--font-display);">
                ⚠️ HINDSIGHT BLOCKED REPEAT FAILURE
            </div>
            <div style="font-size:0.85rem;color:var(--text-primary);margin-bottom:10px;line-height:1.5;border-left:4px solid #ef4444;padding-left:12px;background:rgba(239,68,68,0.08);padding:10px 12px;">
                ${card.warning}
            </div>
            <div style="font-size:0.85rem;color:#86efac;font-weight:600;margin-bottom:14px;padding:8px 12px;background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);border-radius:6px;">
                💡 ${card.recommendation}
            </div>
            <div style="display:flex;gap:8px;">
                <button class="btn-approve" style="background:#22c55e;color:#000;flex:1;" onclick="createTaskAction(this,'${card.task_title}','${card.suggested_assignee}','${card.tag}','')">✓ Accept Reassignment</button>
            </div>
        </div>`;
    }
    if (card.type === "create") {
        return `<div class="action-card">
            <div class="action-header"><span class="action-title">Create New Task</span></div>
            <div class="action-body"><div>${card.task_title}</div><div style="font-size:0.7rem;">→ ${card.assignee}</div></div>
            <button class="btn-approve" onclick="createTaskAction(this,'${card.task_title}','${card.assignee}','${card.tag}','')">Confirm Create Task</button></div>`;
    }
    if (card.type === "reassign") {
        return `<div class="action-card">
            <div class="action-header"><span class="action-title">Approve Reassignment</span></div>
            <div class="action-body"><div>${card.task_title}</div><div style="font-size:0.7rem;">${card.from_assignee} → ${card.to_assignee}</div></div>
            <button class="btn-approve" onclick="approveAction(this,'${card.task_id}','${card.from_assignee}','${card.to_assignee}')">Approve Change</button></div>`;
    }
    return "";
}

async function approveAction(btn, taskId, fromA, toA) {
    if (btn.disabled) return;
    btn.innerHTML = "Processing..."; btn.disabled = true;
    try {
        const data = await fetch(`${API_BASE}/api/tasks/reassign`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({task_id:taskId,new_assignee:toA,team_id:TEAM_ID}) }).then(r=>r.json());
        if (data.success) { btn.classList.add("approved"); btn.innerHTML = "Reassigned"; }
    } catch { btn.innerHTML = "Error."; btn.disabled = false; }
}

async function createTaskAction(btn, title, assignee, tag, deadline) {
    if (btn.disabled) return;
    btn.innerHTML = "Creating..."; btn.disabled = true;
    try {
        const data = await fetch(`${API_BASE}/api/tasks/create`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({title, assignee, tag, deadline, team_id: TEAM_ID}) }).then(r => r.json());
        if (data.success) { btn.classList.add("approved"); btn.innerHTML = `✓ Task Created!`; }
    } catch { btn.innerHTML = "Error."; btn.disabled = false; }
}

async function markTaskFailed(taskId) {
    if (!confirm(`Mark task ${taskId} as GHOSTED? This records a failure pattern to Hindsight.`)) return;
    try {
        const res = await fetch(`${API_BASE}/api/tasks/mark_failed?task_id=${taskId}&team_id=${TEAM_ID}`, { method: "POST" });
        const data = await res.json();
        if (data.success) postSystemNotice(`⚠ Failure recorded for ${taskId}. Hindsight will block this user on similar tasks.`);
    } catch {}
}

function openMeetingModal() { document.getElementById("meeting-modal").style.display = "flex"; }
function closeMeetingModal() { document.getElementById("meeting-modal").style.display = "none"; document.getElementById("meeting-notes-input").value = ""; }

async function submitMeetingNotes() {
    const notes = document.getElementById("meeting-notes-input").value.trim();
    if (!notes) return;
    document.getElementById("meeting-submit-btn").disabled = true;
    try {
        const data = await fetch(`${API_BASE}/api/meeting/summary`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({notes, team_id:TEAM_ID}) }).then(r=>r.json());
        closeMeetingModal();
        postSystemNotice("Rubric / Meeting requirements parsed and stored to Hindsight.");
    } catch { 
        closeMeetingModal(); 
        postSystemNotice("Failed to parse notes."); 
    }
}

async function triggerPanicMode(btn) {
    if (btn.disabled) return;
    const orig = btn.innerHTML;
    btn.innerHTML = "Triaging..."; btn.disabled = true;
    
    const cc = document.getElementById("chat-container");
    const anchor = document.getElementById("chat-anchor");
    
    const userMsg = document.createElement("div"); 
    userMsg.className = "message user";
    userMsg.innerHTML = `<div class="avatar" style="background:#ea580c;color:#fff;">🚨</div><div class="message-content"><div class="bubble" style="background:#ea580c;color:white;">INITIATE PANIC MODE. We have 14 hours. What do we do?</div></div>`;
    cc.insertBefore(userMsg, anchor); 
    cc.scrollTop = cc.scrollHeight;
    
    try {
        const data = await fetch(`${API_BASE}/api/project/panic/${TEAM_ID}`).then(r=>r.json());
        const aiMsg = document.createElement("div"); 
        aiMsg.className = "message ai";
        aiMsg.innerHTML = `${aiAvatar()}<div class="message-content"><div class="recall-badge" style="background:rgba(239,68,68,0.2);color:#fca5a5;border-color:#ef4444;">⚠️ Hindsight Analysis: Severe Time Crunch</div><div class="bubble">${formatAIResponse(data.reply||"Drop the bonus features immediately.")}</div>${buildActionCard(data.action_card||null)}</div>`;
        cc.insertBefore(aiMsg, anchor); 
        cc.scrollTop = cc.scrollHeight;
    } catch { 
        postSystemNotice("Panic mode failed."); 
    }
    
    btn.innerHTML = orig; btn.disabled = false;
}

// ── Restored Memory Graph & Velocity Triggers
async function triggerHeaderAction(btn, type) {
    if (type === "Meeting") openMeetingModal();
    else if (type === "Velocity") {
        document.getElementById("velocity-modal").style.display = "flex";
        document.getElementById("velocity-container").innerHTML = `<div style="color:var(--text-tertiary);padding:20px;">Analyzing team reliability from Hindsight...</div>`;
        try {
            const data = await fetch(`${API_BASE}/api/sprint/velocity/${TEAM_ID}`).then(r=>r.json());
            if (!data.has_data) { 
                document.getElementById("velocity-container").innerHTML = `<div style="color:var(--text-tertiary);padding:20px;">Not enough history.</div>`; 
                return; 
            }
            document.getElementById("velocity-container").innerHTML = `<div style="font-size:0.9rem;line-height:1.5;padding:15px;">${data.summary}</div>`;
        } catch {}
    }
    else if (type === "Memory Graph") {
        document.getElementById("memory-modal").style.display = "flex";
        const c = document.getElementById("timeline-container");
        c.innerHTML = `<div style="color:var(--text-tertiary);font-family:var(--font-mono);padding:20px;">Extracting from Hindsight...</div>`;
        try {
            const data = await fetch(`${API_BASE}/api/memory/graph/${TEAM_ID}`).then(r=>r.json());
            if (!data.nodes || data.nodes.length <= 1) {
                c.innerHTML = `<div style="color:var(--text-tertiary);padding:20px;font-family:var(--font-mono);">No memories yet.</div>`; 
                return;
            }
            const gc = {core:"#a855f7",decision:"#ef4444",meeting:"#3b82f6",blocker:"#f97316", reassignment:"#22c55e",capacity:"#eab308",deadline:"#ec4899",memory:"#64748b"};
            c.innerHTML = `<div class="timeline-container">${
                data.nodes.filter(n=>n.group!=="core").map(n => {
                    const col = gc[n.group]||gc.memory;
                    return `<div class="timeline-item" style="border-left:3px solid ${col}20;">
                        <div class="tl-badge" style="background:${col}20;color:${col};border-color:${col}40;">${n.group.toUpperCase()}</div>
                        <div class="tl-title" style="margin-top:4px;">${n.title||n.label}</div>
                    </div>`;
                }).join("")
            }</div>`;
        } catch { 
            c.innerHTML = `<p style="color:#ef4444;padding:20px;">Failed.</p>`; 
        }
    }
}

async function simulateResponse() {
    const raw = textarea.value.trim(); 
    if (!raw) return;
    
    const cc = document.getElementById("chat-container"); 
    const anchor = document.getElementById("chat-anchor");
    
    const userMsg = document.createElement("div"); 
    userMsg.className = "message user";
    userMsg.innerHTML = `<div class="avatar" style="background:var(--text-primary);color:var(--bg-base);">${CURRENT_USER.substring(0,2).toUpperCase()}</div><div class="message-content"><div class="bubble">${formatMentions(raw)}</div></div>`;
    cc.insertBefore(userMsg, anchor); 
    textarea.value = ""; 
    textarea.style.height = "22px"; 
    cc.scrollTop = cc.scrollHeight;
    
    const typing = document.createElement("div"); 
    typing.className = "message ai typing-msg";
    typing.innerHTML = `${aiAvatar()}<div class="message-content"><div class="bubble"><div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div></div></div>`;
    cc.insertBefore(typing, anchor); 
    cc.scrollTop = cc.scrollHeight;
    
    try {
        const data = await fetch(`${API_BASE}/api/chat`, { 
            method:"POST", 
            headers:{"Content-Type":"application/json"}, 
            body:JSON.stringify({ 
                message:raw, 
                team_id:TEAM_ID, 
                session_id:TEAM_ID, 
                use_memory:document.getElementById("memory-toggle").checked, 
                current_user:CURRENT_USER, 
                current_role:CURRENT_ROLE 
            }) 
        }).then(r=>r.json());
        
        typing.remove();
        const badge = data.memories_used ? `<div class="recall-badge">Hindsight Memory Recalled</div>` : "";
        const aiMsg = document.createElement("div"); 
        aiMsg.className = "message ai";
        aiMsg.innerHTML = `${aiAvatar()}<div class="message-content">${badge}<div class="bubble">${formatAIResponse(data.reply||"")}</div>${buildActionCard(data.action_card||null)}</div>`;
        cc.insertBefore(aiMsg, anchor); 
        cc.scrollTop = cc.scrollHeight;
    } catch { 
        typing.remove(); 
        postSystemNotice("Error: Is backend running?"); 
    }
}

sendBtn.addEventListener("click", simulateResponse);
textarea.addEventListener("keydown", e => { 
    if (e.key === "Enter" && !e.shiftKey) { 
        e.preventDefault(); 
        simulateResponse(); 
    } 
});

async function initApp() {
    document.getElementById("team-code-badge").textContent = TEAM_CODE;
    document.getElementById("sidebar-name").textContent = CURRENT_USER;
    document.getElementById("sidebar-role").textContent = CURRENT_ROLE;
    document.getElementById("sidebar-avatar").textContent = CURRENT_USER.substring(0,2).toUpperCase();
    
    initWebSocket(); 
    await fetchStartupMemory(); 
    await fetchAndRenderBoard(); 
    await fetchMembers();
}

document.addEventListener("DOMContentLoaded", async () => {
    if (!AUTH_TOKEN || !TEAM_ID) {
        document.getElementById("auth-modal").style.display = "flex";
    } else {
        await initApp();
    }
});