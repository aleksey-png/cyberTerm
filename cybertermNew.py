import os
import pty
import fcntl
import termios
import struct
import select
import threading
import queue
import re
import signal
import time
import socket
import binascii
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, font, filedialog
from datetime import datetime

XTERM_COLORS={0:"#000000",1:"#800000",2:"#008000",3:"#808000",4:"#000080",5:"#800080",6:"#008080",7:"#c0c0c0",8:"#808080",9:"#ff0000",10:"#00ff00",11:"#ffff00",12:"#0000ff",13:"#ff00ff",14:"#00ffff",15:"#ffffff"}
for i in range(16,232):
    XTERM_COLORS[i]=f"#{((i-16)//36)*51:02x}{(((i-16)%36)//6)*51:02x}{((i-16)%6)*51:02x}"
for i in range(232,256):
    XTERM_COLORS[i]=f"#{(i-232)*10+8:02x}{(i-232)*10+8:02x}{(i-232)*10+8:02x}"

ANSI_REGEX=re.compile(r'(\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][0-9;]*.*?(?:\x07|\x1b\\))')

class CodeEditor(tk.Toplevel):
    def __init__(self,parent,start_path=None):
        super().__init__(parent)
        self.title("CyberEdit - Source Code Editor")
        self.geometry("1000x700")
        self.configure(bg='#080808')
        self.current_file=start_path if start_path and os.path.isfile(start_path) else None
        self.setup_ui()
        if self.current_file:
            self.load_file(self.current_file)

    def setup_ui(self):
        top_bar=tk.Frame(self,bg='#111',height=45)
        top_bar.pack(fill=tk.X,side=tk.TOP)
        tk.Label(top_bar,text="FILE:",bg='#111',fg='#44AAFF',font=('Consolas',11,'bold')).pack(side=tk.LEFT,padx=10)
        self.file_entry=tk.Entry(top_bar,bg='#222',fg='#0F0',font=('Consolas',11),relief=tk.FLAT,insertbackground='#0F0')
        self.file_entry.pack(side=tk.LEFT,fill=tk.X,expand=True,padx=5,pady=8)
        btn_open=tk.Button(top_bar,text="[O] OPEN",command=self.browse_file,bg='#333',fg='#FFF',relief=tk.FLAT,font=('Consolas',10,'bold'))
        btn_open.pack(side=tk.LEFT,padx=5)
        btn_save=tk.Button(top_bar,text="[S] SAVE",command=self.save_file,bg='#2A5A2A',fg='#4F4',relief=tk.FLAT,font=('Consolas',10,'bold'))
        btn_save.pack(side=tk.LEFT,padx=10)
        self.text_area=tk.Text(self,bg='#0C0C0C',fg='#E0E0E0',font=('Consolas',12),wrap=tk.NONE,insertbackground='#0F0',selectbackground='#353',selectforeground='#0F0')
        self.text_area.pack(fill=tk.BOTH,expand=True,padx=5,pady=5)
        self.text_area.bind('<KeyRelease>',self.syntax_highlight)
        self.keywords=["def","class","import","from","return","if","elif","else","try","except","while","for","in","and","or","not","True","False","None","print","echo","bash","sudo","apt","pacman"]
        self.text_area.tag_configure("keyword",foreground="#FF4444",font=('Consolas',12,'bold'))
        self.text_area.tag_configure("string",foreground="#44FF44")

    def browse_file(self):
        path=filedialog.askopenfilename()
        if path:
            self.load_file(path)

    def load_file(self,path):
        if os.path.exists(path):
            try:
                with open(path,'r',encoding='utf-8',errors='replace') as f:
                    content=f.read()
                self.text_area.delete(1.0,tk.END)
                self.text_area.insert(tk.END,content)
                self.file_entry.delete(0,tk.END)
                self.file_entry.insert(0,path)
                self.current_file=path
                self.syntax_highlight()
            except Exception as e:
                messagebox.showerror("Error",str(e),parent=self)

    def save_file(self):
        path=self.file_entry.get().strip()
        if not path: return
        try:
            with open(path,'w',encoding='utf-8') as f:
                f.write(self.text_area.get(1.0,tk.END).rstrip('\n'))
            self.current_file=path
            messagebox.showinfo("Saved",f"Successfully saved {path}",parent=self)
        except Exception as e:
            messagebox.showerror("Error",str(e),parent=self)

    def syntax_highlight(self,event=None):
        self.text_area.tag_remove("keyword",1.0,tk.END)
        self.text_area.tag_remove("string",1.0,tk.END)
        content=self.text_area.get(1.0,tk.END)
        for kw in self.keywords:
            idx="1.0"
            while True:
                idx=self.text_area.search(r'\b'+kw+r'\b',idx,nocase=False,regexp=True,stopindex=tk.END)
                if not idx: break
                end_idx=f"{idx}+{len(kw)}c"
                self.text_area.tag_add("keyword",idx,end_idx)
                idx=end_idx

class HexViewerTab(ttk.Frame):
    def __init__(self,notebook,close_cb):
        super().__init__(notebook)
        self.close_cb=close_cb
        self.setup_ui()

    def setup_ui(self):
        top=tk.Frame(self,bg='#111',height=40)
        top.pack(fill=tk.X,side=tk.TOP)
        tk.Label(top,text="[#] HEX VIEWER",bg='#111',fg='#A4F',font=('Consolas',11,'bold')).pack(side=tk.LEFT,padx=10)
        self.path_ent=tk.Entry(top,bg='#222',fg='#0F0',font=('Consolas',11),relief=tk.FLAT,insertbackground='#0F0')
        self.path_ent.pack(side=tk.LEFT,fill=tk.X,expand=True,padx=5)
        tk.Button(top,text="LOAD",command=self.load_hex,bg='#333',fg='#FFF',relief=tk.FLAT).pack(side=tk.LEFT,padx=5)
        tk.Button(top,text="[X] CLOSE",command=lambda:self.close_cb(self),bg='#522',fg='#F44',relief=tk.FLAT).pack(side=tk.RIGHT,padx=5)
        self.txt=tk.Text(self,bg='#0A0A0A',fg='#CCC',font=('Consolas',11),wrap=tk.NONE)
        self.txt.pack(fill=tk.BOTH,expand=True,padx=5,pady=5)

    def load_hex(self):
        path=self.path_ent.get().strip()
        if not os.path.isfile(path): return
        self.txt.delete(1.0,tk.END)
        try:
            with open(path,'rb') as f:
                offset=0
                while True:
                    chunk=f.read(16)
                    if not chunk: break
                    hex_str=" ".join(f"{b:02x}" for b in chunk)
                    ascii_str="".join(chr(b) if 32<=b<=126 else "." for b in chunk)
                    self.txt.insert(tk.END,f"{offset:08x}  {hex_str:<48}  |{ascii_str}|\n")
                    offset+=16
                    if offset>65536:
                        self.txt.insert(tk.END,"... [FILE TRUNCATED AT 64KB] ...\n")
                        break
        except Exception as e:
            self.txt.insert(tk.END,str(e))

