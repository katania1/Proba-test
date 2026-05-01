import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QTextEdit, QLabel, QMessageBox, QLineEdit, QFrame,
                             QTreeWidget, QTreeWidgetItem, QWidget, QCheckBox,
                             QMenu, QSplitter, QTextBrowser, QListWidget, QListWidgetItem, QTabWidget)
from PyQt6.QtCore import Qt

# ==========================================
# МАШИНА ВРЕМЕНИ ДЛЯ GIT (С ПОДСВЕТКОЙ И ВКЛАДКАМИ)
# ==========================================
class GitHistoryDialog(QDialog):
    def __init__(self, parent, git_manager, file_path):
        super().__init__(parent)
        self.git_manager = git_manager
        self.file_path = file_path
        self.setWindowTitle(f"🕒 Git-История: {os.path.basename(file_path)}")
        self.resize(850, 600) # Окно чуть шире для комфортного чтения кода
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.init_ui()
        self.load_history()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        lbl = QLabel(f"История файла: {self.file_path}")
        lbl.setStyleSheet("font-weight: bold; color: #569cd6; font-size: 14px;")
        layout.addWidget(lbl)
        
        splitter = QSplitter(Qt.Orientation.Horizontal) # Слева коммиты, справа код
        
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; font-size: 13px; padding: 5px;")
        self.history_list.itemSelectionChanged.connect(self.on_commit_selected)
        splitter.addWidget(self.history_list)
        
        # --- НОВОЕ: ВКЛАДКИ ДЛЯ КОДА ---
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #3c3c3c; }
            QTabBar::tab { background: #252526; color: #888888; padding: 6px 15px; border: 1px solid #3c3c3c; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px;}
            QTabBar::tab:selected { background: #1e1e1e; color: #d4d4d4; font-weight: bold; border-bottom: 1px solid #1e1e1e;}
            QTabBar::tab:hover:!selected { background: #2a2d2e; }
        """)
        
        self.diff_viewer = QTextBrowser()
        self.diff_viewer.setStyleSheet("background-color: #1e1e1e; border: none;")
        
        self.raw_viewer = QTextBrowser()
        self.raw_viewer.setStyleSheet("background-color: #1e1e1e; font-family: Consolas, monospace; font-size: 13px; border: none;")
        
        self.tabs.addTab(self.diff_viewer, "📝 Изменения (Diff)")
        self.tabs.addTab(self.raw_viewer, "📄 Весь файл (Raw)")
        
        splitter.addWidget(self.tabs)
        # --------------------------------
        
        splitter.setSizes([250, 600]) # Пропорции сплиттера
        layout.addWidget(splitter, 1)
        
        btn_layout = QHBoxLayout()
        self.btn_restore = QPushButton("🎯 Восстановить эту версию")
        self.btn_restore.setStyleSheet("background-color: #c75450; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px;")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self.restore_version)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_restore)
        layout.addLayout(btn_layout)

    def format_diff_to_html(self, diff_text):
        """Превращает сырой текст патча в красивый HTML с подсветкой"""
        html = "<div style='font-family: Consolas, monospace; font-size: 13px; white-space: pre-wrap; line-height: 1.4;'>"
        for line in diff_text.split('\n'):
            # Экранируем HTML-теги внутри кода
            escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            if escaped.startswith('+') and not escaped.startswith('+++'):
                html += f"<div style='background-color: #203525; color: #4CAF50; padding: 0 4px;'>{escaped}</div>"
            elif escaped.startswith('-') and not escaped.startswith('---'):
                html += f"<div style='background-color: #3d2325; color: #F44336; padding: 0 4px;'>{escaped}</div>"
            elif escaped.startswith('@@'):
                html += f"<div style='color: #00BCD4; padding: 0 4px; margin-top: 8px;'>{escaped}</div>"
            elif escaped.startswith('diff') or escaped.startswith('index') or escaped.startswith('---') or escaped.startswith('+++'):
                html += f"<div style='color: #888888; font-weight: bold; padding: 0 4px;'>{escaped}</div>"
            else:
                html += f"<div style='color: #d4d4d4; padding: 0 4px;'>{escaped}</div>"
        html += "</div>"
        return html
        
    def load_history(self):
        history = self.git_manager.get_file_history(self.file_path)
        if not history:
            item = QListWidgetItem("История пуста.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_list.addItem(item)
            return
            
        for entry in history:
            item = QListWidgetItem(f"[{entry['date']}] {entry['message']}")
            item.setData(Qt.ItemDataRole.UserRole, entry['hash'])
            self.history_list.addItem(item)
            
    def on_commit_selected(self):
        items = self.history_list.selectedItems()
        if not items: return
        commit_hash = items[0].data(Qt.ItemDataRole.UserRole)
        if not commit_hash: return
        
        self.btn_restore.setEnabled(True)
        self.diff_viewer.setText("⏳ Загрузка...")
        self.raw_viewer.setText("⏳ Загрузка...")
        
        # 1. Загружаем полный файл (Raw)
        code = self.git_manager.get_file_content_at_commit(self.file_path, commit_hash)
        self.raw_viewer.setPlainText(code)
        
        # 2. Загружаем и раскрашиваем Diff
        raw_diff = self.git_manager.get_commit_diff(self.file_path, commit_hash)
        if not raw_diff.strip():
            self.diff_viewer.setHtml("<span style='color:#888888; font-family: sans-serif;'><br>В этом коммите файл не менялся (возможно, он был просто переименован или скопирован).</span>")
        else:
            self.diff_viewer.setHtml(self.format_diff_to_html(raw_diff))
        
    def restore_version(self):
        items = self.history_list.selectedItems()
        if not items: return
        commit_hash = items[0].data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(self, "⚠️ Внимание", f"Перезаписать текущий файл версией из коммита {commit_hash}?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = self.git_manager.restore_file_to_commit(self.file_path, commit_hash)
            if success:
                QMessageBox.information(self, "Успех", "✅ Файл успешно восстановлен!\n(Не забудьте переоткрыть его в редакторе).")
                self.accept()
            else:
                QMessageBox.critical(self, "Ошибка", f"Не удалось восстановить файл:\n{msg}")

# ==========================================
# ОСНОВНОЕ ОКНО GIT
# ==========================================
class GitDialog(QDialog):
    def __init__(self, parent, git_manager):
        super().__init__(parent)
        self.git_manager = git_manager
        self.parent_window = parent
        self.setWindowTitle("📦 Управление Git и GitHub (Pro)")
        self.resize(700, 650)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        self.init_ui()
        self.load_remote_url()
        self.load_file_tree()

    def init_ui(self):
        layout = QVBoxLayout(self)

        lbl_local = QLabel("1. Локальное сохранение (Commit) и Выбор файлов")
        lbl_local.setStyleSheet("font-size: 14px; font-weight: bold; color: #569cd6;")
        layout.addWidget(lbl_local)
        
        file_header_layout = QHBoxLayout()
        lbl_files = QLabel("Структура измененных файлов:")
        
        self.cb_show_all = QCheckBox("Показать ВСЕ файлы проекта (для извлечения из облака)")
        self.cb_show_all.setStyleSheet("""
            QCheckBox { color: #aaaaaa; font-weight: bold; outline: none; }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border: 1px solid #888888; border-radius: 2px;
                background-color: #1e1e1e;
            }
            QCheckBox::indicator:checked { background-color: #0e639c; border: 1px solid #0e639c; }
            QCheckBox::indicator:hover { background-color: #2a2d2e; }
        """)
        self.cb_show_all.stateChanged.connect(self.load_file_tree)
        
        file_header_layout.addWidget(lbl_files)
        file_header_layout.addStretch()
        file_header_layout.addWidget(self.cb_show_all)
        layout.addLayout(file_header_layout)
        
        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setMinimumHeight(250) 
        
        self.file_tree.setStyleSheet("""
            QTreeView { background-color: #252526; border: 1px solid #3c3c3c; font-size: 13px; padding: 5px; outline: none; }
            QTreeView::item { margin: 2px 0px; padding: 3px; }
            QTreeView::item:hover { background-color: #2a2d2e; border-radius: 3px; }
            QTreeView::indicator { width: 14px; height: 14px; border: 1px solid #888888; border-radius: 2px; background-color: #1e1e1e; }
            QTreeView::indicator:checked { background-color: #0e639c; border: 1px solid #0e639c; }
            QTreeView::indicator:indeterminate { background-color: #555555; border: 1px solid #555555; }
        """)
        
        self.file_tree.itemChanged.connect(self.handle_item_changed)
        self.file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self.show_context_menu)
        
        layout.addWidget(self.file_tree, 1) 
        
        sel_layout = QHBoxLayout()
        sel_layout.setContentsMargins(0, 0, 0, 0)
        btn_sel_all = QPushButton("Выбрать всё")
        btn_sel_all.setStyleSheet("background-color: #333333; padding: 4px 10px; border-radius: 3px;")
        btn_sel_all.clicked.connect(lambda: self.toggle_all_files(True))
        btn_sel_none = QPushButton("Снять выделение")
        btn_sel_none.setStyleSheet("background-color: #333333; padding: 4px 10px; border-radius: 3px;")
        btn_sel_none.clicked.connect(lambda: self.toggle_all_files(False))
        sel_layout.addWidget(btn_sel_all)
        sel_layout.addWidget(btn_sel_none)
        sel_layout.addStretch()
        layout.addLayout(sel_layout)

        self.text_input = QTextEdit()
        self.text_input.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; font-size: 14px; padding: 10px;")
        self.text_input.setPlaceholderText("Напишите текст коммита (или нажмите '✨ Сгенерировать ИИ-описание')...")
        self.text_input.setMaximumHeight(80) 
        layout.addWidget(self.text_input)

        btn_layout = QHBoxLayout()
        self.btn_ai = QPushButton("✨ Сгенерировать ИИ-описание")
        self.btn_ai.setStyleSheet("background-color: #673ab7; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px;")
        self.btn_ai.clicked.connect(self.generate_ai_commit)
        self.btn_commit = QPushButton("✅ Сделать Commit")
        self.btn_commit.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px;")
        self.btn_commit.clicked.connect(self.make_commit)
        btn_layout.addWidget(self.btn_ai)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_commit)
        layout.addLayout(btn_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: #3c3c3c; margin-top: 10px; margin-bottom: 10px;")
        layout.addWidget(line)

        lbl_cloud = QLabel("2. Синхронизация с GitHub (Push / Pull)")
        lbl_cloud.setStyleSheet("font-size: 14px; font-weight: bold; color: #e6a822;")
        layout.addWidget(lbl_cloud)

        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setStyleSheet("background-color: #252526; border: 1px solid #3c3c3c; padding: 6px;")
        self.url_input.setPlaceholderText("https://github.com/Имя/Репозиторий.git")
        self.btn_link = QPushButton("🔗 Привязать")
        self.btn_link.setStyleSheet("background-color: #0e639c; color: white; font-weight: bold; padding: 6px 15px; border-radius: 4px;")
        self.btn_link.clicked.connect(self.link_remote)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.btn_link)
        layout.addLayout(url_layout)

        cloud_buttons_layout = QHBoxLayout()
        self.btn_pull = QPushButton("⬇️ Скачать всё")
        self.btn_pull.setStyleSheet("background-color: #1976d2; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        self.btn_pull.clicked.connect(self.pull_code)
        
        self.btn_pull_surgical = QPushButton("🎯 Скачать выбранные")
        self.btn_pull_surgical.setStyleSheet("background-color: #7b1fa2; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        self.btn_pull_surgical.setToolTip("Скачает только те файлы, которые отмечены галочками в дереве сверху")
        self.btn_pull_surgical.clicked.connect(self.pull_surgical)

        self.btn_push = QPushButton("☁️ Отправить (Push)")
        self.btn_push.setStyleSheet("background-color: #005f73; color: white; font-weight: bold; padding: 10px; border-radius: 4px;")
        self.btn_push.clicked.connect(self.push_code)
        
        cloud_buttons_layout.addWidget(self.btn_pull)
        cloud_buttons_layout.addWidget(self.btn_pull_surgical)
        cloud_buttons_layout.addWidget(self.btn_push)
        layout.addLayout(cloud_buttons_layout)


    def show_context_menu(self, pos):
        item = self.file_tree.itemAt(pos)
        if not item: return
        file_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path: return 
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background-color: #0e639c; }
        """)
        
        action_history = menu.addAction("🕒 Посмотреть Git-историю файла")
        action = menu.exec(self.file_tree.viewport().mapToGlobal(pos))
        
        if action == action_history:
            dialog = GitHistoryDialog(self, self.git_manager, file_path)
            if dialog.exec(): 
                self.load_file_tree() 
                self.parent_window.update_git_status()

    # ==========================================
    # УМНАЯ ЛОГИКА ДЕРЕВА И СВОРАЧИВАНИЯ
    # ==========================================
    def load_file_tree(self):
        self.file_tree.blockSignals(True)
        self.file_tree.clear()
        
        if self.cb_show_all.isChecked():
            files = self.git_manager.get_all_tracked_files()
            default_check = Qt.CheckState.Unchecked
        else:
            files = self.git_manager.get_changed_files()
            default_check = Qt.CheckState.Checked
            
        if not files:
            item = QTreeWidgetItem(["Нет измененных файлов." if not self.cb_show_all.isChecked() else "Репозиторий пуст."])
            self.file_tree.addTopLevelItem(item)
            self.file_tree.blockSignals(False)
            return
            
        cleaned_files = sorted([f.replace('\\', '/').strip(' /"') for f in files if f.strip(' /"')])
        folder_nodes = {}

        for file_path in cleaned_files:
            parts = file_path.split('/')
            parent_node = None
            current_path = ""

            for i, part in enumerate(parts):
                is_file = (i == len(parts) - 1)
                current_path = f"{current_path}/{part}" if current_path else part

                if not is_file:
                    if current_path not in folder_nodes:
                        node = QTreeWidgetItem([part])
                        node.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
                        node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        node.setCheckState(0, default_check)
                        
                        if parent_node is None: self.file_tree.addTopLevelItem(node)
                        else: parent_node.addChild(node)
                        folder_nodes[current_path] = node
                    parent_node = folder_nodes[current_path]
                else:
                    node = QTreeWidgetItem([part])
                    node.setIcon(0, self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
                    node.setFlags(node.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    node.setCheckState(0, default_check)
                    node.setData(0, Qt.ItemDataRole.UserRole, file_path) 
                    
                    if parent_node is None: self.file_tree.addTopLevelItem(node)
                    else: parent_node.addChild(node)

        # Всегда сворачиваем дерево при загрузке, чтобы было аккуратно
        self.file_tree.collapseAll() 
        
        self.file_tree.blockSignals(False)

    def handle_item_changed(self, item, column):
        self.file_tree.blockSignals(True)
        state = item.checkState(column)
        self._set_children_state(item, state)
        self._update_parent_state(item.parent())
        self.file_tree.blockSignals(False)

    def _set_children_state(self, item, state):
        for i in range(item.childCount()):
            child = item.child(i)
            child.setCheckState(0, state)
            self._set_children_state(child, state)

    def _update_parent_state(self, parent):
        if not parent: return
        checked_count = 0
        unchecked_count = 0
        for i in range(parent.childCount()):
            state = parent.child(i).checkState(0)
            if state == Qt.CheckState.Checked: checked_count += 1
            elif state == Qt.CheckState.Unchecked: unchecked_count += 1
            else: checked_count += 1 

        if checked_count == parent.childCount(): parent.setCheckState(0, Qt.CheckState.Checked)
        elif unchecked_count == parent.childCount(): parent.setCheckState(0, Qt.CheckState.Unchecked)
        else: parent.setCheckState(0, Qt.CheckState.PartiallyChecked)
        self._update_parent_state(parent.parent())

    def get_selected_files(self):
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        selected = []
        iterator = QTreeWidgetItemIterator(self.file_tree)
        while iterator.value():
            item = iterator.value()
            if item.childCount() == 0 and item.checkState(0) == Qt.CheckState.Checked:
                path = item.data(0, Qt.ItemDataRole.UserRole)
                if path: selected.append(path)
            iterator += 1
        return selected

    def toggle_all_files(self, state):
        check_state = Qt.CheckState.Checked if state else Qt.CheckState.Unchecked
        self.file_tree.blockSignals(True)
        for i in range(self.file_tree.topLevelItemCount()):
            item = self.file_tree.topLevelItem(i)
            item.setCheckState(0, check_state)
            self._set_children_state(item, check_state)
        self.file_tree.blockSignals(False)

    def load_remote_url(self):
        url = self.git_manager.get_remote_url()
        if url: self.url_input.setText(url)

    def generate_ai_commit(self):
        selected_files = self.get_selected_files()
        if not selected_files:
            QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один файл для генерации описания!")
            return
        diff = self.git_manager.get_diff_for_files(selected_files)
        if not diff:
            QMessageBox.information(self, "Пусто", "Нет изменений в выбранных файлах.")
            return
            
        # Меняем текст кнопки и НЕ закрываем окно!
        self.btn_ai.setText("⏳ Ожидание ИИ...")
        self.btn_ai.setEnabled(False)
        self.parent_window.request_ai_commit_message(diff)

    def make_commit(self):
        selected_files = self.get_selected_files()
        if not selected_files:
            QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один файл для коммита!")
            return
        msg = self.text_input.toPlainText().strip()
        if not msg:
            QMessageBox.warning(self, "Ошибка", "Введите описание коммита!")
            return
        success, result = self.git_manager.commit_selected(msg, selected_files)
        if success:
            QMessageBox.information(self, "Успех", "✅ " + result)
            self.text_input.clear()
            self.cb_show_all.setChecked(False) 
            self.load_file_tree()
            self.parent_window.update_git_status()
        else:
            QMessageBox.critical(self, "Ошибка Git", result)

    def link_remote(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Ошибка", "Введите ссылку на репозиторий GitHub!")
            return
        success, msg = self.git_manager.set_remote_url(url)
        if success: QMessageBox.information(self, "Успех", "✅ Репозиторий успешно привязан!")
        else: QMessageBox.critical(self, "Ошибка", f"Не удалось привязать репозиторий:\n{msg}")

    def push_code(self):
        if not self.git_manager.get_remote_url():
            QMessageBox.warning(self, "Ошибка", "Сначала привяжите ссылку на репозиторий GitHub!")
            return
        self.btn_push.setText("⏳ Отправка...")
        self.btn_push.setEnabled(False)
        self.repaint()
        success, msg = self.git_manager.push_to_cloud()
        self.btn_push.setText("☁️ Отправить (Push)")
        self.btn_push.setEnabled(True)
        if success: QMessageBox.information(self, "Успех", "✅ Код успешно отправлен в GitHub!")
        else: QMessageBox.critical(self, "Ошибка Push", f"Не удалось отправить код:\n{msg}\n\nВозможно, нужно авторизоваться или репозиторий не пустой.")

    def pull_code(self):
        if not self.git_manager.get_remote_url():
            QMessageBox.warning(self, "Ошибка", "Сначала привяжите ссылку на репозиторий GitHub!")
            return
        self.btn_pull.setText("⏳ Скачивание...")
        self.btn_pull.setEnabled(False)
        self.repaint()
        success, msg = self.git_manager.pull_from_cloud()
        self.btn_pull.setText("⬇️ Скачать всё")
        self.btn_pull.setEnabled(True)
        if success:
            QMessageBox.information(self, "Успех", "✅ Код успешно скачан с GitHub!\n(Если у вас были открыты вкладки с файлами, переоткройте их).")
            self.parent_window.update_git_status()
            self.load_file_tree()
        else:
            QMessageBox.critical(self, "Ошибка Pull", f"Не удалось скачать код:\n{msg}\n\nВозможно, у вас есть локальные конфликты.")

    def pull_surgical(self):
        if not self.git_manager.get_remote_url():
            QMessageBox.warning(self, "Ошибка", "Сначала привяжите ссылку на репозиторий GitHub!")
            return
        selected_files = self.get_selected_files()
        if not selected_files:
            QMessageBox.warning(self, "Ошибка", "Сначала поставьте галочки на файлах в дереве сверху!")
            return
        reply = QMessageBox.question(self, "⚠️ Внимание", 
                                     f"Вы собираетесь перезаписать {len(selected_files)} файла(ов) версиями из GitHub.\nВаши локальные изменения в них будут потеряны.\n\nПродолжить?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No: return
        self.btn_pull_surgical.setText("⏳ Извлечение...")
        self.btn_pull_surgical.setEnabled(False)
        self.repaint()
        success, msg = self.git_manager.pull_specific_files(selected_files)
        self.btn_pull_surgical.setText("🎯 Скачать выбранные")
        self.btn_pull_surgical.setEnabled(True)
        if success:
            QMessageBox.information(self, "Успех", f"✅ {msg}\nПереоткройте эти файлы в редакторе.")
            self.parent_window.update_git_status()
            self.load_file_tree()
        else:
            QMessageBox.critical(self, "Ошибка", msg)