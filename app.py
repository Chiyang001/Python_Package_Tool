from flask import Flask, render_template, request, jsonify, send_file, session
import os
import subprocess
import threading
import queue
import shutil
import glob
import time
import tempfile
import zipfile
from werkzeug.utils import secure_filename
from PIL import Image
import uuid
import json

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 存储任务状态的字典
tasks = {}

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {'py', 'ico'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def validate_icon(icon_path):
    """验证ICO图标文件"""
    try:
        with Image.open(icon_path) as img:
            # 检查文件格式
            if img.format != 'ICO':
                return False, "仅支持ICO格式的图标文件"
            
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
                return True, f"警告: 图标文件缺少以下尺寸: {missing_sizes}"
            
            return True, "图标文件验证通过"
    except Exception as e:
        return False, f"验证图标文件时出错: {str(e)}"

def run_pyinstaller_task(task_id, python_file, resource_folder=None, icon_file=None, 
                        output_dir=None, onefile=True, noconsole=True, clean=True):
    """在后台线程中运行PyInstaller"""
    task = tasks[task_id]
    task['status'] = 'running'
    task['progress'] = 0
    task['logs'] = []
    
    try:
        # 创建临时工作目录
        work_dir = tempfile.mkdtemp()
        task['work_dir'] = work_dir
        
        # 复制Python文件到工作目录
        python_filename = secure_filename(python_file.filename)
        python_path = os.path.join(work_dir, python_filename)
        python_file.save(python_path)
        
        # 复制资源文件夹（如果提供）
        if resource_folder:
            resource_dir = os.path.join(work_dir, os.path.basename(resource_folder))
            shutil.copytree(resource_folder, resource_dir)
        
        # 复制图标文件（如果提供）
        icon_path = None
        if icon_file:
            icon_filename = secure_filename(icon_file.filename)
            icon_path = os.path.join(work_dir, icon_filename)
            icon_file.save(icon_path)
            
            # 验证图标
            is_valid, icon_msg = validate_icon(icon_path)
            if not is_valid:
                task['logs'].append(f"错误: {icon_msg}")
                task['status'] = 'error'
                return
            elif "警告" in icon_msg:
                task['logs'].append(icon_msg)
        
        # 检查PyInstaller是否安装
        try:
            subprocess.run(["pyinstaller", "--version"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            task['logs'].append("错误: 请先安装PyInstaller (pip install pyinstaller)")
            task['status'] = 'error'
            return
        
        # 构建命令
        cmd = ["pyinstaller", "--noconfirm"]
        if onefile:
            cmd.append("--onefile")
        if noconsole:
            cmd.append("--windowed")
        if clean:
            cmd.append("--clean")
        
        # 添加资源文件夹
        if resource_folder:
            cmd.extend(["--add-data", f"{resource_dir};{os.path.basename(resource_folder)}"])
        
        # 添加图标
        if icon_path:
            cmd.extend(["--icon", icon_path])
        
        # 指定输出目录
        if output_dir:
            cmd.extend(["--distpath", output_dir])
        
        cmd.append(python_filename)
        
        task['logs'].append(f"开始打包: {' '.join(cmd)}")
        
        # 运行PyInstaller
        os.chdir(work_dir)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        
        # 实时读取输出
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                task['logs'].append(line)
                
                # 解析进度信息
                if "[=" in line and "]" in line:
                    try:
                        progress = int(line.split("[=")[1].split("]")[0].strip("%"))
                        task['progress'] = progress
                    except:
                        pass
        
        process.wait()
        
        # 处理生成文件
        if process.returncode == 0:
            exe_name = python_filename.replace(".py", ".exe")
            if output_dir:
                dist_path = os.path.join(output_dir, exe_name)
            else:
                dist_path = os.path.join(work_dir, "dist", exe_name)
            
            if os.path.exists(dist_path):
                # 创建ZIP文件
                zip_filename = f"{exe_name[:-4]}_package.zip"
                zip_path = os.path.join(work_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 添加EXE文件
                    zipf.write(dist_path, exe_name)
                    
                    # 添加资源文件夹（如果存在）
                    if resource_folder and os.path.exists(resource_dir):
                        for root, dirs, files in os.walk(resource_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.relpath(file_path, work_dir)
                                zipf.write(file_path, arcname)
                
                task['result_file'] = zip_path
                task['result_filename'] = zip_filename
                task['status'] = 'completed'
                task['progress'] = 100
                task['logs'].append(f"打包成功: {zip_filename}")
            else:
                task['logs'].append("错误: 未找到生成的EXE文件")
                task['status'] = 'error'
        else:
            task['logs'].append(f"错误: 打包失败 (退出码 {process.returncode})")
            task['status'] = 'error'
            
    except Exception as e:
        task['logs'].append(f"错误: {str(e)}")
        task['status'] = 'error'
    finally:
        # 清理临时文件（保留结果文件）
        if 'work_dir' in task and task['status'] != 'completed':
            try:
                shutil.rmtree(task['work_dir'])
            except:
                pass

def find_main_file(project_dir):
    """在项目目录中查找主程序文件"""
    main_files = []
    
    # 常见的入口文件名
    entry_names = ['main.py', 'app.py', 'run.py', 'start.py', '__main__.py']
    
    # 查找根目录下的入口文件
    for name in entry_names:
        if os.path.exists(os.path.join(project_dir, name)):
            main_files.append(name)
    
    # 如果没有找到常见的入口文件，查找包含 if __name__ == '__main__' 的文件
    if not main_files:
        for root, dirs, files in os.walk(project_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if 'if __name__' in content and '__main__' in content:
                                rel_path = os.path.relpath(file_path, project_dir)
                                main_files.append(rel_path)
                    except:
                        continue
    
    return main_files

def run_project_pyinstaller_task(task_id, project_zip, icon_file=None, output_dir=None, 
                                onefile=True, noconsole=True, clean=True):
    """在后台线程中运行多文件项目打包"""
    task = tasks[task_id]
    task['status'] = 'running'
    task['progress'] = 0
    task['logs'] = []
    
    try:
        # 创建临时工作目录
        work_dir = tempfile.mkdtemp()
        task['work_dir'] = work_dir
        
        # 解压项目文件
        project_filename = secure_filename(project_zip.filename)
        project_path = os.path.join(work_dir, project_filename)
        project_zip.save(project_path)
        
        # 解压ZIP文件
        extract_dir = os.path.join(work_dir, 'project')
        with zipfile.ZipFile(project_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # 查找项目根目录（通常是解压后的第一个目录）
        project_root = None
        for item in os.listdir(extract_dir):
            item_path = os.path.join(extract_dir, item)
            if os.path.isdir(item_path):
                project_root = item_path
                break
        
        if not project_root:
            # 如果没有子目录，直接使用解压目录
            project_root = extract_dir
        
        task['logs'].append(f"项目根目录: {project_root}")
        
        # 查找主程序文件
        main_files = find_main_file(project_root)
        
        if not main_files:
            task['logs'].append("错误: 未找到主程序文件")
            task['status'] = 'error'
            return
        
        # 选择主程序文件（优先选择常见的入口文件）
        main_file = main_files[0]
        task['logs'].append(f"找到主程序文件: {main_file}")
        
        # 复制图标文件（如果提供）
        icon_path = None
        if icon_file:
            icon_filename = secure_filename(icon_file.filename)
            icon_path = os.path.join(work_dir, icon_filename)
            icon_file.save(icon_path)
            
            # 验证图标
            is_valid, icon_msg = validate_icon(icon_path)
            if not is_valid:
                task['logs'].append(f"错误: {icon_msg}")
                task['status'] = 'error'
                return
            elif "警告" in icon_msg:
                task['logs'].append(icon_msg)
        
        # 检查PyInstaller是否安装
        try:
            subprocess.run(["pyinstaller", "--version"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            task['logs'].append("错误: 请先安装PyInstaller (pip install pyinstaller)")
            task['status'] = 'error'
            return
        
        # 构建命令
        cmd = ["pyinstaller", "--noconfirm"]
        if onefile:
            cmd.append("--onefile")
        if noconsole:
            cmd.append("--windowed")
        if clean:
            cmd.append("--clean")
        
        # 添加图标
        if icon_path:
            cmd.extend(["--icon", icon_path])
        
        # 指定输出目录
        if output_dir:
            cmd.extend(["--distpath", output_dir])
        
        # 添加主程序文件
        cmd.append(main_file)
        
        task['logs'].append(f"开始打包: {' '.join(cmd)}")
        
        # 运行PyInstaller
        os.chdir(project_root)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, bufsize=1)
        
        # 实时读取输出
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                task['logs'].append(line)
                
                # 解析进度信息
                if "[=" in line and "]" in line:
                    try:
                        progress = int(line.split("[=")[1].split("]")[0].strip("%"))
                        task['progress'] = progress
                    except:
                        pass
        
        process.wait()
        
        # 处理生成文件
        if process.returncode == 0:
            exe_name = os.path.splitext(main_file)[0] + ".exe"
            if output_dir:
                dist_path = os.path.join(output_dir, exe_name)
            else:
                dist_path = os.path.join(project_root, "dist", exe_name)
            
            if os.path.exists(dist_path):
                # 创建ZIP文件
                zip_filename = f"{os.path.splitext(main_file)[0]}_project_package.zip"
                zip_path = os.path.join(work_dir, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 添加EXE文件
                    zipf.write(dist_path, exe_name)
                    
                    # 添加项目中的资源文件
                    resource_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', 
                                         '.json', '.xml', '.txt', '.csv', '.xlsx', '.xls',
                                         '.mp3', '.wav', '.mp4', '.avi', '.pdf', '.doc', '.docx'}
                    
                    for root, dirs, files in os.walk(project_root):
                        for file in files:
                            file_path = os.path.join(root, file)
                            file_ext = os.path.splitext(file)[1].lower()
                            
                            # 跳过Python文件、临时文件和构建文件
                            if (file_ext in resource_extensions and 
                                not file.endswith('.pyc') and 
                                not file.endswith('.pyo') and
                                '__pycache__' not in root and
                                '.git' not in root and
                                'build' not in root and
                                'dist' not in root):
                                
                                arcname = os.path.relpath(file_path, project_root)
                                zipf.write(file_path, arcname)
                
                task['result_file'] = zip_path
                task['result_filename'] = zip_filename
                task['status'] = 'completed'
                task['progress'] = 100
                task['logs'].append(f"项目打包成功: {zip_filename}")
            else:
                task['logs'].append("错误: 未找到生成的EXE文件")
                task['status'] = 'error'
        else:
            task['logs'].append(f"错误: 打包失败 (退出码 {process.returncode})")
            task['status'] = 'error'
            
    except Exception as e:
        task['logs'].append(f"错误: {str(e)}")
        task['status'] = 'error'
    finally:
        # 清理临时文件（保留结果文件）
        if 'work_dir' in task and task['status'] != 'completed':
            try:
                shutil.rmtree(task['work_dir'])
            except:
                pass

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    try:
        # 获取打包类型
        package_type = request.form.get('package_type', 'single')
        
        if package_type == 'single':
            # 单文件打包
            if 'python_file' not in request.files:
                return jsonify({'error': '请选择Python文件'}), 400
            
            python_file = request.files['python_file']
            if python_file.filename == '':
                return jsonify({'error': '请选择Python文件'}), 400
            
            if not allowed_file(python_file.filename, {'py'}):
                return jsonify({'error': '请选择有效的Python文件 (.py)'}), 400
            
            # 获取其他参数
            resource_folder = request.form.get('resource_folder', '').strip()
            icon_file = request.files.get('icon_file')
            output_dir = request.form.get('output_dir', '').strip()
            onefile = request.form.get('onefile', 'true').lower() == 'true'
            noconsole = request.form.get('noconsole', 'true').lower() == 'true'
            clean = request.form.get('clean', 'true').lower() == 'true'
            
            # 验证图标文件
            if icon_file and icon_file.filename != '':
                if not allowed_file(icon_file.filename, {'ico'}):
                    return jsonify({'error': '请选择有效的图标文件 (.ico)'}), 400
            
            # 创建任务ID
            task_id = str(uuid.uuid4())
            tasks[task_id] = {
                'status': 'pending',
                'progress': 0,
                'logs': [],
                'created_at': time.time(),
                'type': 'single'
            }
            
            # 启动后台任务
            thread = threading.Thread(
                target=run_pyinstaller_task,
                args=(task_id, python_file, resource_folder, icon_file, output_dir, onefile, noconsole, clean)
            )
            thread.daemon = True
            thread.start()
            
        else:
            # 多文件项目打包
            if 'project_folder' not in request.files:
                return jsonify({'error': '请选择项目文件夹'}), 400
            
            project_zip = request.files['project_folder']
            if project_zip.filename == '':
                return jsonify({'error': '请选择项目文件夹'}), 400
            
            if not project_zip.filename.endswith('.zip'):
                return jsonify({'error': '请上传ZIP格式的项目文件夹'}), 400
            
            # 获取其他参数
            icon_file = request.files.get('icon_file')
            output_dir = request.form.get('output_dir', '').strip()
            onefile = request.form.get('onefile', 'true').lower() == 'true'
            noconsole = request.form.get('noconsole', 'true').lower() == 'true'
            clean = request.form.get('clean', 'true').lower() == 'true'
            
            # 验证图标文件
            if icon_file and icon_file.filename != '':
                if not allowed_file(icon_file.filename, {'ico'}):
                    return jsonify({'error': '请选择有效的图标文件 (.ico)'}), 400
            
            # 创建任务ID
            task_id = str(uuid.uuid4())
            tasks[task_id] = {
                'status': 'pending',
                'progress': 0,
                'logs': [],
                'created_at': time.time(),
                'type': 'project'
            }
            
            # 启动后台任务
            thread = threading.Thread(
                target=run_project_pyinstaller_task,
                args=(task_id, project_zip, icon_file, output_dir, onefile, noconsole, clean)
            )
            thread.daemon = True
            thread.start()
        
        return jsonify({'task_id': task_id})
        
    except Exception as e:
        return jsonify({'error': f'上传失败: {str(e)}'}), 500

@app.route('/status/<task_id>')
def get_status(task_id):
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    
    task = tasks[task_id]
    return jsonify({
        'status': task['status'],
        'progress': task['progress'],
        'logs': task['logs'][-50:],  # 只返回最后50行日志
        'result_filename': task.get('result_filename')
    })

@app.route('/download/<task_id>')
def download(task_id):
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    
    task = tasks[task_id]
    if task['status'] != 'completed' or 'result_file' not in task:
        return jsonify({'error': '文件未准备好'}), 400
    
    try:
        return send_file(
            task['result_file'],
            as_attachment=True,
            download_name=task['result_filename']
        )
    except Exception as e:
        return jsonify({'error': f'下载失败: {str(e)}'}), 500

@app.route('/cleanup/<task_id>')
def cleanup(task_id):
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    
    task = tasks[task_id]
    try:
        # 清理工作目录
        if 'work_dir' in task and os.path.exists(task['work_dir']):
            shutil.rmtree(task['work_dir'])
        
        # 删除任务记录
        del tasks[task_id]
        
        return jsonify({'message': '清理成功'})
    except Exception as e:
        return jsonify({'error': f'清理失败: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5006) 
