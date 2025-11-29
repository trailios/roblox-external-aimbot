from ctypes import wintypes
from pyglet import gl

import win32process # type: ignore
import threading
import win32gui # type: ignore
import win32con # type: ignore
import win32api # type: ignore
import requests
import psutil
import ctypes
import pyglet
import struct
import time
import math

OFFSETS_URL = "https://robloxoffsets.com/offsets.json"
OFFSETS = requests.get(OFFSETS_URL, timeout=5).json()
TEAM_CHECK = False
PLAYER_CACHE_INTERVAL = 0.05
DRAW_NAMES = False
DRAW_HEALTH = False
DEBUG_COUNTS = True

COLOR_ENEMY = (255, 50, 50, 255)
COLOR_HEALTH_BG = (40, 40, 40, 200)
COLOR_HEALTH_FG = (0, 255, 0, 255)
COLOR_TEXT = (255, 255, 255, 255)

class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("th32ModuleID", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("GlblcntUsage", wintypes.DWORD),
        ("ProccntUsage", wintypes.DWORD),
        ("modBaseAddr", ctypes.POINTER(wintypes.BYTE)),
        ("modBaseSize", wintypes.DWORD),
        ("hModule", wintypes.HMODULE),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_char * 260)
    ]

class Vec2:
    __slots__ = ('x', 'y')
    def __init__(self, x=0.0, y=0.0):
        self.x = x
        self.y = y

class Vec3:
    __slots__ = ('x', 'y', 'z')
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x
        self.y = y
        self.z = z

