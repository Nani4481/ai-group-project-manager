# 🎓 TeamSync AI

**A HackwithBanglore 2.0 Submission** TeamSync AI is a brutally honest AI Group Project Manager built for the theme: AI Agents That Learn Using Hindsight. 

Anyone who has taken a Computer Science capstone knows the problem: students struggle to coordinate tasks in group projects. Standard AI tools have amnesia—they will happily suggest assigning a critical database task to the exact same teammate who completely ghosted the team on the last sprint. 

To solve this, we built an AI project manager that actively remembers team roles, past decisions, and task completion progress. By leveraging Vectorize's Hindsight memory, TeamSync AI doesn't just manage tasks; it enforces behavioral policies to protect your grade.

## ✨ Key Features

Our project includes automatic meeting summaries, task assignment recommendations, and deadline reminders, supercharged by long-term memory.

* **🧠 Hindsight Memory Integration:** Stores meeting notes, grading rubrics, and failure patterns natively using the Hindsight API so the agent learns over time.
* **🛑 Brutally Honest Interventions:** Powered by Gemini 2.5 Flash, the AI will throw an "Intervention Card" and actively block you if you try to assign critical tasks to repeat free-riders.
* **🚨 Panic Mode:** When deadlines are 24 hours away, the AI cross-references the Kanban board with historical capacity memories to ruthlessly suggest cutting bonus features and reassigning work to reliable members.
* **📊 Visual Memory Graph:** A dynamic, node-based timeline UI that allows you to literally see the agent's memory (decisions, blockers, meeting notes) over the lifecycle of the sprint.
* **⚡ Real-time Collaboration:** WebSocket-driven Kanban board that updates instantly across all team members' screens.

## 🛠️ Tech Stack

**Frontend:**
* HTML5, CSS3, Vanilla JavaScript
* `vis-network` (for the interactive Hindsight Memory Graph)

**Backend:**
* Python 3.x
* FastAPI & Uvicorn (REST API & WebSockets)
* SQLite / `aiosqlite` (Local state management)

**AI & Memory:**
* **LLM:** Google Gemini 2.5 Flash (`google-genai` SDK)
* **Agent Memory:** Hindsight API by Vectorize

## 🚀 Getting Started

Follow these instructions to run TeamSync AI on your local machine.

### Prerequisites
You will need API keys for both Google Gemini and Hindsight.
1. Get a [Gemini API Key](https://aistudio.google.com/)
2. Get a [Hindsight API Key & Project ID](https://hindsight.vectorize.io/)

### Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR-USERNAME/teamsync-ai.git](https://github.com/YOUR-USERNAME/teamsync-ai.git)
   cd teamsync-ai
