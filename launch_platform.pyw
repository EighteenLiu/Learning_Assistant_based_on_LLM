import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, TOP, Button, Frame, Label, StringVar, Tk
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


def find_node_command() -> list[str] | None:
    candidates = [
        ["npm.cmd"],
        ["npm"],
        [r"C:\Program Files\nodejs\npm.cmd"],
        [r"C:\Program Files (x86)\nodejs\npm.cmd"],
    ]
    for cmd in candidates:
        try:
            subprocess.run(cmd + ["--version"], capture_output=True, text=True, timeout=8, check=True)
            return cmd
        except Exception:
            continue
    return None


class LauncherApp:
    def __init__(self):
        self.root = Tk()
        self.root.title("双语课程辅助学习平台启动器")
        self.root.geometry("1080x720")
        self.root.configure(bg="#edf4ff")
        self.backend_process: subprocess.Popen | None = None
        self.frontend_process: subprocess.Popen | None = None
        self.node_cmd = find_node_command()
        self.status_text = StringVar(value="就绪")
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        header = Frame(self.root, bg="#0f62fe", padx=20, pady=18)
        header.pack(fill="x")
        Label(
            header,
            text="双语课程辅助学习平台",
            bg="#0f62fe",
            fg="white",
            font=("Microsoft YaHei", 20, "bold"),
        ).pack(anchor="w")
        Label(
            header,
            text="一键启动前后端、打开浏览器，并在窗口中查看运行日志",
            bg="#0f62fe",
            fg="#dbeafe",
            font=("Microsoft YaHei", 10),
        ).pack(anchor="w", pady=(6, 0))

        toolbar = Frame(self.root, bg="#edf4ff", padx=20, pady=14)
        toolbar.pack(fill="x")
        Button(toolbar, text="启动后端", command=self.start_backend, width=12, bg="#1d4ed8", fg="white").pack(side=LEFT, padx=4)
        Button(toolbar, text="启动前端", command=self.start_frontend, width=12, bg="#0891b2", fg="white").pack(side=LEFT, padx=4)
        Button(toolbar, text="全部启动", command=self.start_all, width=12, bg="#0f766e", fg="white").pack(side=LEFT, padx=4)
        Button(toolbar, text="打开前端", command=lambda: webbrowser.open(FRONTEND_URL), width=12).pack(side=LEFT, padx=4)
        Button(toolbar, text="打开后端", command=lambda: webbrowser.open(BACKEND_URL), width=12).pack(side=LEFT, padx=4)
        Button(toolbar, text="停止服务", command=self.stop_all, width=12, bg="#b91c1c", fg="white").pack(side=LEFT, padx=4)

        status_bar = Frame(self.root, bg="#edf4ff", padx=20, pady=2)
        status_bar.pack(fill="x")
        Label(status_bar, text="状态：", bg="#edf4ff", fg="#334155", font=("Microsoft YaHei", 10, "bold")).pack(side=LEFT)
        Label(status_bar, textvariable=self.status_text, bg="#edf4ff", fg="#0f172a", font=("Microsoft YaHei", 10)).pack(side=LEFT)

        tips = Frame(self.root, bg="#edf4ff", padx=20, pady=2)
        tips.pack(fill="x")
        node_text = "已检测到 npm 命令" if self.node_cmd else "未检测到 npm，请安装 Node.js 后再启动前端"
        Label(tips, text=node_text, bg="#edf4ff", fg="#475569", font=("Microsoft YaHei", 9)).pack(anchor="w")

        logs = Frame(self.root, bg="#edf4ff", padx=20, pady=14)
        logs.pack(fill=BOTH, expand=True)

        left = Frame(logs, bg="#edf4ff")
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))
        Label(left, text="后端日志", bg="#edf4ff", fg="#0f172a", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.backend_output = ScrolledText(left, wrap="word", font=("Consolas", 10), bg="#0f172a", fg="#dbeafe")
        self.backend_output.pack(fill=BOTH, expand=True)

        right = Frame(logs, bg="#edf4ff")
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(8, 0))
        Label(right, text="前端日志", bg="#edf4ff", fg="#0f172a", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", pady=(0, 6))
        self.frontend_output = ScrolledText(right, wrap="word", font=("Consolas", 10), bg="#082f49", fg="#e0f2fe")
        self.frontend_output.pack(fill=BOTH, expand=True)

    def append_log(self, widget: ScrolledText, text: str):
        widget.after(0, lambda: self._append(widget, text))

    @staticmethod
    def _append(widget: ScrolledText, text: str):
        widget.insert(END, text)
        widget.see(END)

    def _stream_output(self, process: subprocess.Popen, widget: ScrolledText):
        if process.stdout is None:
            return
        for line in process.stdout:
            self.append_log(widget, line)

    def start_backend(self):
        if self.backend_process and self.backend_process.poll() is None:
            self.status_text.set("后端已在运行")
            return
        command = [sys.executable, "manage.py", "runserver", "127.0.0.1:8000"]
        self.backend_process = subprocess.Popen(
            command,
            cwd=BACKEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(
            target=self._stream_output,
            args=(self.backend_process, self.backend_output),
            daemon=True,
        ).start()
        self.status_text.set("后端启动中")

    def start_frontend(self):
        if not self.node_cmd:
            messagebox.showerror("缺少 Node.js", "未检测到 npm。请先安装 Node.js，并确保 npm 可用。")
            self.status_text.set("前端未启动：缺少 Node.js")
            return
        if self.frontend_process and self.frontend_process.poll() is None:
            self.status_text.set("前端已在运行")
            return
        command = self.node_cmd + ["run", "dev", "--", "--host", "127.0.0.1"]
        self.frontend_process = subprocess.Popen(
            command,
            cwd=FRONTEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._stream_output, args=(self.frontend_process, self.frontend_output), daemon=True).start()
        self.status_text.set("前端启动中")

    def start_all(self):
        self.start_backend()
        self.start_frontend()
        self.root.after(4000, lambda: webbrowser.open(FRONTEND_URL))

    def _terminate(self, process: subprocess.Popen | None):
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def stop_all(self):
        self._terminate(self.backend_process)
        self._terminate(self.frontend_process)
        self.status_text.set("服务已停止")

    def on_close(self):
        self.stop_all()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    os.chdir(ROOT)
    LauncherApp().run()
