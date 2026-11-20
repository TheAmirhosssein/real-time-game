# Architecture Decision Record (ADR): 1v1 Reactor / Core Duel

**Project:** 1v1 Reactor / Core Duel (University Real-Time Game Project)  
**Tech Stack:** Python 3.10+, Kivy Framework, SQLite (Local/Server DB), Socket/Async Networking (for 1v1 Matchmaking & Sync)  
**Target AI Code Generator:** Grok 4.6  
**Status:** Accepted / Ready for Implementation  

---

## 1. Context & Architectural Goals

We are building a real-time 1v1 top-down arena game (**Reactor / Core Duel**) in Python using the Kivy framework. The entire codebase will be generated iteratively via vibe coding with Grok 4.6.

### Core Architectural Decisions
1. **Strict Separation of Concerns:** Isolate game simulation/physics (`core/`), database & matchmaking (`services/`), and Kivy UI/Canvas rendering (`ui/`). Never mix business logic or SQL queries inside `.kv` files or Kivy `Widget` draw loops.
2. **Unified Database Identity (Registered + Guest):** Every player—whether registered with credentials or entering via a one-click Temporary Guest account—must be persisted in the database with a unique `user_id`, skill rating (`score`), and match history.
3. **Score-Range Matchmaking:** Matchmaking queries the active queue for opponents within an expanding `±score` window before falling back to wider brackets or local/bot fallback for classroom demos.
4. **Full Movement & Event Telemetry:** Player inputs, position snapshots, dashes, shots, and match outcomes are recorded in a structured format (both for real-time state sync and post-match database persistence/replay logs).
5. **60 FPS Delta-Time Loop:** All real-time arena updates run via `Clock.schedule_interval(update, 1.0 / 60.0)` using `dt` (delta time) to ensure frame-rate independence.

---

## 2. Visual Design System & Color Palette

The game uses a **Dark Reactor / Cyber-Arcade** theme optimized for high contrast on Kivy's `Canvas` without visual clutter.

| Role | Token Name | Hex Code | RGBA (Kivy Normalized) | Usage |
| :--- | :--- | :--- | :--- | :--- |
| **Background Void** | `BG_VOID` | `#090D16` | `(0.035, 0.051, 0.086, 1)` | App root background, arena void |
| **Panel Surface** | `SURFACE_PANEL` | `#111827` | `(0.067, 0.094, 0.153, 1)` | Auth cards, lobby containers, modals |
| **Elevated Control** | `SURFACE_ELEVATED` | `#1E293B` | `(0.118, 0.161, 0.231, 1)` | TextInputs, secondary buttons, pills |
| **Border / Grid** | `BORDER_CONDUIT` | `#283548` | `(0.157, 0.208, 0.282, 1)` | Card outlines, subtle arena grid lines |
| **Primary Text** | `TEXT_PRIMARY` | `#F8FAFC` | `(0.973, 0.980, 0.988, 1)` | Headings, active callsigns, HUD timers |
| **Muted Text** | `TEXT_MUTED` | `#94A3B8` | `(0.580, 0.639, 0.722, 1)` | Subtitles, hints, rating labels |
| **Player 1 / Primary** | `ACCENT_CYAN` | `#00E5FF` | `(0.000, 0.898, 1.000, 1)` | P1 Core, primary CTAs, focus borders |
| **Player 2 / Rival** | `ACCENT_AMBER` | `#FF6B00` | `(1.000, 0.420, 0.000, 1)` | P2 Core, opponent badges, alerts |
| **Success / Ready** | `STATE_SUCCESS` | `#10B981` | `(0.063, 0.725, 0.506, 1)` | Ready status, matchmaking found |
| **Error / Critical** | `STATE_ERROR` | `#EF4444` | `(0.937, 0.267, 0.267, 1)` | Validation errors, Sudden Death alert |

---

## 3. UI & Screen Architecture (`ScreenManager`)

All screens are managed by a root `ScreenManager` with `FadeTransition` or `NoTransition`.

### 3.1 Login Screen (`login_screen`)
* **Layout:** Centered card (`420dp` width) on `BG_VOID` with `1dp` `BORDER_CONDUIT` stroke.
* **Components:**
  * Header emblem: `CORE DUEL // 1V1` + `PILOT LOGIN`.
  * `TextInput` for **Callsign / Username** and **Password** (password masked).
  * Primary CTA (`ACCENT_CYAN`): **`ENTER LOBBY`**.
  * Secondary CTA (`SURFACE_ELEVATED`): **`CONTINUE AS GUEST`** (auto-creates a temporary guest record in DB and logs in immediately).
  * Link/Button: **`CREATE NEW ACCOUNT`** -> transitions to `register_screen`.
  * Inline status label (`STATE_ERROR` / `STATE_SUCCESS`).

