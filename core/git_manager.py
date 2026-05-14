import os
import subprocess

class GitManager:
    def __init__(self, project_path):
        self.project_path = project_path

    def run_git(self, *args):
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            # НОВОЕ: Заставляем Git нормально читать русские названия папок и файлов!
            full_args = ['git', '-c', 'core.quotePath=false'] + list(args)

            result = subprocess.run(
                full_args,
                cwd=self.project_path,
                capture_output=True, text=True, check=True,
                startupinfo=startupinfo, encoding='utf-8'
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e: return False, e.stderr.strip()
        except FileNotFoundError: return False, "GIT_NOT_INSTALLED"

    def is_repo(self):
        return os.path.exists(os.path.join(self.project_path, '.git'))

    def ensure_gitignore(self):
        gitignore_path = os.path.join(self.project_path, '.gitignore')
        rules = ["# VibeCoder", ".vibecoder/", ".vibe_backups/", "__pycache__/", "*.pyc", "venv/", "env/", ".env"]
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w', encoding='utf-8') as f: f.write("\n".join(rules) + "\n")
            return True
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f: content = f.read()
            missing_rules = [r for r in rules if r not in content and not r.startswith("#")]
            if missing_rules:
                with open(gitignore_path, 'a', encoding='utf-8') as f:
                    f.write("\n\n# Auto-added by VibeCoder\n" + "\n".join(missing_rules) + "\n")
                return True
        except Exception: pass
        return False

    def init_repo(self):
        success, msg = self.run_git('init')
        if success: self.ensure_gitignore()
        return success, msg

    def get_status(self):
        if self.is_repo(): self.ensure_gitignore()
        success, output = self.run_git('status', '--porcelain')
        return len(output.split('\n')) if success and output else (0 if success else -1)

    def get_changed_files(self):
        if not self.is_repo(): return []
        success, output = self.run_git('status', '--porcelain')
        if not success or not output: return []
        
        files = []
        for line in output.splitlines():
            line = line.strip() 
            if not line: continue
            
            parts = line.split(maxsplit=1)
            if len(parts) < 2: continue
            
            file_path = parts[1].strip()
            
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
                
            if ' -> ' in file_path:
                file_path = file_path.split(' -> ')[-1].strip()
                if file_path.startswith('"') and file_path.endswith('"'):
                    file_path = file_path[1:-1]
                    
            if file_path:
                files.append(file_path)
        return files

    def get_all_tracked_files(self):
        if not self.is_repo(): return []
        success, output = self.run_git('ls-files')
        return [line.strip() for line in output.split('\n') if line.strip()] if success and output else []

    def get_diff_for_files(self, files):
        if not files: return ""
        
        # ОПТИМИЗАЦИЯ: Пакетное добавление намерений (intent-to-add) для ускорения генерации описаний
        to_add_intent = []
        for f in files:
            abs_path = os.path.join(self.project_path, f)
            if os.path.exists(abs_path):
                to_add_intent.append(f)
                
        if to_add_intent:
            chunk_size = 100
            for i in range(0, len(to_add_intent), chunk_size):
                chunk = to_add_intent[i:i + chunk_size]
                self.run_git('add', '-N', '--force', '--', *chunk)
            
        success, output = self.run_git('diff', '--', *files)
        return output if success else ""

    def commit_selected(self, message, files):
        if not files: return False, "Не выбрано ни одного файла."
        self.run_git('reset')
        
        # ОПТИМИЗАЦИЯ: Разделение путей на существующие (add) и удаленные (rm)
        to_add = []
        to_rm = []
        for f in files:
            abs_path = os.path.join(self.project_path, f)
            if os.path.exists(abs_path):
                to_add.append(f)
            else:
                to_rm.append(f)
                
        # Пакетное добавление файлов (партиями по 100 штук для обхода лимитов cmd в Windows)
        if to_add:
            chunk_size = 100
            for i in range(0, len(to_add), chunk_size):
                chunk = to_add[i:i + chunk_size]
                add_success, add_err = self.run_git('add', '--force', '--', *chunk)
                if not add_success:
                    return False, f"Ошибка добавления файлов: {add_err}"
                    
        # Пакетное удаление файлов
        if to_rm:
            chunk_size = 100
            for i in range(0, len(to_rm), chunk_size):
                chunk = to_rm[i:i + chunk_size]
                self.run_git('rm', '--cached', '--ignore-unmatch', '--', *chunk)
                
        commit_success, commit_err = self.run_git('commit', '-m', message)
        if not commit_success: return False, f"Ошибка git commit: {commit_err}"
        return True, "Коммит успешно создан!"

    # ==========================================
    # РАБОТА С ИСТОРИЕЙ ВЕРСИЙ (GIT TIMELINE)
    # ==========================================

    def get_file_history(self, file_path):
        # ИСПРАВЛЕНИЕ: Вытягиваем %B (полное тело коммита). 
        # Используем кастомные разделители, чтобы не сломать парсинг многострочных текстов.
        success, output = self.run_git('log', '--pretty=format:%h|VIBE|%ad|VIBE|%B|VIBE_END|', '--date=short', '--', file_path)
        if not success or not output: return []
        
        history = []
        commits = output.split('|VIBE_END|')
        for commit_str in commits:
            if not commit_str.strip(): continue
            parts = commit_str.strip().split('|VIBE|', 2)
            if len(parts) == 3:
                history.append({
                    'hash': parts[0].strip(),
                    'date': parts[1].strip(),
                    'message': parts[2].strip()
                })
        return history

    def get_file_content_at_commit(self, file_path, commit_hash):
        unix_path = file_path.replace('\\', '/')
        success, output = self.run_git('show', f'{commit_hash}:{unix_path}')
        return output if success else f"Не удалось прочитать файл:\n{output}"

    def get_commit_diff(self, file_path, commit_hash):
        success, output = self.run_git('show', '--format=', '--patch', commit_hash, '--', file_path)
        return output if success else ""

    def restore_file_to_commit(self, file_path, commit_hash):
        success, output = self.run_git('checkout', commit_hash, '--', file_path)
        return success, output

    # ==========================================
    # GITHUB (ОБЛАКО)
    # ==========================================
    
    def get_remote_url(self):
        success, output = self.run_git('remote', 'get-url', 'origin')
        return output if success else None

    def set_remote_url(self, url):
        return self.run_git('remote', 'set-url', 'origin', url) if self.get_remote_url() else self.run_git('remote', 'add', 'origin', url)

    def get_current_branch(self):
        success, output = self.run_git('branch', '--show-current')
        return output if success else "main"

    def push_to_cloud(self):
        success, output = self.run_git('push', '-u', 'origin', self.get_current_branch())
        return (True, "Код отправлен в облако!") if success else (False, output)

    def pull_from_cloud(self):
        success, output = self.run_git('pull', 'origin', self.get_current_branch())
        return (True, "Код скачан из облака!") if success else (False, output)

    def pull_specific_files(self, files):
        if not files: return False, "Файлы не выбраны."
        branch = self.get_current_branch()
        fetch_success, fetch_err = self.run_git('fetch', 'origin', branch)
        if not fetch_success: return False, f"Ошибка fetch: {fetch_err}"
            
        args = ['checkout', f'origin/{branch}', '--'] + files
        checkout_success, checkout_err = self.run_git(*args)
        return (True, f"Извлечено {len(files)} файлов!") if checkout_success else (False, f"Ошибка извлечения: {checkout_err}")