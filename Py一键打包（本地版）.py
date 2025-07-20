import tkinter as tk
from tkinter import filedialog, scrolledtext
import subprocess
import os
import threading
import queue
import shutil
import glob
import time
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from PIL import Image
import win32com.client
import ctypes
import winreg

class PyInstallerGUI(ttk.Window):
    def __init__(self):
        # 选择一个颜色协调的主题，这里使用 'minty'
        super().__init__(themename="minty")
        self.title("Python转EXE工具")
        self.geometry("1000x900")
        self.resizable(False, False)

        # 创建顶部标题区域
        self.create_title_frame()
        # 创建文件选择区域
        self.create_file_frame()
        # 创建资源文件夹选择区域
        self.create_resource_frame()
        # 创建图标选择区域
        self.create_icon_frame()
        # 创建输出目录选择区域
        self.create_output_dir_frame()
        # 创建PyInstaller选项区域
        self.create_options_frame()
        # 创建打包按钮
        self.create_start_button()
        # 创建日志显示区域
        self.create_log_area()
        # 线程通信队列
        self.queue = queue.Queue()
        self.check_queue()
        # 进度条
        self.create_progressbar()

    def create_title_frame(self):
        title_frame = ttk.Frame(self, bootstyle="light")
        title_frame.pack(pady=20, fill=tk.X)
        title_label = ttk.Label(title_frame, text="Python 脚本打包工具", font=("Helvetica", 24, "bold"))
        title_label.pack(pady=10)

    def create_file_frame(self):
        file_frame = ttk.Frame(self, bootstyle="light", padding=10)
        file_frame.pack(pady=10, padx=20, fill=tk.X)
        self.file_path = tk.StringVar()
        file_label = ttk.Label(file_frame, text="选择Python文件:")
        file_label.pack(side=tk.LEFT, padx=5)
        file_entry = ttk.Entry(file_frame, textvariable=self.file_path, width=50)
        file_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        file_button = ttk.Button(file_frame, text="浏览文件", command=self.select_file, bootstyle="info")
        file_button.pack(side=tk.LEFT, padx=5)

    def select_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("Python files", "*.py")])
        if file_path:
            self.file_path.set(file_path)

    def create_resource_frame(self):
        resource_frame = ttk.Frame(self, bootstyle="light", padding=10)
        resource_frame.pack(pady=10, padx=20, fill=tk.X)
        self.resource_folder_path = tk.StringVar()
        resource_label = ttk.Label(resource_frame, text="选择资源文件夹 (可选):")
        resource_label.pack(side=tk.LEFT, padx=5)
        resource_entry = ttk.Entry(resource_frame, textvariable=self.resource_folder_path, width=50)
        resource_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        resource_button = ttk.Button(resource_frame, text="浏览文件夹", command=self.select_resource_folder, bootstyle="info")
        resource_button.pack(side=tk.LEFT, padx=5)

    def select_resource_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path:
            self.resource_folder_path.set(folder_path)

    def create_icon_frame(self):
        icon_frame = ttk.Frame(self, bootstyle="light", padding=10)
        icon_frame.pack(pady=10, padx=20, fill=tk.X)
        self.icon_path = tk.StringVar()
        icon_label = ttk.Label(icon_frame, text="选择图标文件 (可选):")
        icon_label.pack(side=tk.LEFT, padx=5)
        icon_entry = ttk.Entry(icon_frame, textvariable=self.icon_path, width=50)
        icon_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        icon_button = ttk.Button(icon_frame, text="浏览图标", command=self.select_icon, bootstyle="info")
        icon_button.pack(side=tk.LEFT, padx=5)

    def select_icon(self):
        icon_path = filedialog.askopenfilename(filetypes=[("Icon files", "*.ico")])
        if icon_path:
            self.icon_path.set(icon_path)

    def create_output_dir_frame(self):
        output_dir_frame = ttk.Frame(self, bootstyle="light", padding=10)
        output_dir_frame.pack(pady=10, padx=20, fill=tk.X)
        self.output_dir = tk.StringVar()
        output_dir_label = ttk.Label(output_dir_frame, text="选择输出目录 (可选):")
        output_dir_label.pack(side=tk.LEFT, padx=5)
        output_dir_entry = ttk.Entry(output_dir_frame, textvariable=self.output_dir, width=50)
        output_dir_entry.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        output_dir_button = ttk.Button(output_dir_frame, text="浏览目录", command=self.select_output_dir, bootstyle="info")
        output_dir_button.pack(side=tk.LEFT, padx=5)

    def select_output_dir(self):
        output_dir = filedialog.askdirectory()
        if output_dir:
            self.output_dir.set(output_dir)

    def create_options_frame(self):
        options_frame = ttk.Frame(self, bootstyle="light", padding=10)
        options_frame.pack(pady=10, padx=20, fill=tk.X)
        self.onefile_var = tk.IntVar(value=1)
        onefile_check = ttk.Checkbutton(options_frame, text="单文件模式 (--onefile)", variable=self.onefile_var, bootstyle="round-toggle")
        onefile_check.pack(side=tk.LEFT, padx=10)
        self.noconsole_var = tk.IntVar(value=1)
        noconsole_check = ttk.Checkbutton(options_frame, text="无控制台模式 (--windowed)", variable=self.noconsole_var, bootstyle="round-toggle")
        noconsole_check.pack(side=tk.LEFT, padx=10)
        self.clean_var = tk.IntVar(value=1)
        clean_check = ttk.Checkbutton(options_frame, text="清理临时文件 (--clean)", variable=self.clean_var, bootstyle="round-toggle")
        clean_check.pack(side=tk.LEFT, padx=10)

    def create_start_button(self):
        self.start_btn = ttk.Button(self, text="开始打包", command=self.start_process, bootstyle="success", width=20)
        self.start_btn.pack(pady=20)

    def create_log_area(self):
        self.log_area = scrolledtext.ScrolledText(self, state='disabled', height=10, width=70)
        self.log_area.pack(pady=10, padx=20, fill=tk.BOTH, expand=True)
        self.log_area.tag_config("error", foreground="red")

    def create_progressbar(self):
        self.loading_label = ttk.Label(self, text="", font=("Courier", 20))
        self.loading_chars = ["⠇", "⠋", "⠙", "⠸", "⠴", "⠦"]
        self.loading_index = 0
        self.loading_active = False

    def show_loading_animation(self):
        if self.loading_active:
            self.loading_label.config(text=self.loading_chars[self.loading_index % len(self.loading_chars)])
            self.loading_index += 1
            self.after(150, self.show_loading_animation)

    def start_process(self):
        file = self.file_path.get()
        if not file.endswith(".py"):
            self.log("错误: 请选择有效的Python文件 (.py)", "error")
            return

        self.start_btn.config(state=DISABLED)
        self.loading_active = True
        self.show_loading_animation()
        self.loading_label.pack(pady=10)

        threading.Thread(target=self.run_pyinstaller, daemon=True).start()

    def hide_loading_animation(self):
        self.loading_active = False
        self.loading_label.pack_forget()
        self.loading_index = 0
        self.loading_label.config(text="")

    def run_pyinstaller(self):
        src_file = self.file_path.get()
        work_dir = os.path.dirname(src_file)
        file_name = os.path.basename(src_file)
        exe_name = file_name.replace(".py", ".exe")

        try:
            # 检查PyInstaller是否安装
            subprocess.run(["pyinstaller", "--version"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            self.queue.put(("错误: 请先安装PyInstaller (pip install pyinstaller)", "error"))
            self.start_btn.config(state=NORMAL)
            self.hide_loading_animation()
            return

        # 构建命令
        cmd = "pyinstaller --noconfirm"
        if self.onefile_var.get():
            cmd += " --onefile"
        if self.noconsole_var.get():
            cmd += " --windowed"
        if self.clean_var.get():
            cmd += " --clean"

        # 添加资源文件夹
        resource_folder = self.resource_folder_path.get()
        if resource_folder:
            cmd += f' --add-data "{resource_folder};{os.path.basename(resource_folder)}"'

        # 添加图标
        icon = self.icon_path.get()
        if icon:
            # 验证图标文件
            if not self.validate_icon(icon):
                self.queue.put(("警告: 图标文件可能不是标准格式，尝试继续打包...", "error"))
            
            # 确保图标路径是绝对路径
            icon_abs_path = os.path.abspath(icon)
            # 添加图标参数，确保正确设置文件资源管理器图标
            cmd += f' --icon "{icon_abs_path}"'

        # 指定输出目录
        output_dir = self.output_dir.get()
        if output_dir:
            cmd += f' --distpath "{output_dir}"'

        cmd += f' "{file_name}"'
        self.queue.put(("开始打包: " + cmd, "info"))

        try:
            os.chdir(work_dir)
            process = subprocess.Popen(cmd, shell=True,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT,
                                       text=True, bufsize=1)

            # 实时读取输出
            total_lines = 0
            for line in iter(process.stdout.readline, ''):
                total_lines += 1
                if "[=" in line and "]" in line:
                    try:
                        progress = int(line.split("[=")[1].split("]")[0].strip("%"))
                        self.queue.put(("progress", progress))
                    except:
                        pass
                self.queue.put((line.strip(), "info"))

            process.wait()

            # 处理生成文件
            if process.returncode == 0:
                if output_dir:
                    dist_path = os.path.join(output_dir, exe_name)
                else:
                    dist_path = os.path.join(work_dir, "dist", exe_name)
                if os.path.exists(dist_path):
                    # 移动并清理文件
                    if output_dir:
                        final_path = os.path.join(output_dir, exe_name)
                    else:
                        final_path = os.path.join(work_dir, exe_name)
                    shutil.move(dist_path, final_path)
                    self.queue.put(("生成成功: " + final_path, "success"))
                else:
                    self.queue.put(("错误: 未找到生成的EXE文件", "error"))

                # 清理临时文件
                for item in ["build", "dist", f"{exe_name[:-4]}.spec"]:
                    path = os.path.join(work_dir, item)
                    if os.path.exists(path):
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
                
                # 打包完成
            else:
                self.queue.put((f"错误: 打包失败 (退出码 {process.returncode})", "error"))
        except Exception as e:
            self.queue.put((f"错误: {str(e)}", "error"))
        finally:
            self.start_btn.config(state=NORMAL)
            self.hide_loading_animation()

    def validate_icon(self, icon_path):
        """验证ICO图标文件"""
        try:
            with Image.open(icon_path) as img:
                # 检查文件格式
                if img.format != 'ICO':
                    self.log("错误: 仅支持ICO格式的图标文件", "error")
                    return False
                
                # 检查图标尺寸
                sizes = []
                if hasattr(img, 'n_frames'):
                    for frame in range(img.n_frames):
                        img.seek(frame)
                        sizes.append(img.size)
                else:
                    sizes.append(img.size)
                
                # 检查是否包含常用尺寸
                required_sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]
                missing_sizes = [size for size in required_sizes if size not in sizes]
                
                if missing_sizes:
                    self.log(f"警告: 图标文件缺少以下尺寸: {missing_sizes}", "warning")
                    self.log("请使用包含标准尺寸的ICO文件", "warning")
                
                return True
        except Exception as e:
            self.log(f"错误: 验证图标文件时出错 - {str(e)}", "error")
            return False

    def clear_icon_cache(self):
        """清理Windows图标缓存(已禁用)"""
        pass
        try:
            self.queue.put(("开始刷新图标缓存...", "info"))
            
            # 1. 删除所有图标缓存文件
            cache_locations = [
                os.path.join(os.environ['LOCALAPPDATA'], 'Microsoft', 'Windows', 'Explorer'),
                os.path.join(os.environ['USERPROFILE'], 'AppData', 'Local', 'Microsoft', 'Windows', 'Explorer')
            ]
            
            for location in cache_locations:
                if os.path.exists(location):
                    for pattern in ['iconcache_*.db', 'thumbcache_*.db', '*.tmp']:
                        for file in glob.glob(os.path.join(location, pattern)):
                            try:
                                os.remove(file)
                                self.queue.put((f"已删除缓存文件: {file}", "debug"))
                            except Exception as e:
                                self.queue.put((f"无法删除缓存文件: {file} - {str(e)}", "debug"))

            # 2. 多次刷新系统图标缓存
            for i in range(3):
                try:
                    # 使用多种方法刷新缓存
                    shell = win32com.client.Dispatch("Shell.Application")
                    shell.RefreshEnvironment()
                    
                    # 通知系统图标缓存已更改
                    SHCNE_ASSOCCHANGED = 0x08000000
                    SHCNF_IDLIST = 0x0000
                    shell32 = ctypes.WinDLL('shell32')
                    shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
                    
                    time.sleep(1)  # 等待系统处理
                except Exception as e:
                    self.queue.put((f"刷新图标缓存时出错(尝试 {i+1}/3): {str(e)}", "debug"))

            # 3. 重启资源管理器
            try:
                self.queue.put(("正在重启Windows资源管理器...", "info"))
                subprocess.run('taskkill /f /im explorer.exe', shell=True, 
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                time.sleep(2)  # 确保资源管理器完全关闭
                subprocess.Popen('explorer.exe')
                time.sleep(1)  # 等待资源管理器重新启动
            except Exception as e:
                self.queue.put((f"重启资源管理器时出错: {str(e)}", "warning"))

            # 4. 最终检查和建议
            self.queue.put(("图标缓存已彻底刷新", "info"))
            self.queue.put(("如果某些视图下图标仍未更新:", "info"))
            self.queue.put(("1. 尝试切换到其他文件夹再切换回来", "info"))
            self.queue.put(("2. 或者注销并重新登录Windows", "info"))
            self.queue.put(("3. 某些情况下需要重启电脑才能完全生效", "info"))
            
        except Exception as e:
            self.queue.put((f"严重错误: 刷新图标缓存失败 - {str(e)}", "error"))
            self.queue.put(("请尝试手动重启电脑以更新图标缓存", "error"))

    def check_queue(self):
        while not self.queue.empty():
            msg = self.queue.get_nowait()
            if isinstance(msg, tuple):
                if msg[0] == "progress":
                    self.progressbar["value"] = msg[1]
                else:
                    self.log(msg[0], msg[1])
            else:
                self.log(msg)
        self.after(100, self.check_queue)

    def log(self, message, tag=None):
        self.log_area.config(state=NORMAL)
        if tag:
            self.log_area.insert(tk.END, message + "\n", tag)
        else:
            self.log_area.insert(tk.END, message + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state=DISABLED)

    def log_clear(self):
        self.log_area.config(state=NORMAL)
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state=DISABLED)

    def show_progressbar(self):
        self.progressbar.pack(pady=10)
        self.progressbar["value"] = 0

    def hide_progressbar(self):
        self.progressbar["value"] = 0
        self.progressbar.pack_forget()

if __name__ == "__main__":
    app = PyInstallerGUI()
    app.mainloop()