class RobloxMemory:
    def __init__(self):
        self.process_handle = None
        self.base_address = None
        self.data_model = None
        self.visual_engine = None
        self.workspace = None
        self.players = None
        self.local_player = None
        self.hwnd = None
        self._view_matrix_cache = None
        self._view_matrix_time = 0.0
        self._player_cache = []
        self._cache_time = 0.0
        
        if not self.find_roblox_process():
            raise Exception("Roblox process not found")
        self.initialize_game_data()

    def _o(self, key):
        val = OFFSETS.get(key, "0x0")
        return int(val, 16) if isinstance(val, str) else val

    def find_roblox_process(self):
        hwnd, pid = self._find_window_by_exe("RobloxPlayerBeta.exe")
        if not pid:
            pid = self._get_process_id_by_psutil("RobloxPlayerBeta.exe")
            if not pid:
                return False
            hwnd, _ = self._find_window_by_exe("RobloxPlayerBeta.exe")
        
        self.hwnd = hwnd
        self.process_id = pid
        
        self.process_handle = ctypes.windll.kernel32.OpenProcess(
            win32con.PROCESS_ALL_ACCESS, False, self.process_id
        )
        if not self.process_handle:
            return False
        
        self.base_address = self._get_module_address("RobloxPlayerBeta.exe")
        if not self.base_address:
            ctypes.windll.kernel32.CloseHandle(self.process_handle)
            return False
        return True

    def _find_window_by_exe(self, exe_name):
        matches = []
        def enum_proc(hwnd, _):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                p = psutil.Process(pid)
                if p.name().lower() == exe_name.lower():
                    matches.append((hwnd, pid))
            except:
                pass
            return True
        
        win32gui.EnumWindows(enum_proc, None)
        return matches[0] if matches else (None, None)

    def _get_process_id_by_psutil(self, process_name):
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'].lower() == process_name.lower():
                return proc.info['pid']
        return None

    def _get_module_address(self, module_name):
        snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(0x18, self.process_id)
        if snapshot == -1:
            return None
        
        module_entry = MODULEENTRY32()
        module_entry.dwSize = ctypes.sizeof(MODULEENTRY32)
        
        if ctypes.windll.kernel32.Module32First(snapshot, ctypes.byref(module_entry)):
            while True:
                name = module_entry.szModule.decode().lower()
                if module_name.lower() == name:
                    ctypes.windll.kernel32.CloseHandle(snapshot)
                    return ctypes.addressof(module_entry.modBaseAddr.contents)
                if not ctypes.windll.kernel32.Module32Next(snapshot, ctypes.byref(module_entry)):
                    break
        
        ctypes.windll.kernel32.CloseHandle(snapshot)
        return None

    def read_memory(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        bytes_read = ctypes.c_size_t()
        result = ctypes.windll.kernel32.ReadProcessMemory(
            self.process_handle, ctypes.c_void_p(address), 
            buffer, size, ctypes.byref(bytes_read)
        )
        return buffer.raw[:bytes_read.value] if result and bytes_read.value > 0 else None

    def read_ptr(self, address):
        data = self.read_memory(address, 8)
        return int.from_bytes(data, 'little') if data else None

    def read_int(self, address):
        data = self.read_memory(address, 4)
        return int.from_bytes(data, 'little', signed=True) if data else None

    def read_float(self, address):
        data = self.read_memory(address, 4)
        return struct.unpack('f', data)[0] if data else None

    def read_string(self, address):
        if not address:
            return ""
        str_length = self.read_int(address + 0x18)
        if not str_length or str_length <= 0 or str_length > 1000:
            return ""
        
        if str_length >= 16:
            address = self.read_ptr(address)
            if not address:
                return ""
        
        data = self.read_memory(address, min(str_length, 1000))
        if not data:
            return ""
        
        try:
            null_pos = data.index(0)
            data = data[:null_pos]
        except ValueError:
            pass
        
        return data.decode('utf-8', errors='ignore').strip()

    def initialize_game_data(self):
        fake_dm = self.read_ptr(self.base_address + self._o("FakeDataModelPointer"))
        if not fake_dm or fake_dm == 0xFFFFFFFF:
            return
        
        dm_ptr = self.read_ptr(fake_dm + self._o("FakeDataModelToDataModel"))
        if not dm_ptr or dm_ptr == 0xFFFFFFFF:
            return
        
        for _ in range(30):
            name_ptr = self.read_ptr(dm_ptr + self._o("Name"))
            dm_name = self.read_string(name_ptr)
            if "Ugc" in dm_name or dm_name == "Ugc":
                break
            time.sleep(1)
            fake_dm = self.read_ptr(self.base_address + self._o("FakeDataModelPointer"))
            if fake_dm:
                dm_ptr = self.read_ptr(fake_dm + self._o("FakeDataModelToDataModel"))
        else:
            return
        
        self.data_model = dm_ptr
        self.visual_engine = self.read_ptr(self.base_address + self._o("VisualEnginePointer"))
        self.workspace = self._find_first_child_of_class(self.data_model, "Workspace")
        self.players = self._find_first_child_of_class(self.data_model, "Players")
        
        if self.players:
            self.local_player = self.read_ptr(self.players + self._o("LocalPlayer"))

    def _get_children(self, parent):
        if not parent:
            return []
        children_ptr = self.read_ptr(parent + self._o("Children"))
        if not children_ptr:
            return []

        start = self.read_ptr(children_ptr)
        end = self.read_ptr(children_ptr + self._o("ChildrenEnd"))
        if not start or not end or end <= start:
            return []

        def walk(stride):
            out = []
            cur = start
            while cur and cur < end:
                child = self.read_ptr(cur)
                if child:
                    out.append(child)
                cur += stride
            return out

        first = walk(0x10)
        if len(first) > 1:
            return first
        second = walk(0x8)
        return second if len(second) > len(first) else first

    def _get_instance_name(self, address):
        name_ptr = self.read_ptr(address + self._o("Name"))
        return self.read_string(name_ptr) if name_ptr else ""

    def _get_instance_class(self, address):
        class_desc = self.read_ptr(address + self._o("ClassDescriptor"))
        if class_desc:
            class_name_ptr = self.read_ptr(class_desc + self._o("ClassDescriptorToClassName"))
            return self.read_string(class_name_ptr) if class_name_ptr else ""
        return ""

    def _find_first_child_of_class(self, parent, class_name):
        for child in self._get_children(parent):
            if self._get_instance_class(child) == class_name:
                return child
        return None

    def _find_first_child_by_name(self, parent, name):
        for child in self._get_children(parent):
            if self._get_instance_name(child) == name:
                return child
        return None

    def read_matrix4(self, address):
        data = self.read_memory(address, 64)
        return [struct.unpack('f', data[i*4:(i+1)*4])[0] for i in range(16)] if data else None

    def get_view_matrix(self):
        now = time.time()
        if self._view_matrix_cache and now - self._view_matrix_time < 0.02:
            return self._view_matrix_cache
        if not self.visual_engine:
            return None
        matrix = self.read_matrix4(self.visual_engine + self._o("viewmatrix"))
        if matrix:
            self._view_matrix_cache = matrix
            self._view_matrix_time = now
        return matrix

    def get_player_data(self):
        now = time.time()
        if now - self._cache_time < PLAYER_CACHE_INTERVAL:
            return self._player_cache
        
        if not self.players or not self.local_player:
            self._player_cache = []
            return []

        local_team_name = None
        if TEAM_CHECK:
            try:
                lp_team_ptr = self.read_ptr(self.local_player + self._o("Team"))
                if lp_team_ptr:
                    local_team_name = self._get_instance_name(lp_team_ptr)
            except:
                pass
        
        players_data = []
        for player_ptr in self._get_children(self.players):
            if player_ptr == self.local_player:
                continue

            try:
                team_ptr = self.read_ptr(player_ptr + self._o("Team"))
                team_name = self._get_instance_name(team_ptr) if team_ptr else ""
                if TEAM_CHECK and local_team_name and team_name == local_team_name:
                    continue
            except:
                team_name = ""
            
            character_ptr = self.read_ptr(player_ptr + self._o("ModelInstance"))
            if not character_ptr or self._get_instance_class(character_ptr) != "Model":
                continue
            
            hrp = self._find_first_child_by_name(character_ptr, "HumanoidRootPart")
            if not hrp or self._get_instance_class(hrp) != "Part":
                continue
            
            primitive = self.read_ptr(hrp + self._o("Primitive"))
            if not primitive:
                continue
            
            pos_data = self.read_memory(primitive + self._o("Position"), 12)
            if not pos_data:
                continue
            
            x, y, z = struct.unpack('fff', pos_data)
            
            head = self._find_first_child_by_name(character_ptr, "Head")
            head_pos = None
            if head:
                head_prim = self.read_ptr(head + self._o("Primitive"))
                if head_prim:
                    head_data = self.read_memory(head_prim + self._o("Position"), 12)
                    if head_data:
                        hx, hy, hz = struct.unpack('fff', head_data)
                        head_pos = Vec3(hx, hy, hz)
            
            humanoid = self._find_first_child_of_class(character_ptr, "Humanoid")
            health = max_health = None
            if humanoid:
                health = self.read_float(humanoid + self._o("Health"))
                max_health = self.read_float(humanoid + self._o("MaxHealth"))
            
            players_data.append({
                "name": self._get_instance_name(player_ptr),
                "root_pos": Vec3(x, y, z),
                "head_pos": head_pos or Vec3(x, y + 3, z),
                "health": health,
                "max_health": max_health,
                "team": team_name
            })
        
        self._player_cache = players_data
        self._cache_time = now
        return players_data

    def get_viewport(self):
        if not self.hwnd:
            return Vec2(1920, 1080)
        try:
            left, top, right, bottom = win32gui.GetClientRect(self.hwnd)
            width = right - left
            height = bottom - top
            return Vec2(float(width), float(height)) if width > 0 and height > 0 else Vec2(1920, 1080)
        except:
            return Vec2(1920, 1080)

    def world_to_screen(self, pos, matrix=None, viewport=None):
        if not self.visual_engine:
            return Vec2(-1, -1)
        
        matrix = matrix or self.get_view_matrix()
        if not matrix:
            return Vec2(-1, -1)
        
        qx = pos.x * matrix[0] + pos.y * matrix[1] + pos.z * matrix[2] + matrix[3]
        qy = pos.x * matrix[4] + pos.y * matrix[5] + pos.z * matrix[6] + matrix[7]
        qw = pos.x * matrix[12] + pos.y * matrix[13] + pos.z * matrix[14] + matrix[15]
        
        if qw < 0.1:
            return Vec2(-1, -1)
        
        viewport = viewport or self.get_viewport()
        x = (viewport.x / 2.0) * (1.0 + qx / qw)
        y = (viewport.y / 2.0) * (1.0 - qy / qw)
        
        return Vec2(x, y) if 0 <= x <= viewport.x and 0 <= y <= viewport.y else Vec2(-1, -1)

class AimbotThread(threading.Thread):
    def __init__(self, memory):
        super().__init__(daemon=True)
        self.memory = memory
        self.enabled = False
        self.running = True
        self.fov = 80
        self.smooth = 1.2
        self._last_b_state = False

    def run(self):
        while self.running:
            self._check_toggle()
            if self.enabled and (win32api.GetAsyncKeyState(0x02) & 0x8000):
                self.aim_at_closest()
            time.sleep(1/144)

    def _check_toggle(self):
        b_state = win32api.GetAsyncKeyState(0x42) & 0x8000
        if b_state and not self._last_b_state:
            self.enabled = not self.enabled
        self._last_b_state = b_state

    def _window_active(self):
        try:
            return win32gui.GetForegroundWindow() == self.memory.hwnd
        except:
            return True

    def _move_mouse(self, dx, dy):
        step_x = int(dx / self.smooth)
        step_y = int(dy / self.smooth)
        step_x = max(-6, min(6, step_x))
        step_y = max(-6, min(6, step_y))
        if step_x == 0 and abs(dx) > 0.4:
            step_x = 1 if dx > 0 else -1
        if step_y == 0 and abs(dy) > 0.4:
            step_y = 1 if dy > 0 else -1
        if step_x == 0 and step_y == 0:
            return
        try:
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, step_x, step_y, 0, 0)
        except:
            try:
                cur_x, cur_y = win32api.GetCursorPos()
                win32api.SetCursorPos((cur_x + step_x, cur_y + step_y))
            except:
                pass

    def aim_at_closest(self):
        try:
            if not self._window_active():
                return
            players = self.memory.get_player_data()
            if not players:
                return
            matrix = self.memory.get_view_matrix()
            viewport = self.memory.get_viewport()
            center_x = viewport.x / 2
            center_y = viewport.y / 2
            closest_target = None
            closest_dist = float('inf')
            for player in players:
                head_screen = self.memory.world_to_screen(player['head_pos'], matrix, viewport)
                if head_screen.x < 0:
                    continue
                dx = head_screen.x - center_x
                dy = head_screen.y - center_y
                dist = math.hypot(dx, dy)
                if dist < self.fov and dist < closest_dist:
                    closest_dist = dist
                    closest_target = head_screen
            if closest_target:
                if closest_dist < 6.0:
                    return
                dx = closest_target.x - center_x
                dy = closest_target.y - center_y
                scale = 0.25 if closest_dist < 80 else 0.45
                self._move_mouse(dx * scale, dy * scale)
        except:
            pass