### 3.2 Register Screen (`register_screen`)
* **Layout:** Matches Login card dimensions for visual continuity.
* **Components:**
  * Top navigation: `← BACK TO LOGIN`.
  * Fields: **Callsign** (unique, 3–16 chars), **Email / Student ID**, **Password**, **Confirm Password**.
  * Primary CTA (`ACCENT_CYAN`): **`REGISTER PILOT`**.
  * Validation: Checks duplicate callsign in DB, password match, and non-empty fields. New accounts start at default rating `score = 1000`.

### 3.3 Lobby & Matchmaking Screen (`lobby_screen`)
* **Top Telemetry Bar:** Displays active user's Callsign, Account Badge (`REGISTERED` vs. `GUEST`), current **Skill Score (MMR)**, W/L record, and `LOG OUT` button.
* **Left Panel (Match Configuration & Queue):**
  * **Arena Preset Selector:** `Standard Containment`, `Twin Pillars`, `Overclocked`.
  * **Matchmaking Controls:**
    * Primary CTA: **`FIND 1V1 MATCH`** (enters score-based matchmaking queue).
    * Queue Status Box: Shows elapsed search time, current search rating bracket (e.g., `Searching: 950 – 1050 MMR...`), and `CANCEL SEARCH`.
    * Demo Fallback Button: **`LOCAL 1V1 (SAME KEYBOARD)`** so two players can test/demo instantly on one laptop if no second network client is queued.
* **Right Panel (Versus Readiness Card):**
  * **Slot 01 (`ACCENT_CYAN`):** Current player's Callsign, Score, and `READY` badge.
  * **Slot 02 (`ACCENT_AMBER`):** Matched opponent's Callsign, Score, and `READY` status (shows `SEARCHING...` while in queue).

### 3.4 Arena HUD & Overlays (`game_screen`)
* **Canvas Layer:** Full-window `BG_VOID` arena with subtle `BORDER_CONDUIT` grid, central Reactor Core energy zone, obstacle pillars, glowing player cores, projectiles/pulses, and particle trails.
* **Top HUD Strip:**
  * Left: P1 Callsign + Core Integrity HP Bar (`ACCENT_CYAN`) + Energy/Dash charge.
  * Center: Match Countdown Timer (`90s`) -> turns `STATE_ERROR` during `SUDDEN DEATH`.
  * Right: P2 Callsign + Core Integrity HP Bar (`ACCENT_AMBER`) + Energy/Dash charge.
* **Modals:**
  * **Pause Overlay:** `RESUME`, `FORFEIT / RETURN TO LOBBY`.
  * **Post-Match Summary Overlay:** Winner banner, updated Skill Score delta (e.g., `+24 MMR` / `-24 MMR`), movement/accuracy telemetry summary, `PLAY AGAIN`, and `LOBBY`.

---

## 4. Database Schema & Persistence Rules

Use SQLite (`sqlite3` with WAL mode enabled for concurrent reads/writes) via a dedicated `DatabaseManager` class.

