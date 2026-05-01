import os
import subprocess

class GitManager:
    def __init__(self, project_path):
        self.project_path = project_path

    def run_git(self, *args):
        """Выполняет консольную команду git и возвращает результат"""
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(
                ['git'] + list(args),
                cwd=self.project_path,
                capture_output=True,
                text=True,
                check=True,
                startupinfo=startupinfo,
                encoding='utf-8'
            )
            return True, result.stdout.strip()
        except subprocess.CalledProcessError as e:
            return False, e.stderr.strip()
        except FileNotFoundError:
            return False, "GIT_NOT_INSTALLED"

    def is_repo(self):
        """Проверяет, инициализирован ли git в папке"""
        return os.path.exists(os.path.join(self.project_path, '.git'))

    def ensure_gitignore(self):
        """Создает файл .gitignore, чтобы скрыть мусор от коммитов"""
        gitignore_path = os.path.join(self.project_path, '.gitignore')
        
        # Стандартные правила для VibeCoder и Python
        rules = [
            "# VibeCoder",
            ".vibecoder/",
            ".vibe_backups/",
            "__pycache__/",
            "*.pyc",
            "# Python Virtual Environment",
            "venv/",
            "env/",
            ".env"
        ]
        
        # Если файла нет, создаем его со стандартными правилами
        if not os.path.exists(gitignore_path):
            with open(gitignore_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(rules) + "\n")
            return True
            
        # Если файл есть, проверяем, есть ли там наши ключевые папки
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            missing_rules = [r for r in rules if r not in content and not r.startswith("#")]
            
            if missing_rules:
                with open(gitignore_path, 'a', encoding='utf-8') as f:
                    f.write("\n\n# Auto-added by VibeCoder\n")
                    f.write("\n".join(missing_rules) + "\n")
                return True
        except Exception:
            pass
            
        return False

    def init_repo(self):
        """Инициализирует пустой репозиторий и сразу настраивает gitignore"""
        success, msg = self.run_git('init')
        if success:
            self.ensure_gitignore()
        return success, msg

    def get_status(self):
        """Получает список измененных файлов (игнорируя те, что в .gitignore)"""
        # Сначала убедимся, что игнор настроен (на случай если папку создали до этого)
        if self.is_repo():
            self.ensure_gitignore()
            
        success, output = self.run_git('status', '--porcelain')
        if not success:
            return -1

        if not output:
            return 0

        return len(output.split('\n'))

    def get_diff(self):
        """Получает разницу кода для генерации описания ИИ"""
        self.run_git('add', '-N', '.') 
        success, output = self.run_git('diff')
        return output if success else ""

    def commit_all(self, message):
        """Добавляет все файлы (кроме проигнорированных) и делает коммит"""
        add_success, add_err = self.run_git('add', '.')
        if not add_success:
            return False, f"Ошибка git add: {add_err}"
            
        commit_success, commit_err = self.run_git('commit', '-m', message)
        if not commit_success:
            return False, f"Ошибка git commit: {commit_err}"
            
        return True, "Коммит успешно создан!"

    # ==========================================
    # НОВЫЕ ФУНКЦИИ ДЛЯ РАБОТЫ С GITHUB (ОБЛАКОМ)
    # ==========================================
    
    def get_remote_url(self):
        """Проверяет, подключен ли удаленный репозиторий (origin)"""
        success, output = self.run_git('remote', 'get-url', 'origin')
        return output if success else None

    def set_remote_url(self, url):
        """Подключает удаленный репозиторий GitHub"""
        # Если origin уже есть, меняем его (set-url), иначе добавляем (add)
        if self.get_remote_url():
            return self.run_git('remote', 'set-url', 'origin', url)
        else:
            return self.run_git('remote', 'add', 'origin', url)

    def get_current_branch(self):
        """Получает название текущей ветки (обычно main или master)"""
        success, output = self.run_git('branch', '--show-current')
        return output if success else "main"

    def push_to_cloud(self):
        """Отправляет коммиты на GitHub"""
        branch = self.get_current_branch()
        # Ключ -u нужен для связывания локальной и удаленной ветки при первом пуше
        success, output = self.run_git('push', '-u', 'origin', branch)
        if not success:
            return False, output
        return True, "Код успешно отправлен в облако!"