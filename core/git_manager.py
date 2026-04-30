import os
import subprocess

class GitManager:
    def __init__(self, project_path):
        self.project_path = project_path

    def run_git(self, *args):
        """Выполняет консольную команду git и возвращает результат"""
        try:
            # Скрываем окно консоли в Windows
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

    def init_repo(self):
        """Инициализирует пустой репозиторий"""
        return self.run_git('init')

    def get_status(self):
        """Получает список измененных файлов"""
        success, output = self.run_git('status', '--porcelain')
        if not success:
            return -1 # Ошибка или Git не установлен

        if not output:
            return 0 # Нет изменений

        # Считаем количество строк (каждая строка - измененный файл)
        return len(output.split('\n'))

    def get_diff(self):
        """Получает разницу кода для генерации описания ИИ"""
        # Добавляем все файлы в индекс временно, чтобы увидеть diff новых файлов
        self.run_git('add', '-N', '.') 
        success, output = self.run_git('diff')
        return output if success else ""

    def commit_all(self, message):
        """Добавляет все файлы и делает коммит"""
        add_success, add_err = self.run_git('add', '.')
        if not add_success:
            return False, f"Ошибка git add: {add_err}"
            
        commit_success, commit_err = self.run_git('commit', '-m', message)
        if not commit_success:
            return False, f"Ошибка git commit: {commit_err}"
            
        return True, "Коммит успешно создан!"