import os
import sys
import winreg
from pathlib import Path

REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "NuclearHeart"

class StartupManager:
    @staticmethod
    def get_launch_command():
        base_dir = Path(__file__).resolve().parent.parent
        vbs_launcher = base_dir / "launch_silent.vbs"
        if vbs_launcher.exists():
            return f'wscript.exe "{vbs_launcher}"'

        # Fallback: pythonw.exe
        python_exe = sys.executable
        if python_exe.endswith("python.exe"):
            pythonw = python_exe.replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw):
                python_exe = pythonw

        main_py = base_dir / "app" / "main.py"
        return f'"{python_exe}" "{main_py}" --startup'

    @staticmethod
    def is_enabled():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                return bool(val)
        except WindowsError:
            return False

    @staticmethod
    def set_enabled(enable=True):
        cmd = StartupManager.get_launch_command()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                    print(f"[Autostart] Enabled startup: {cmd}")
                else:
                    try:
                        winreg.DeleteValue(key, APP_NAME)
                        print("[Autostart] Disabled startup")
                    except WindowsError:
                        pass
            return True
        except Exception as e:
            print(f"[Autostart] Failed to modify registry: {e}")
            return False