class AdvancedTerminalTab(ttk.Frame):
    def __init__(self,notebook,name,close_callback):
        super().__init__(notebook)
        self.notebook=notebook
        self.name=name
        self.close_callback=close_callback
        self.master_fd=None
        self.slave_fd=None
        self.pid=None
        self.io_queue=queue.Queue()
        self.running=False
        self.saved_cursor_pos="1.0"
        self.reset_sgr()
        self.setup_ui()
        self.start_pty()
        self.bind_events()
        self.poll_queue()

    def setup_ui(self):
        self.font=font.Font(family="Consolas",size=11)
        self.bold_font=font.Font(family="Consolas",size=11,weight="bold")
        self.italic_font=font.Font(family="Consolas",size=11,slant="italic")
        control_frame=tk.Frame(self,bg='#141414',height=35)
        control_frame.pack(fill=tk.X,side=tk.TOP)
        tk.Label(control_frame,text=f"[~] {self.name}",bg='#141414',fg='#00FF00',font=('Consolas',10,'bold')).pack(side=tk.LEFT,padx=10)
        close_btn=tk.Button(control_frame,text="[X] CLOSE",command=lambda:self.close_callback(self),bg='#5A2A2A',fg='#FF4444',font=('Consolas',9,'bold'),relief=tk.FLAT,padx=10)
        close_btn.pack(side=tk.RIGHT,padx=5,pady=4)
        edit_btn=tk.Button(control_frame,text="[E] EDITOR",command=lambda:CodeEditor(self.winfo_toplevel(),os.path.expanduser("~")),bg='#2A5A2A',fg='#44FF44',font=('Consolas',9,'bold'),relief=tk.FLAT,padx=10)
        edit_btn.pack(side=tk.RIGHT,padx=5,pady=4)
        self.text_widget=tk.Text(self,bg='#0C0C0C',fg='#CCCCCC',insertbackground='#00FF00',font=self.font,wrap=tk.NONE,relief=tk.FLAT,padx=5,pady=5,selectbackground='#335533',selectforeground='#00FF00')
        self.text_widget.pack(fill=tk.BOTH,expand=True)
        self.v_scroll=ttk.Scrollbar(self.text_widget,orient=tk.VERTICAL,command=self.text_widget.yview)
        self.v_scroll.pack(side=tk.RIGHT,fill=tk.Y)
        self.text_widget.configure(yscrollcommand=self.v_scroll.set)
        self.text_widget.mark_set(tk.INSERT,"1.0")

    def bind_events(self):
        self.text_widget.bind("<Key>",self.handle_keypress)
        self.text_widget.bind("<Return>",lambda e:self.send_to_pty(b'\r'))
        self.text_widget.bind("<BackSpace>",lambda e:self.send_to_pty(b'\x08'))
        self.text_widget.bind("<Tab>",lambda e:self.send_to_pty(b'\t'))
        self.text_widget.bind("<Escape>",lambda e:self.send_to_pty(b'\x1b'))
        self.text_widget.bind("<Up>",lambda e:self.send_to_pty(b'\x1b[A'))
        self.text_widget.bind("<Down>",lambda e:self.send_to_pty(b'\x1b[B'))
        self.text_widget.bind("<Right>",lambda e:self.send_to_pty(b'\x1b[C'))
        self.text_widget.bind("<Left>",lambda e:self.send_to_pty(b'\x1b[D'))
        self.text_widget.bind("<Configure>",self.on_resize)
        self.text_widget.bind("<Control-c>",self.handle_ctrl_c)
        self.text_widget.bind("<Control-v>",self.handle_ctrl_v)

    def start_pty(self):
        self.master_fd,self.slave_fd=pty.openpty()
        env=os.environ.copy()
        env["TERM"]="xterm-256color"
        home_dir=os.path.expanduser("~")
        rc_path=os.path.join(home_dir,".cyberterm_rc")
        try:
            with open(rc_path,"w") as f:
                f.write("if [ -f ~/.bashrc ]; then . ~/.bashrc; fi\n")
                f.write("function edit() { if [ -z \"$1\" ]; then printf \"\\033]99;edit;\\007\"; else printf \"\\033]99;edit;%s\\007\" \"$(realpath $1)\"; fi; }\n")
        except: pass
        self.pid=os.fork()
        if self.pid==0:
            os.setsid()
            os.close(self.master_fd)
            os.dup2(self.slave_fd,0)
            os.dup2(self.slave_fd,1)
            os.dup2(self.slave_fd,2)
            if self.slave_fd>2: os.close(self.slave_fd)
            os.chdir(home_dir)
            shell=env.get("SHELL","/bin/bash")
            os.execvpe(shell,[shell,"--rcfile",rc_path],env)
        else:
            os.close(self.slave_fd)
            self.running=True
            threading.Thread(target=self.pty_read_loop,daemon=True).start()

    def pty_read_loop(self):
        while self.running:
            try:
                r,_,_=select.select([self.master_fd],[],[],0.1)
                if self.master_fd in r:
                    data=os.read(self.master_fd,16384)
                    if not data: break
                    self.io_queue.put(data)
            except OSError: break
        self.io_queue.put(b"EOF")

    def poll_queue(self):
        try:
            while True:
                data=self.io_queue.get_nowait()
                if data==b"EOF":
                    self.text_widget.insert(tk.END,"\n[Session Terminated]\n")
                    return
                self.process_ansi(data)
                self.text_widget.see(tk.END)
        except queue.Empty: pass
        if self.running: self.after(10,self.poll_queue)

    def process_ansi(self,data):
        text=data.decode('utf-8',errors='replace')
        parts=ANSI_REGEX.split(text)
        for part in parts:
            if not part: continue
            if part.startswith('\x1b['): self.handle_ansi_code(part)
            elif part.startswith('\x1b]99;edit;'):
                filename=part.split(';')[2].strip('\x07').strip('\x1b\\')
                if not filename: filename=None
                CodeEditor(self.winfo_toplevel(),filename)
            elif part.startswith('\x1b]'): pass
            else: self.insert_text(part)

    def write_char(self,char):
        idx=self.text_widget.index(tk.INSERT)
        line_end=self.text_widget.index(f"{idx} lineend")
        if self.text_widget.compare(idx,"<",line_end):
            self.text_widget.delete(idx)
        self.text_widget.insert(idx,char,self.get_current_tag())

    def insert_text(self,text):
        i=0
        while i<len(text):
            char=text[i]
            if char=='\r':
                self.text_widget.mark_set(tk.INSERT,f"{self.text_widget.index(tk.INSERT)} linestart")
            elif char=='\b':
                idx=self.text_widget.index(tk.INSERT)
                if self.text_widget.compare(idx,">",f"{idx} linestart"):
                    self.text_widget.mark_set(tk.INSERT,f"{idx} - 1 chars")
            elif char=='\n':
                self.text_widget.insert(tk.INSERT,'\n')
            elif char=='\x07': pass
            else: self.write_char(char)
            i+=1

    def handle_ansi_code(self,code):
        cmd=code[-1]
        params=code[2:-1].split(';')
        if params==['']: params=[]
        if cmd=='m': self.update_sgr(params)
        elif cmd=='K':
            mode=int(params[0]) if params else 0
            idx=self.text_widget.index(tk.INSERT)
            if mode==0: self.text_widget.delete(idx,f"{idx} lineend")
            elif mode==1: self.text_widget.delete(f"{idx} linestart",idx)
            elif mode==2: self.text_widget.delete(f"{idx} linestart",f"{idx} lineend")
        elif cmd=='J':
            mode=int(params[0]) if params else 0
            idx=self.text_widget.index(tk.INSERT)
            if mode==0: self.text_widget.delete(idx,tk.END)
            elif mode==1: self.text_widget.delete("1.0",idx)
            elif mode==2 or mode==3:
                self.text_widget.delete("1.0",tk.END)
                self.text_widget.mark_set(tk.INSERT,"1.0")
        elif cmd=='s': self.saved_cursor_pos=self.text_widget.index(tk.INSERT)
        elif cmd=='u': self.text_widget.mark_set(tk.INSERT,self.saved_cursor_pos)
        elif cmd in ['H','f']:
            row=max(1,int(params[0]) if len(params)>0 and params[0] else 1)
            col=max(1,int(params[1]) if len(params)>1 and params[1] else 1)
            num_lines=int(float(self.text_widget.index('end-1c')))
            if row>num_lines:
                self.text_widget.insert(tk.END,'\n'*(row-num_lines))
            line_len=len(self.text_widget.get(f"{row}.0",f"{row}.end"))
            if col>line_len+1:
                self.text_widget.insert(f"{row}.end",' '*(col-line_len-1))
            self.text_widget.mark_set(tk.INSERT,f"{row}.{col-1}")
        elif cmd=='A':
            n=int(params[0]) if params else 1
            self.text_widget.mark_set(tk.INSERT,f"{self.text_widget.index(tk.INSERT)} - {n} lines")
        elif cmd=='B':
            n=int(params[0]) if params else 1
            self.text_widget.mark_set(tk.INSERT,f"{self.text_widget.index(tk.INSERT)} + {n} lines")
        elif cmd=='C':
            n=int(params[0]) if params else 1
            self.text_widget.mark_set(tk.INSERT,f"{self.text_widget.index(tk.INSERT)} + {n} chars")
        elif cmd=='D':
            n=int(params[0]) if params else 1
            self.text_widget.mark_set(tk.INSERT,f"{self.text_widget.index(tk.INSERT)} - {n} chars")

    def update_sgr(self,params):
        if not params: self.reset_sgr(); return
        i=0
        while i<len(params):
            p=int(params[i]) if params[i] else 0
            if p==0: self.reset_sgr()
            elif p==1: self.bold=True
            elif p==3: self.italic=True
            elif p==4: self.underline=True
            elif p==7: self.inverse=True
            elif p==22: self.bold=False
            elif 30<=p<=37: self.current_fg=XTERM_COLORS[p-30]
            elif 40<=p<=47: self.current_bg=XTERM_COLORS[p-40]
            elif p==38:
                if len(params)>i+2 and params[i+1]=='5': self.current_fg=XTERM_COLORS.get(int(params[i+2]),"#CCC"); i+=2
                elif len(params)>i+4 and params[i+1]=='2': self.current_fg=f"#{int(params[i+2]):02x}{int(params[i+3]):02x}{int(params[i+4]):02x}"; i+=4
            elif p==48:
                if len(params)>i+2 and params[i+1]=='5': self.current_bg=XTERM_COLORS.get(int(params[i+2]),"#0C0C0C"); i+=2
                elif len(params)>i+4 and params[i+1]=='2': self.current_bg=f"#{int(params[i+2]):02x}{int(params[i+3]):02x}{int(params[i+4]):02x}"; i+=4
            elif p==39: self.current_fg=None
            elif p==49: self.current_bg=None
            elif 90<=p<=97: self.current_fg=XTERM_COLORS[p-90+8]
            elif 100<=p<=107: self.current_bg=XTERM_COLORS[p-100+8]
            i+=1

    def reset_sgr(self):
        self.current_fg,self.current_bg=None,None
        self.bold,self.italic,self.underline,self.inverse=False,False,False,False

    def get_current_tag(self):
        if not any([self.current_fg,self.current_bg,self.bold,self.italic,self.underline,self.inverse]): return ()
        tag_name=f"T_{self.current_fg}_{self.current_bg}_{self.bold}_{self.italic}_{self.underline}_{self.inverse}"
        fg=self.current_fg or '#CCCCCC'
        bg=self.current_bg or '#0C0C0C'
        if self.inverse: fg,bg=bg,fg
        font_obj=self.bold_font if self.bold else self.italic_font if self.italic else self.font
        self.text_widget.tag_configure(tag_name,foreground=fg,background=bg,font=font_obj,underline=self.underline)
        return (tag_name,)

    def send_to_pty(self,data):
        if self.master_fd and self.running:
            try: os.write(self.master_fd,data)
            except OSError: pass
        return "break"

    def handle_keypress(self,event):
        if not self.running: return "break"
        if event.char and not event.state&0x0004: self.send_to_pty(event.char.encode('utf-8'))
        return "break"

    def handle_ctrl_c(self,event):
        if not self.text_widget.tag_ranges("sel"): self.send_to_pty(b'\x03')
        return "break"

    def handle_ctrl_v(self,event):
        try: self.send_to_pty(self.clipboard_get().encode('utf-8'))
        except: pass
        return "break"

    def on_resize(self,event):
        if not self.master_fd or not self.running: return
        cols=max(1,event.width//self.font.measure('0'))
        rows=max(1,event.height//self.font.metrics('linespace'))
        try: fcntl.ioctl(self.master_fd,termios.TIOCSWINSZ,struct.pack("HHHH",rows,cols,0,0))
        except: pass

    def stop(self):
        self.running=False
        if self.pid:
            try: os.kill(self.pid,signal.SIGKILL); os.waitpid(self.pid,0)
            except: pass
        if self.master_fd:
            try: os.close(self.master_fd)
            except: pass

class AdvancedToolTab(ttk.Frame):
    def __init__(self,notebook,tool_name,config,close_callback):
        super().__init__(notebook)
        self.notebook=notebook
        self.tool_name=tool_name
        self.config=config
        self.close_callback=close_callback
        self.running=False
        self.io_queue=queue.Queue()
        self.setup_ui()

    def setup_ui(self):
        control_frame=tk.Frame(self,bg='#141414',height=35)
        control_frame.pack(fill=tk.X,side=tk.TOP)
        tk.Label(control_frame,text=f"[*] TOOL: {self.tool_name}",bg='#141414',fg='#AA44FF',font=('Consolas',10,'bold')).pack(side=tk.LEFT,padx=10)
        tk.Button(control_frame,text="[X] CLOSE",command=lambda:self.close_callback(self),bg='#5A2A2A',fg='#FF4444',font=('Consolas',9,'bold'),relief=tk.FLAT).pack(side=tk.RIGHT,padx=5,pady=4)
        top_frame=tk.Frame(self,bg='#141414')
        top_frame.pack(fill=tk.X)
        tk.Label(top_frame,text=self.config['description'],bg='#141414',fg='#888888',font=('Consolas',10)).pack(pady=5)
        params_frame=tk.Frame(top_frame,bg='#141414')
        params_frame.pack(pady=5)
        self.entries={}
        for param in self.config.get('params',[]):
            row=tk.Frame(params_frame,bg='#141414')
            row.pack(pady=2,fill=tk.X)
            tk.Label(row,text=f"{param['name']}:",bg='#141414',fg='#44AAFF',width=20,anchor='e').pack(side=tk.LEFT,padx=5)
            ent=tk.Entry(row,bg='#1E1E1E',fg='#00FF00',insertbackground='#00FF00',width=60)
            ent.insert(0,param['default'])
            ent.pack(side=tk.LEFT,padx=5)
            self.entries[param['key']]=ent
        btn_frame=tk.Frame(top_frame,bg='#141414')
        btn_frame.pack(pady=10)
        self.btn_run=tk.Button(btn_frame,text="[>] EXECUTE",command=self.run_tool,bg='#2A5A2A',fg='#44FF44',relief=tk.FLAT,padx=20)
        self.btn_run.pack(side=tk.LEFT,padx=5)
        self.btn_stop=tk.Button(btn_frame,text="[#] TERMINATE",command=self.stop_tool,bg='#5A2A2A',fg='#FF4444',relief=tk.FLAT,padx=20,state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT,padx=5)
        tk.Button(btn_frame,text="[C] CLEAR",command=lambda:self.out_text.delete(1.0,tk.END),bg='#333',fg='#DDD',relief=tk.FLAT,padx=20).pack(side=tk.LEFT,padx=5)
        self.out_text=tk.Text(self,bg='#0A0A0A',fg='#CCCCCC',font=('Consolas',11),wrap=tk.WORD,relief=tk.FLAT,padx=10,pady=10)
        self.out_text.pack(fill=tk.BOTH,expand=True)

    def run_tool(self):
        if self.running: return
        cmd=self.config['build_cmd']({k:v.get() for k,v in self.entries.items()})
        self.btn_run.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.out_text.insert(tk.END,f"\n$ {cmd}\n{'-'*60}\n","header")
        self.out_text.tag_configure("header",foreground="#44AAFF")
        self.running=True
        threading.Thread(target=self.process_runner,args=(cmd,),daemon=True).start()
        self.poll_queue()

    def process_runner(self,cmd):
        try: self.current_process=pty.spawn(['/bin/bash','-c',cmd],lambda fd:self.io_queue.put(os.read(fd,4096)) or b"")
        except: pass
        finally: self.io_queue.put(b"EOF")

    def poll_queue(self):
        try:
            while True:
                data=self.io_queue.get_nowait()
                if data==b"EOF":
                    self.running=False
                    self.btn_run.config(state=tk.NORMAL)
                    self.btn_stop.config(state=tk.DISABLED)
                    return
                self.out_text.insert(tk.END,re.sub(r'\x1b\[[0-9;]*[mK]','',data.decode('utf-8',errors='replace')))
                self.out_text.see(tk.END)
        except queue.Empty: pass
        if self.running: self.after(50,self.poll_queue)

    def stop_tool(self):
        self.running=False
        try: os.system(f"pkill -P {os.getpid()}")
        except: pass
    def stop(self): self.stop_tool()

MASSIVE_TOOLS = {
    "Nmap SYN Scan":{"cat":"Network Recon","desc":"Stealth SYN Scan","params":[{"name":"Target","key":"t","default":"127.0.0.1"}],"build_cmd":lambda p:f"sudo nmap -sS {p['t']}"},
    "Nmap Version Det":{"cat":"Network Recon","desc":"Service version detection","params":[{"name":"Target","key":"t","default":"127.0.0.1"}],"build_cmd":lambda p:f"nmap -sV {p['t']}"},
    "Nmap OS Det":{"cat":"Network Recon","desc":"OS detection","params":[{"name":"Target","key":"t","default":"127.0.0.1"}],"build_cmd":lambda p:f"sudo nmap -O {p['t']}"},
    "Nmap Aggressive":{"cat":"Network Recon","desc":"Aggressive scan (-A)","params":[{"name":"Target","key":"t","default":"127.0.0.1"}],"build_cmd":lambda p:f"nmap -A {p['t']}"},
    "Nmap All Ports":{"cat":"Network Recon","desc":"Scan all 65535 ports","params":[{"name":"Target","key":"t","default":"127.0.0.1"}],"build_cmd":lambda p:f"nmap -p- -T4 {p['t']}"},
    "Nmap UDP Scan":{"cat":"Network Recon","desc":"Scan UDP ports","params":[{"name":"Target","key":"t","default":"127.0.0.1"},{"name":"Ports","key":"p","default":"53,161,137"}],"build_cmd":lambda p:f"sudo nmap -sU -p {p['p']} {p['t']}"},
    "Nmap Ping Sweep":{"cat":"Network Recon","desc":"Discover alive hosts","params":[{"name":"Subnet","key":"s","default":"192.168.1.0/24"}],"build_cmd":lambda p:f"nmap -sn {p['s']}"},
    "Gobuster Dir":{"cat":"Web Recon","desc":"Directory brute-forcing","params":[{"name":"URL","key":"u","default":"http://example.com"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/dirb/common.txt"}],"build_cmd":lambda p:f"gobuster dir -u {p['u']} -w {p['w']}"},
    "Gobuster DNS":{"cat":"Web Recon","desc":"Subdomain enum","params":[{"name":"Domain","key":"d","default":"example.com"},{"name":"Wordlist","key":"w","default":"/usr/share/seclists/Discovery/DNS/subdomains-top1million-110000.txt"}],"build_cmd":lambda p:f"gobuster dns -d {p['d']} -w {p['w']}"},
    "Gobuster VHost":{"cat":"Web Recon","desc":"VHost enum","params":[{"name":"URL","key":"u","default":"http://example.com"},{"name":"Wordlist","key":"w","default":"/usr/share/seclists/Discovery/DNS/subdomains-top1million-110000.txt"}],"build_cmd":lambda p:f"gobuster vhost -u {p['u']} -w {p['w']}"},
    "SQLMap Basic":{"cat":"Web Exploitation","desc":"Test URL for SQLi","params":[{"name":"URL","key":"u","default":"http://test.com?id=1"}],"build_cmd":lambda p:f"sqlmap -u '{p['u']}' --batch --dbs"},
    "SQLMap Forms":{"cat":"Web Exploitation","desc":"Test forms for SQLi","params":[{"name":"URL","key":"u","default":"http://test.com"}],"build_cmd":lambda p:f"sqlmap -u '{p['u']}' --forms --batch"},
    "SQLMap Dump":{"cat":"Web Exploitation","desc":"Dump DB table","params":[{"name":"URL","key":"u","default":"http://test.com?id=1"},{"name":"DB","key":"d","default":"db_name"},{"name":"Table","key":"t","default":"users"}],"build_cmd":lambda p:f"sqlmap -u '{p['u']}' -D {p['d']} -T {p['t']} --dump --batch"},
    "Hydra SSH":{"cat":"Brute Force","desc":"SSH Brute Force","params":[{"name":"Target","key":"t","default":"192.168.1.1"},{"name":"User","key":"u","default":"root"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/rockyou.txt"}],"build_cmd":lambda p:f"hydra -l {p['u']} -P {p['w']} ssh://{p['t']}"},
    "Hydra FTP":{"cat":"Brute Force","desc":"FTP Brute Force","params":[{"name":"Target","key":"t","default":"192.168.1.1"},{"name":"User","key":"u","default":"admin"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/rockyou.txt"}],"build_cmd":lambda p:f"hydra -l {p['u']} -P {p['w']} ftp://{p['t']}"},
    "Hydra RDP":{"cat":"Brute Force","desc":"RDP Brute Force","params":[{"name":"Target","key":"t","default":"192.168.1.1"},{"name":"User","key":"u","default":"Administrator"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/rockyou.txt"}],"build_cmd":lambda p:f"hydra -l {p['u']} -P {p['w']} rdp://{p['t']}"},
    "Nikto Scan":{"cat":"Web Recon","desc":"Web server scanner","params":[{"name":"Host","key":"h","default":"http://example.com"}],"build_cmd":lambda p:f"nikto -h {p['h']}"},
    "WPScan Basic":{"cat":"Web Recon","desc":"WordPress Scanner","params":[{"name":"URL","key":"u","default":"http://example.com"}],"build_cmd":lambda p:f"wpscan --url {p['u']} --enumerate u"},
    "WPScan Plugins":{"cat":"Web Recon","desc":"WP Vulnerable Plugins","params":[{"name":"URL","key":"u","default":"http://example.com"}],"build_cmd":lambda p:f"wpscan --url {p['u']} --enumerate vp"},
    "Amass Enum":{"cat":"OSINT","desc":"Attack Surface Mapping","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"amass enum -d {p['d']}"},
    "FFuF Web":{"cat":"Web Recon","desc":"Fast web fuzzer","params":[{"name":"Target (use FUZZ)","key":"t","default":"http://example.com/FUZZ"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/dirb/common.txt"}],"build_cmd":lambda p:f"ffuf -u {p['t']} -w {p['w']}"},
    "Netcat Listener":{"cat":"Network Exploitation","desc":"Reverse shell catcher","params":[{"name":"Port","key":"p","default":"4444"}],"build_cmd":lambda p:f"nc -lvnp {p['p']}"},
    "Netcat Connect":{"cat":"Network Exploitation","desc":"Connect to port","params":[{"name":"Target","key":"t","default":"127.0.0.1"},{"name":"Port","key":"p","default":"4444"}],"build_cmd":lambda p:f"nc {p['t']} {p['p']}"},
    "Whois Lookup":{"cat":"OSINT","desc":"Domain registry info","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"whois {p['d']}"},
    "TheHarvester":{"cat":"OSINT","desc":"Emails & Domains","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"theHarvester -d {p['d']} -b all"},
    "Sherlock":{"cat":"OSINT","desc":"Social media accounts","params":[{"name":"Username","key":"u","default":"johndoe"}],"build_cmd":lambda p:f"sherlock {p['u']}"},
    "ExifTool":{"cat":"Forensics","desc":"Read file metadata","params":[{"name":"File Path","key":"f","default":"image.jpg"}],"build_cmd":lambda p:f"exiftool {p['f']}"},
    "Binwalk Extract":{"cat":"Forensics","desc":"Extract firmware","params":[{"name":"File Path","key":"f","default":"firmware.bin"}],"build_cmd":lambda p:f"binwalk -e {p['f']}"},
    "Strings":{"cat":"Forensics","desc":"Find printable strings","params":[{"name":"File Path","key":"f","default":"binary_file"}],"build_cmd":lambda p:f"strings {p['f']}"},
    "Curl Headers":{"cat":"Web Recon","desc":"Fetch HTTP Headers","params":[{"name":"URL","key":"u","default":"https://example.com"}],"build_cmd":lambda p:f"curl -I {p['u']}"},
    "Curl Fetch":{"cat":"Web Recon","desc":"Fetch HTTP Content","params":[{"name":"URL","key":"u","default":"https://example.com"}],"build_cmd":lambda p:f"curl -s {p['u']}"},
    "Wget Mirror":{"cat":"Web Recon","desc":"Mirror a website","params":[{"name":"URL","key":"u","default":"https://example.com"}],"build_cmd":lambda p:f"wget -m -k -K -E {p['u']}"},
    "SS Local Ports":{"cat":"System","desc":"Show listening ports","params":[],"build_cmd":lambda p:"ss -tulpn | grep LISTEN"},
    "Top Processes":{"cat":"System","desc":"Resource Monitor","params":[],"build_cmd":lambda p:"top -b -n 1 | head -n 20"},
    "HTop Batch":{"cat":"System","desc":"Process list batch","params":[],"build_cmd":lambda p:"htop -b -n 1"},
    "Df Disk Usage":{"cat":"System","desc":"Disk usage stats","params":[],"build_cmd":lambda p:"df -h"},
    "Free Memory":{"cat":"System","desc":"Memory usage stats","params":[],"build_cmd":lambda p:"free -h"},
    "Uname System":{"cat":"System","desc":"Kernel info","params":[],"build_cmd":lambda p:"uname -a"},
    "IP Addr":{"cat":"System","desc":"Network interfaces","params":[],"build_cmd":lambda p:"ip addr show"},
    "Route Table":{"cat":"System","desc":"IP routing table","params":[],"build_cmd":lambda p:"ip route"},
    "ARP Table":{"cat":"System","desc":"ARP cache","params":[],"build_cmd":lambda p:"arp -a"},
    "Ping Target":{"cat":"Network Recon","desc":"ICMP Echo","params":[{"name":"Target","key":"t","default":"8.8.8.8"}],"build_cmd":lambda p:f"ping -c 4 {p['t']}"},
    "Traceroute":{"cat":"Network Recon","desc":"Trace network path","params":[{"name":"Target","key":"t","default":"8.8.8.8"}],"build_cmd":lambda p:f"traceroute {p['t']}"},
    "Dig DNS":{"cat":"Network Recon","desc":"DNS lookup","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"dig {p['d']}"},
    "Host Lookup":{"cat":"Network Recon","desc":"Host to IP","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"host {p['d']}"},
    "Nslookup":{"cat":"Network Recon","desc":"Name server query","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"nslookup {p['d']}"},
    "Tcpdump Basic":{"cat":"Network Sniffing","desc":"Sniff packets on intf","params":[{"name":"Interface","key":"i","default":"eth0"}],"build_cmd":lambda p:f"sudo tcpdump -i {p['i']} -c 20"},
    "Tcpdump Port":{"cat":"Network Sniffing","desc":"Sniff on port","params":[{"name":"Interface","key":"i","default":"eth0"},{"name":"Port","key":"p","default":"80"}],"build_cmd":lambda p:f"sudo tcpdump -i {p['i']} port {p['p']} -c 20"},
    "Tshark CLI":{"cat":"Network Sniffing","desc":"Wireshark CLI","params":[{"name":"Interface","key":"i","default":"eth0"}],"build_cmd":lambda p:f"sudo tshark -i {p['i']} -c 20"},
    "Aircrack-ng Test":{"cat":"Wireless","desc":"Test injection","params":[{"name":"Interface","key":"i","default":"wlan0mon"}],"build_cmd":lambda p:f"sudo aireplay-ng --test {p['i']}"},
    "Airodump-ng":{"cat":"Wireless","desc":"Capture 802.11 frames","params":[{"name":"Interface","key":"i","default":"wlan0mon"}],"build_cmd":lambda p:f"sudo airodump-ng {p['i']}"},
    "Macchanger":{"cat":"Wireless","desc":"Spoof MAC Address","params":[{"name":"Interface","key":"i","default":"wlan0"}],"build_cmd":lambda p:f"sudo macchanger -r {p['i']}"},
    "John The Ripper":{"cat":"Cracking","desc":"Crack password hashes","params":[{"name":"Hash File","key":"f","default":"hash.txt"}],"build_cmd":lambda p:f"john {p['f']}"},
    "Hashcat MD5":{"cat":"Cracking","desc":"Crack MD5 hashes","params":[{"name":"Hash File","key":"f","default":"hash.txt"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/rockyou.txt"}],"build_cmd":lambda p:f"hashcat -m 0 -a 0 {p['f']} {p['w']}"},
    "Medusa SSH":{"cat":"Brute Force","desc":"Parallel login brute force","params":[{"name":"Target","key":"t","default":"192.168.1.1"},{"name":"User","key":"u","default":"root"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/rockyou.txt"}],"build_cmd":lambda p:f"medusa -h {p['t']} -u {p['u']} -P {p['w']} -M ssh"},
    "Dirb Basic":{"cat":"Web Recon","desc":"Web Content Scanner","params":[{"name":"URL","key":"u","default":"http://example.com"}],"build_cmd":lambda p:f"dirb {p['u']}"},
    "Wfuzz Basic":{"cat":"Web Recon","desc":"Web fuzzer","params":[{"name":"URL (use FUZZ)","key":"u","default":"http://example.com/FUZZ"},{"name":"Wordlist","key":"w","default":"/usr/share/wordlists/dirb/common.txt"}],"build_cmd":lambda p:f"wfuzz -c -z file,{p['w']} --hc 404 {p['u']}"},
    "Cewl Spider":{"cat":"Web Recon","desc":"Custom wordlist gen","params":[{"name":"URL","key":"u","default":"http://example.com"}],"build_cmd":lambda p:f"cewl -d 2 -m 5 -w wordlist.txt {p['u']}; cat wordlist.txt"},
    "Searchsploit":{"cat":"Exploitation","desc":"Exploit DB Search","params":[{"name":"Search Term","key":"s","default":"wordpress"}],"build_cmd":lambda p:f"searchsploit {p['s']}"},
    "Metasploit CLI":{"cat":"Exploitation","desc":"MSFConsole launch","params":[],"build_cmd":lambda p:"msfconsole -q"},
    "Msfvenom RevShell":{"cat":"Payload Gen","desc":"Generate Reverse Shell","params":[{"name":"LHOST","key":"lh","default":"192.168.1.10"},{"name":"LPORT","key":"lp","default":"4444"},{"name":"Format","key":"f","default":"elf"}],"build_cmd":lambda p:f"msfvenom -p linux/x86/meterpreter/reverse_tcp LHOST={p['lh']} LPORT={p['lp']} -f {p['f']} -o payload.{p['f']}"},
    "GPG Encrypt":{"cat":"Crypto","desc":"Encrypt file","params":[{"name":"File","key":"f","default":"secret.txt"},{"name":"Recipient","key":"r","default":"user@email.com"}],"build_cmd":lambda p:f"gpg -e -r {p['r']} {p['f']}"},
    "GPG Decrypt":{"cat":"Crypto","desc":"Decrypt file","params":[{"name":"File","key":"f","default":"secret.txt.gpg"}],"build_cmd":lambda p:f"gpg -d {p['f']}"},
    "OpenSSL MD5":{"cat":"Crypto","desc":"MD5 Hash","params":[{"name":"File","key":"f","default":"file.txt"}],"build_cmd":lambda p:f"openssl md5 {p['f']}"},
    "OpenSSL SHA256":{"cat":"Crypto","desc":"SHA256 Hash","params":[{"name":"File","key":"f","default":"file.txt"}],"build_cmd":lambda p:f"openssl sha256 {p['f']}"},
    "Base64 Encode":{"cat":"Crypto","desc":"Encode file to Base64","params":[{"name":"File","key":"f","default":"file.txt"}],"build_cmd":lambda p:f"base64 {p['f']}"},
    "Base64 Decode":{"cat":"Crypto","desc":"Decode Base64 file","params":[{"name":"File","key":"f","default":"file.b64"}],"build_cmd":lambda p:f"base64 -d {p['f']}"},
    "Steghide Embed":{"cat":"Steganography","desc":"Hide file in image","params":[{"name":"Cover Image","key":"c","default":"cover.jpg"},{"name":"Secret File","key":"s","default":"secret.txt"}],"build_cmd":lambda p:f"steghide embed -cf {p['c']} -ef {p['s']}"},
    "Steghide Extract":{"cat":"Steganography","desc":"Extract from image","params":[{"name":"Stego Image","key":"s","default":"stego.jpg"}],"build_cmd":lambda p:f"steghide extract -sf {p['s']}"},
    "Outguess Embed":{"cat":"Steganography","desc":"Universal stego tool","params":[{"name":"Cover Image","key":"c","default":"cover.jpg"},{"name":"Secret File","key":"s","default":"secret.txt"}],"build_cmd":lambda p:f"outguess -d {p['s']} {p['c']} out.jpg"},
    "Zsteg Basic":{"cat":"Steganography","desc":"Detect LSB stego in PNG","params":[{"name":"Image","key":"i","default":"image.png"}],"build_cmd":lambda p:f"zsteg {p['i']}"},
    "Netdiscover":{"cat":"Network Recon","desc":"ARP Scanner","params":[{"name":"Interface","key":"i","default":"eth0"},{"name":"Range","key":"r","default":"192.168.1.0/24"}],"build_cmd":lambda p:f"sudo netdiscover -i {p['i']} -r {p['r']}"},
    "Masscan Basic":{"cat":"Network Recon","desc":"Fast port scanner","params":[{"name":"Target","key":"t","default":"192.168.1.0/24"},{"name":"Ports","key":"p","default":"80,443"}],"build_cmd":lambda p:f"sudo masscan -p{p['p']} {p['t']} --rate=1000"},
    "Dmitry Basic":{"cat":"OSINT","desc":"Deepmagic Info Gathering","params":[{"name":"Domain","key":"d","default":"example.com"}],"build_cmd":lambda p:f"dmitry -winse {p['d']}"},
    "Recon-ng CLI":{"cat":"OSINT","desc":"Web Recon framework","params":[],"build_cmd":lambda p:"recon-ng"},
    "Maltego CE":{"cat":"OSINT","desc":"Link analysis (Requires GUI)","params":[],"build_cmd":lambda p:"maltego"},
    "Wireshark GUI":{"cat":"Network Sniffing","desc":"Network analyzer (Requires GUI)","params":[],"build_cmd":lambda p:"wireshark"},
    "Burp Suite":{"cat":"Web Exploitation","desc":"Web proxy (Requires GUI)","params":[],"build_cmd":lambda p:"burpsuite"},
    "Owasp ZAP":{"cat":"Web Exploitation","desc":"Web scanner (Requires GUI)","params":[],"build_cmd":lambda p:"zaproxy"},
    "Ghidra Run":{"cat":"Reverse Engineering","desc":"SRE framework (Requires GUI)","params":[],"build_cmd":lambda p:"ghidra"},
    "Radare2 Basic":{"cat":"Reverse Engineering","desc":"CLI Reverse Eng framework","params":[{"name":"Binary","key":"b","default":"./a.out"}],"build_cmd":lambda p:f"r2 {p['b']}"},
    "Objdump Disasm":{"cat":"Reverse Engineering","desc":"Disassemble binary","params":[{"name":"Binary","key":"b","default":"./a.out"}],"build_cmd":lambda p:f"objdump -d {p['b']} | head -n 50"},
    "Ltrace Basic":{"cat":"Reverse Engineering","desc":"Library call tracer","params":[{"name":"Binary","key":"b","default":"./a.out"}],"build_cmd":lambda p:f"ltrace {p['b']}"},
    "Strace Basic":{"cat":"Reverse Engineering","desc":"System call tracer","params":[{"name":"Binary","key":"b","default":"./a.out"}],"build_cmd":lambda p:f"strace {p['b']} 2>&1 | head -n 50"},
    "Chkrootkit":{"cat":"System Security","desc":"Check for rootkits","params":[],"build_cmd":lambda p:"sudo chkrootkit"},
    "Rkhunter Check":{"cat":"System Security","desc":"Rootkit Hunter","params":[],"build_cmd":lambda p:"sudo rkhunter --check --sk"},
    "Lynis Audit":{"cat":"System Security","desc":"Security auditing tool","params":[],"build_cmd":lambda p:"sudo lynis audit system"},
    "ClamAV Scan":{"cat":"System Security","desc":"Antivirus scan dir","params":[{"name":"Directory","key":"d","default":"/home"}],"build_cmd":lambda p:f"clamscan -r {p['d']}"},
    "Iptables List":{"cat":"Firewall","desc":"List current rules","params":[],"build_cmd":lambda p:"sudo iptables -L -n -v"},
    "Ufw Status":{"cat":"Firewall","desc":"Uncomplicated Firewall","params":[],"build_cmd":lambda p:"sudo ufw status verbose"},
    "Fail2ban Status":{"cat":"System Security","desc":"Intrusion prevention","params":[{"name":"Jail","key":"j","default":"sshd"}],"build_cmd":lambda p:f"sudo fail2ban-client status {p['j']}"},
    "Docker PS":{"cat":"DevOps","desc":"List running containers","params":[],"build_cmd":lambda p:"docker ps"},
    "Docker Images":{"cat":"DevOps","desc":"List docker images","params":[],"build_cmd":lambda p:"docker images"},
    "Kubectl Get Pods":{"cat":"DevOps","desc":"K8s list pods","params":[],"build_cmd":lambda p:"kubectl get pods --all-namespaces"},
    "Git Status":{"cat":"DevOps","desc":"Repo status","params":[],"build_cmd":lambda p:"git status"},
    "Git Log":{"cat":"DevOps","desc":"Commit history","params":[],"build_cmd":lambda p:"git log --oneline -n 10"},
    "Python Server":{"cat":"Utility","desc":"Simple HTTP Server","params":[{"name":"Port","key":"p","default":"8000"}],"build_cmd":lambda p:f"python3 -m http.server {p['p']}"},
    "Tar Extract":{"cat":"Utility","desc":"Extract tar.gz","params":[{"name":"Archive","key":"a","default":"archive.tar.gz"}],"build_cmd":lambda p:f"tar -xzvf {p['a']}"},
    "Zip Extract":{"cat":"Utility","desc":"Extract zip","params":[{"name":"Archive","key":"a","default":"archive.zip"}],"build_cmd":lambda p:f"unzip {p['a']}"}
}

class CyberTermEngine(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🔥 CyberTerm v12.0 - Ultimate Security Edition")
        self.geometry("1500x950")
        self.configure(bg='#080808')
        style=ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook',background='#080808',borderwidth=0)
        style.configure('TNotebook.Tab',background='#141414',foreground='#555555',padding=[20,10],font=('Consolas',11,'bold'))
        style.map('TNotebook.Tab',background=[('selected','#222222')],foreground=[('selected','#00FF00')])
        self.tabs=[]
        self.tab_count=0
        self.setup_layout()
        self.add_terminal()

    def setup_layout(self):
        header=tk.Frame(self,bg='#080808',height=60)
        header.pack(fill=tk.X,padx=10,pady=5)
        tk.Label(header,text="🔥 CyberTerm v12.0",bg='#080808',fg='#44AAFF',font=('Consolas',16,'bold')).pack(side=tk.LEFT,padx=10)
        tk.Button(header,text="[+] NEW TERMINAL",command=self.add_terminal,bg='#111',fg='#0F0',font=('Consolas',10,'bold'),relief=tk.FLAT,padx=15).pack(side=tk.RIGHT,padx=5)
        tk.Button(header,text="[#] HEX VIEWER",command=self.add_hex_viewer,bg='#111',fg='#FF4',font=('Consolas',10,'bold'),relief=tk.FLAT,padx=15).pack(side=tk.RIGHT,padx=5)
        tk.Button(header,text="[S] SCRIPT EDITOR",command=lambda:CodeEditor(self),bg='#111',fg='#F44',font=('Consolas',10,'bold'),relief=tk.FLAT,padx=15).pack(side=tk.RIGHT,padx=5)
        tk.Button(header,text="[T] TOOLS MENU",command=self.show_tools,bg='#111',fg='#A4F',font=('Consolas',10,'bold'),relief=tk.FLAT,padx=15).pack(side=tk.RIGHT,padx=5)
        self.notebook=ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH,expand=True,padx=5,pady=5)
        
    def add_terminal(self):
        self.tab_count+=1
        tab=AdvancedTerminalTab(self.notebook,f"Shell-{self.tab_count}",self.close_tab)
        self.notebook.add(tab,text=f" 💻 Shell-{self.tab_count} ")
        self.notebook.select(tab)
        self.tabs.append(tab)
        tab.text_widget.focus_set()

    def add_hex_viewer(self):
        tab=HexViewerTab(self.notebook,self.close_tab)
        self.notebook.add(tab,text=" [#] Hex Viewer ")
        self.notebook.select(tab)
        self.tabs.append(tab)

    def show_tools(self):
        dlg=tk.Toplevel(self)
        dlg.title("Cyber Security Arsenal")
        dlg.geometry("800x800")
        dlg.configure(bg='#0A0A0A')
        search_var=tk.StringVar()
        tk.Entry(dlg,textvariable=search_var,bg='#222',fg='#0F0',font=('Consolas',14)).pack(fill=tk.X,padx=20,pady=20)
        canvas=tk.Canvas(dlg,bg='#0A0A0A',highlightthickness=0)
        scroll=ttk.Scrollbar(dlg,orient="vertical",command=canvas.yview)
        scrollable_frame=tk.Frame(canvas,bg='#0A0A0A')
        scrollable_frame.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0),window=scrollable_frame,anchor="nw",width=750)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left",fill="both",expand=True,padx=20)
        scroll.pack(side="right",fill="y")
        def update_list(*args):
            for w in scrollable_frame.winfo_children(): w.destroy()
            q=search_var.get().lower()
            for name,conf in MASSIVE_TOOLS.items():
                if q in name.lower() or q in conf['cat'].lower() or q in conf['desc'].lower():
                    f=tk.Frame(scrollable_frame,bg='#151515')
                    f.pack(fill=tk.X,pady=5)
                    tk.Label(f,text=f"{name} [{conf['cat']}]",bg='#151515',fg='#0F0',font=('Consolas',12,'bold')).pack(anchor='w',padx=10,pady=5)
                    tk.Label(f,text=conf['desc'],bg='#151515',fg='#888',font=('Consolas',10)).pack(anchor='w',padx=10)
                    tk.Button(f,text="LAUNCH",command=lambda n=name,c=conf:[dlg.destroy(),self.add_tool(n,c)],bg='#222',fg='#FFF',relief=tk.FLAT).pack(side=tk.RIGHT,padx=10,pady=5)
        search_var.trace_add("write",update_list)
        update_list()

    def add_tool(self,name,conf):
        tab=AdvancedToolTab(self.notebook,name,{"description":conf['desc'],"params":conf.get('params',[]),"build_cmd":conf['build_cmd']},self.close_tab)
        self.notebook.add(tab,text=f" 🔧 {name} ")
        self.notebook.select(tab)
        self.tabs.append(tab)

    def close_tab(self,tab):
        if hasattr(tab,'stop'): tab.stop()
        if tab in self.tabs: self.tabs.remove(tab)
        self.notebook.forget(tab)
        tab.destroy()

if __name__=="__main__":
    app=CyberTermEngine()
    app.mainloop()
