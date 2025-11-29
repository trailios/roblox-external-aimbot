# Roblox ESP & Aimbot (deep.py)

Python-based overlay for Roblox that draws simple ESP boxes/health and provides a toggleable aimbot using live process memory reads. Runs a transparent pyglet window over the game and moves the mouse toward the closest target inside a user-defined FOV. Built for educational/testing purposes only - just a fun side project, not a primary tool.

## Features
- ESP: 2D boxes, optional names and health bars (toggle in code).
- Aimbot: Toggle with `B`, hold right mouse button to aim; configurable FOV/smoothing.
- Team filtering and cached player refresh for lower overhead.
- Uses offsets from `https://robloxoffsets.com/offsets.json` at startup.

## Requirements
- Windows OS (calls Win32 APIs and reads Roblox process memory).
- FishStrap (production channel): https://www.fishstrap.app/
- Python 3.8+.
- Roblox client running (`RobloxPlayerBeta.exe`).
- Dependencies: `pip install pyglet psutil requests pywin32`.

## Quick Start
1) Install dependencies:  
   `pip install pyglet psutil requests pywin32`
2) Start Roblox and join a game.
3) Run the script (may need an elevated prompt for process access):  
   `python deep.py`
4) An overlay window appears; keep Roblox focused for aiming to work.

## Controls
- `B`: Toggle aimbot on/off (status shown on overlay).
- Hold right mouse button: Engage aim when enabled.

## Configuration (edit `deep.py`)
- Visual toggles: `DRAW_NAMES`, `DRAW_HEALTH`, `TEAM_CHECK`.
- Timing/cache: `PLAYER_CACHE_INTERVAL`.
- Colors: `COLOR_ENEMY`, `COLOR_HEALTH_*`, `COLOR_TEXT`.
- Aimbot tuning: `AimbotThread.fov`, `AimbotThread.smooth`.

## Notes
- The script fetches offsets at launch; stale/invalid offsets will break reads.
- Overlay uses a borderless, click-through window; close with `Esc`.
- Error output prints to the console; set `DEBUG_COUNTS = True` to log player cache changes.

## Disclaimer
Use responsibly and at your own risk. Interacting with game memory may violate game terms of service and could lead to enforcement actions. For educational/testing purposes only.

## Credits
Original concept/codebase inspiration: https://github.com/BornPaster/roblox-external
My mental health help: Chatgpt 5.1 MAX