class ESPOverlay:
    def __init__(self, memory):
        self.memory = memory
        viewport = memory.get_viewport()
        self.width = int(viewport.x)
        self.height = int(viewport.y)
        
        self.aimbot = AimbotThread(memory)
        self.aimbot.start()
        
        config = pyglet.gl.Config(double_buffer=True, sample_buffers=0, samples=0)
        self.window = pyglet.window.Window(
            width=self.width,
            height=self.height,
            style=pyglet.window.Window.WINDOW_STYLE_BORDERLESS,
            caption="ESP Overlay",
            config=config,
            vsync=False
        )
        
        hwnd = self.window._hwnd
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                               ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST)
        color_key = 0x00000000
        win32gui.SetLayeredWindowAttributes(hwnd, color_key, 0, win32con.LWA_COLORKEY)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, self.width, self.height, 
                              win32con.SWP_SHOWWINDOW)
        
        self.player_cache = []
        self.cache_lock = threading.Lock()
        
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glDisable(gl.GL_DEPTH_TEST)
        
        @self.window.event
        def on_draw():
            self.window.clear()
            gl.glClearColor(0, 0, 0, 0)
            self.render()
        
        @self.window.event
        def on_key_press(symbol, modifiers):
            if symbol == pyglet.window.key.ESCAPE:
                self.aimbot.running = False
                self.window.close()
        
        pyglet.clock.schedule_interval(self.update_players, PLAYER_CACHE_INTERVAL)
        pyglet.clock.schedule_interval(self.update, 1/120.0)

    def draw_line(self, x1, y1, x2, y2, color):
        line = pyglet.shapes.Line(x1, y1, x2, y2, color=color[:3])
        line.opacity = color[3]
        line.draw()

    def draw_rect(self, x, y, width, height, color, filled=False):
        if filled:
            rect = pyglet.shapes.Rectangle(x, y, width, height, color=color[:3])
            rect.opacity = color[3]
            rect.draw()
            return
        l1 = pyglet.shapes.Line(x, y, x + width, y, color=color[:3])
        l2 = pyglet.shapes.Line(x + width, y, x + width, y + height, color=color[:3])
        l3 = pyglet.shapes.Line(x + width, y + height, x, y + height, color=color[:3])
        l4 = pyglet.shapes.Line(x, y + height, x, y, color=color[:3])
        for ln in (l1, l2, l3, l4):
            ln.opacity = color[3]
            ln.draw()

    def draw_box(self, screen_pos, head_pos, color):
        if screen_pos.x < 0 or head_pos.x < 0:
            return
        screen_y = self.height - screen_pos.y
        head_y = self.height - head_pos.y
        height = abs(screen_y - head_y)
        width = height * 0.6
        x = head_pos.x - width / 2
        y = head_y
        self.draw_rect(x, y, width, height, color)

    def draw_health_bar(self, screen_pos, health, max_health):
        if not DRAW_HEALTH or screen_pos.x < 0 or health is None or max_health is None:
            return
        bar_width = 50
        bar_height = 6
        x = screen_pos.x - bar_width / 2
        y = self.height - screen_pos.y + 15
        self.draw_rect(x, y, bar_width, bar_height, COLOR_HEALTH_BG, filled=True)
        health_pct = max(0, min(1, health / max_health))
        self.draw_rect(x, y, bar_width * health_pct, bar_height, COLOR_HEALTH_FG, filled=True)

    def update_players(self, dt):
        try:
            data = self.memory.get_player_data()
            if DEBUG_COUNTS and len(data) != len(self.player_cache):
                print(f"Players cached: {len(data)}")
            with self.cache_lock:
                self.player_cache = data
        except:
            pass

    def render(self):
        matrix = self.memory.get_view_matrix()
        viewport = self.memory.get_viewport()
        with self.cache_lock:
            players_snapshot = list(self.player_cache)
        
        for player in players_snapshot:
            root_screen = self.memory.world_to_screen(player["root_pos"], matrix, viewport)
            head_screen = self.memory.world_to_screen(player["head_pos"], matrix, viewport)
            
            if root_screen.x > 0:
                self.draw_box(root_screen, head_screen, COLOR_ENEMY)
                if DRAW_NAMES:
                    pyglet.text.Label(
                        player["name"], font_name='Arial', font_size=11,
                        x=head_screen.x, y=self.height - head_screen.y + 15,
                        anchor_x='center', color=COLOR_TEXT
                    ).draw()
                if DRAW_HEALTH and player["health"] is not None and player["max_health"] is not None:
                    self.draw_health_bar(root_screen, player["health"], player["max_health"])
                    pyglet.text.Label(
                        f"{int(player['health'])}/{int(player['max_health'])}",
                        font_name='Arial', font_size=10,
                        x=root_screen.x, y=self.height - root_screen.y + 25,
                        anchor_x='center', color=COLOR_HEALTH_FG
                    ).draw()
        
        status = "ON" if self.aimbot.enabled else "OFF"
        pyglet.text.Label(
            f"FOV: {int(self.aimbot.fov)} | Aim: {status} | Toggle: B",
            font_name='Arial', font_size=12,
            x=10, y=self.height - 20,
            anchor_x='left', anchor_y='center',
            color=COLOR_TEXT
        ).draw()
        
        try:
            fov_circle = pyglet.shapes.Arc(
                x=self.width / 2,
                y=self.height / 2,
                radius=max(5, float(self.aimbot.fov)),
                color=(200, 200, 200),
                segments=96,
                angle=360
            )
            fov_circle.opacity = 140
            fov_circle.draw()
        except:
            self.draw_line(self.width/2 - 10, self.height/2, self.width/2 + 10, self.height/2, COLOR_TEXT)
            self.draw_line(self.width/2, self.height/2 - 10, self.width/2, self.height/2 + 10, COLOR_TEXT)

    def update(self, dt):
        try:
            self.window.invalid = True
        except:
            pass

    def run(self):
        pyglet.app.run()

def main():
    try:
        memory = RobloxMemory()
        overlay = ESPOverlay(memory)
        overlay.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

    ## lots of AI was used yes.