### 4.1 `users` Table
Stores both permanent accounts and temporary guest accounts uniformly so matchmaking and telemetry treat every player identically.
```sql
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,           -- UUIDv4
    username TEXT UNIQUE NOT NULL,      -- e.g., "Pilot_Nova" or "Guest_8492"
    password_hash TEXT,                 -- NULL for guest accounts
    is_guest INTEGER NOT NULL DEFAULT 0,-- 0 = Registered, 1 = Temporary Guest
    score INTEGER NOT NULL DEFAULT 1000,-- Matchmaking Rating (MMR)
    wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 `matchmaking_queue` Table
Tracks players actively searching for a 1v1 duel.
```sql
CREATE TABLE IF NOT EXISTS matchmaking_queue (
    queue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT UNIQUE NOT NULL,
    score INTEGER NOT NULL,
    arena_preset TEXT DEFAULT 'Standard Containment',
    status TEXT DEFAULT 'SEARCHING',    -- 'SEARCHING', 'MATCHED'
    matched_room_id TEXT,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```

### 4.3 `matches` & `movement_logs` Tables
Persists match outcomes and full player movement/action telemetry in the database.
```sql
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    player1_id TEXT NOT NULL,
    player2_id TEXT NOT NULL,
    winner_id TEXT,
    p1_score_before INTEGER,
    p2_score_before INTEGER,
    p1_score_delta INTEGER,
    p2_score_delta INTEGER,
    duration_seconds REAL,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (player1_id) REFERENCES users(user_id),
    FOREIGN KEY (player2_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS movement_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    pos_x REAL NOT NULL,
    pos_y REAL NOT NULL,
    vel_x REAL NOT NULL,
    vel_y REAL NOT NULL,
    angle REAL NOT NULL,
    action_flags TEXT,                  -- JSON string: e.g., {"dash": true, "fire": false}
    FOREIGN KEY (match_id) REFERENCES matches(match_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);
```
* **Performance Decision for Movement Logging:** During 60 FPS gameplay, buffer movement ticks in memory (e.g., sampling at 15–20 Hz or batching every 60 ticks) and execute a single batch `executemany()` transaction to SQLite so disk I/O never causes frame drops.

---

## 5. Core Game Mechanics & Matchmaking Logic

### 5.1 Score-Range Matchmaking Algorithm
1. When a player clicks **`FIND 1V1 MATCH`**, insert/update their row in `matchmaking_queue` with `status = 'SEARCHING'` and their current `users.score`.
2. **Expanding Search Window:**
   * **0–5 seconds in queue:** Search for an opponent with `abs(opponent.score - my.score) <= 100`.
   * **5–15 seconds in queue:** Expand range to `<= 250`.
   * **15+ seconds in queue:** Expand range to `<= 500` (or match any available waiting player).
3. When two players match, atomically create a `match_id`, update both queue rows to `MATCHED` with the shared `matched_room_id`, and transition both clients to `game_screen`.
4. **ELO / Score Update:** On match completion, adjust winner/loser scores using standard ELO ($K = 32$) and update `users.score`, `wins`, and `losses`.

### 5.2 1v1 Reactor / Core Duel Gameplay Rules
* **Arena & Objective:** Top-down rectangular containment arena (`1280x720` virtual coordinates scaled to window). Each player controls a Reactor Core ship (`radius = 22px`). Win by reducing the opponent's Core Integrity from `100 HP` to `0 HP`, or having higher HP when the `90s` timer expires.
* **Player Controls:**
  * **Movement:** Smooth 8-directional acceleration/friction physics (`WASD` for P1; `Arrow Keys` for P2 in local mode, or `WASD` + Mouse/Keyboard aim in networked 1v1).
  * **Plasma Pulse (Primary Fire):** Fires an energy bolt (`cooldown: 0.35s`, `damage: 12 HP`) that bounces once off outer containment walls.
  * **Phase Dash (Ability):** Short high-speed burst (`cooldown: 2.5s`) granting brief invulnerability frames (`0.2s`) to dodge incoming bolts.
  * **Central Reactor Overcharge:** Periodically spawns an energy node in the center; holding position inside the ring charges a **Overload Beam** (`damage: 25 HP`).
* **Sudden Death:** If HP is tied at `0:00`, arena containment walls shrink inward and cooldowns are halved until the next hit decides the winner.

---

## 6. Recommended Directory Structure for Grok 4.6

Instruct Grok 4.6 to strictly adhere to this modular layout:

```text
core_duel/
├── main.py                  # App entry point, ScreenManager setup, theme constants
├── adr.md                   # This Architecture Decision Record
├── core/
│   ├── __init__.py
│   ├── engine.py            # Pure Python 1v1 physics, collision, cooldowns, Sudden Death
│   ├── entities.py          # PlayerCore, Projectile, EnergyNode, Obstacle dataclasses
│   └── telemetry.py         # In-memory movement/input buffer & batch DB flush
├── services/
│   ├── __init__.py
│   ├── database.py          # SQLite schema init, user/guest CRUD, batch log writer
│   ├── auth_service.py      # Register, login, password hashing, Guest account generator
│   └── matchmaking.py       # Score-range queue polling, bracket expansion, ELO math
└── ui/
    ├── theme.kv             # Reusable Kivy widgets (CyberButton, CyberInput, PanelCard)
    ├── login_screen.kv      # Login UI + Guest button
    ├── register_screen.kv   # Registration UI
    ├── lobby_screen.kv      # Top bar, score-range queue UI, P1 vs P2 cards
    └── game_screen.py       # Kivy Canvas renderer, keyboard/touch input, HUD & modals
```

---

## 7. Prompting Guardrails for Grok 4.6

When feeding this `adr.md` to Grok 4.6, enforce these rules in every prompt:
1. **Build in Vertical Slices:** Generate `services/database.py` + `services/auth_service.py` first; then `ui/` auth & lobby screens; then `core/engine.py` + `ui/game_screen.py`; finally wire `services/matchmaking.py` and `core/telemetry.py`.
2. **Coordinate Scaling:** Always map arena logic (`1280x720` logical space) dynamically to the Kivy widget's `self.pos` and `self.size` so window resizing never breaks hitboxes.
3. **Clean Cleanup:** Ensure `Clock.unschedule` is called when leaving `game_screen` or `lobby_screen` so background polling or game loops never leak across screens.