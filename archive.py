# TODO : 
import os
import sys
import json
import fitz
from webdav3.client import Client
from PIL import Image
import shutil
from datetime import datetime
import io
from dotenv import load_dotenv
import webbrowser
from preview_generator.manager import PreviewManager as PreviewManagerBase
import tempfile
# весь наш интерфейс, сложно но можно
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon, QFontMetrics
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QListWidget, 
                            QPushButton, QFileDialog, QMessageBox, QLabel, QHBoxLayout,
                            QScrollArea, QListWidgetItem, QSizePolicy, QComboBox, 
                            QLineEdit, QDialog, QFormLayout, QDialogButtonBox, QTabWidget,
                            QTableWidget, QTableWidgetItem, QHeaderView)


load_dotenv()

class PreviewThread(QThread):
    preview_generated = pyqtSignal(str, QPixmap)  # Сигнал: путь файла и превью
    
    def __init__(self, file_path, preview_manager):
        super().__init__()
        self.file_path = file_path
        self.preview_manager = preview_manager
    
    def run(self):
        """Генерация превью в отдельном потоке"""
        try:
            if self.file_path.startswith('yadisk:'):
                self.preview_generated.emit(self.file_path, None)
                return
                
            if not os.path.exists(self.file_path):
                self.preview_generated.emit(self.file_path, None)
                return
            
            # Генерируем превью
            preview_path = self.preview_manager.create_preview(self.file_path)
            if preview_path and os.path.exists(preview_path):
                pixmap = QPixmap(preview_path)
                self.preview_generated.emit(self.file_path, pixmap)
            else:
                self.preview_generated.emit(self.file_path, None)
                
        except Exception as e:
            print(f"Ошибка генерации превью в потоке: {e}")
            self.preview_generated.emit(self.file_path, None)

class PreviewManager:
    def __init__(self):
        # Создаем временную директорию для кэша превью
        self.cache_dir = os.path.join(tempfile.gettempdir(), 'document_archive_previews')
        os.makedirs(self.cache_dir, exist_ok=True)
        self.manager = PreviewManagerBase(self.cache_dir, create_folder=True)
    
    def create_preview(self, file_path, output_path=None):
        """Создает превью для файла любого поддерживаемого формата"""
        try:
            # Для удаленных файлов превью не доступно
            if file_path.startswith('yadisk:'):
                return None
                
            # Если файл не существует, возвращаем None
            if not os.path.exists(file_path):
                return None
            
            # Создаем временный файл для превью, если не указан выходной путь
            if output_path is None:
                output_path = os.path.join(self.cache_dir, f"preview_{os.path.basename(file_path)}.png")
            
            # Генерируем превью
            preview_path = self.manager.get_jpeg_preview(
                file_path, 
                width=800, 
                height=600
            )
            
            # Копируем превью в нужное место
            if preview_path and os.path.exists(preview_path):
                if output_path != preview_path:
                    shutil.copy2(preview_path, output_path)
                return output_path
            return None

        except Exception as e:
            print(f"Ошибка создания превью: {e}")
            return None
    
    def get_preview_pixmap(self, file_path):
        """Возвращает QPixmap с превью документа"""
        preview_path = self.create_preview(file_path)
        if preview_path and os.path.exists(preview_path):
            pixmap = QPixmap(preview_path)
            if not pixmap.isNull():
                return pixmap
        return None
    
    def cleanup(self):
        """Очищает кэш превью"""
        try:
            shutil.rmtree(self.cache_dir)
            os.makedirs(self.cache_dir, exist_ok=True)
        except Exception as e:
            print(f"Ошибка очистки кэша превью: {e}")

class OpenFileThread(QThread):
    finished = pyqtSignal()
    
    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path
    
    def run(self):
        try:
            if sys.platform == 'win32':
                os.startfile(self.file_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{self.file_path}"')
            else:
                os.system(f'xdg-open "{self.file_path}"')
        except Exception as e:
            print(f"Ошибка открытия файла: {e}")
        finally:
            self.finished.emit()

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setFixedSize(600, 400)
        
        self.parent = parent
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        self.senders_tab = QWidget()
        self.senders_layout = QVBoxLayout(self.senders_tab)
        
        self.senders_table = QTableWidget()
        self.senders_table.setColumnCount(3)
        self.senders_table.setHorizontalHeaderLabels(["ID", "Имя", "Описание"])
        self.senders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.senders_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        add_sender_btn = QPushButton("Добавить отправителя")
        add_sender_btn.clicked.connect(self.add_sender)
        remove_sender_btn = QPushButton("Удалить выбранного")
        remove_sender_btn.clicked.connect(self.remove_sender)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(add_sender_btn)
        btn_layout.addWidget(remove_sender_btn)
        
        self.senders_layout.addWidget(self.senders_table)
        self.senders_layout.addLayout(btn_layout)
        
        self.executors_tab = QWidget()
        self.executors_layout = QVBoxLayout(self.executors_tab)
        
        self.executors_table = QTableWidget()
        self.executors_table.setColumnCount(3)
        self.executors_table.setHorizontalHeaderLabels(["ID", "Имя", "Описание"])
        self.executors_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.executors_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        
        add_executor_btn = QPushButton("Добавить исполнителя")
        add_executor_btn.clicked.connect(self.add_executor)
        remove_executor_btn = QPushButton("Удалить выбранного")
        remove_executor_btn.clicked.connect(self.remove_executor)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(add_executor_btn)
        btn_layout.addWidget(remove_executor_btn)
        
        self.executors_layout.addWidget(self.executors_table)
        self.executors_layout.addLayout(btn_layout)
        
        tabs.addTab(self.senders_tab, "Отправители")
        tabs.addTab(self.executors_tab, "Исполнители")
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def load_data(self):
        """Загрузка данных отправителей и исполнителей"""
        data = self.parent.load_data()
        
        self.senders_table.setRowCount(len(data["senders"]))
        for row, sender in enumerate(data["senders"]):
            self.senders_table.setItem(row, 0, QTableWidgetItem(str(sender["id"])))
            self.senders_table.setItem(row, 1, QTableWidgetItem(sender["name"]))
            self.senders_table.setItem(row, 2, QTableWidgetItem(sender.get("description", "")))
        
        self.executors_table.setRowCount(len(data["executors"]))
        for row, executor in enumerate(data["executors"]):
            self.executors_table.setItem(row, 0, QTableWidgetItem(str(executor["id"])))
            self.executors_table.setItem(row, 1, QTableWidgetItem(executor["name"]))
            self.executors_table.setItem(row, 2, QTableWidgetItem(executor.get("description", "")))
    
    def add_sender(self):
        """Добавление нового отправителя"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить отправителя")
        dialog.setFixedSize(300, 150)
        
        layout = QFormLayout()
        dialog.setLayout(layout)
        
        name_edit = QLineEdit()
        description_edit = QLineEdit()
        
        layout.addRow("Имя:", name_edit)
        layout.addRow("Описание:", description_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        
        layout.addRow(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Ошибка", "Имя не может быть пустым")
                return
            
            data = self.parent.load_data()
            if any(s["name"].lower() == name.lower() for s in data["senders"]):
                QMessageBox.warning(self, "Ошибка", "Отправитель с таким именем уже существует")
                return
            
            new_id = max(s["id"] for s in data["senders"]) + 1 if data["senders"] else 1
            new_sender = {
                "id": new_id,
                "name": name,
                "description": description_edit.text(),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            data["senders"].append(new_sender)
            self.parent.save_data(data)
            self.load_data()
    
    def remove_sender(self):
        """Удаление выбранного отправителя"""
        selected = self.senders_table.currentRow()
        if selected == -1:
            QMessageBox.warning(self, "Ошибка", "Выберите отправителя для удаления")
            return
        
        sender_id = int(self.senders_table.item(selected, 0).text())
        sender_name = self.senders_table.item(selected, 1).text()
        
        reply = QMessageBox.question(
            self, 
            'Подтверждение', 
            f'Вы уверены что хотите удалить отправителя "{sender_name}"?', 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            data = self.parent.load_data()
            data["senders"] = [s for s in data["senders"] if s["id"] != sender_id]
            self.parent.save_data(data)
            self.load_data()
    
    def add_executor(self):
        """Добавление нового исполнителя"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить исполнителя")
        dialog.setFixedSize(300, 150)
        
        layout = QFormLayout()
        dialog.setLayout(layout)
        
        name_edit = QLineEdit()
        description_edit = QLineEdit()
        
        layout.addRow("Имя:", name_edit)
        layout.addRow("Описание:", description_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        
        layout.addRow(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Ошибка", "Имя не может быть пустым")
                return
            
            data = self.parent.load_data()
            if any(e["name"].lower() == name.lower() for e in data["executors"]):
                QMessageBox.warning(self, "Ошибка", "Исполнитель с таким именем уже существует")
                return
            
            new_id = max(e["id"] for e in data["executors"]) + 1 if data["executors"] else 1
            new_executor = {
                "id": new_id,
                "name": name,
                "description": description_edit.text(),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            data["executors"].append(new_executor)
            self.parent.save_data(data)
            self.load_data()
    
    def remove_executor(self):
        """Удаление выбранного исполнителя"""
        selected = self.executors_table.currentRow()
        if selected == -1:
            QMessageBox.warning(self, "Ошибка", "Выберите исполнителя для удаления")
            return
        
        executor_id = int(self.executors_table.item(selected, 0).text())
        executor_name = self.executors_table.item(selected, 1).text()
        
        reply = QMessageBox.question(
            self, 
            'Подтверждение', 
            f'Вы уверены что хотите удалить исполнителя "{executor_name}"?', 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            data = self.parent.load_data()
            data["executors"] = [e for e in data["executors"] if e["id"] != executor_id]
            self.parent.save_data(data)
            self.load_data()


class DocumentUploadDialog(QDialog):
    def __init__(self, doc_type, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Детали {'входящего' if doc_type == 'incoming' else 'исходящего'} письма")
        self.setFixedSize(300, 200)
        
        layout = QFormLayout()
        self.setLayout(layout)
        
        self.doc_number = QLineEdit()
        self.doc_date = QLineEdit()
        self.doc_date.setPlaceholderText("ДД.ММ.ГГГГ")
        
        layout.addRow("Номер письма:", self.doc_number)
        layout.addRow("Дата письма:", self.doc_date)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addRow(button_box)
    
    def get_data(self):
        return {
            "doc_number": self.doc_number.text().strip(),
            "doc_date": self.doc_date.text().strip()
        }

class DocumentManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Архив Local/Web")
        self.setGeometry(100, 100, 1000, 600)
        
        self.base_dir = os.path.join(os.path.dirname(__file__), "Документы архива")
        self.documents_dir = os.path.join(self.base_dir, "Документы")
        self.incoming_dir = os.path.join(self.base_dir, "Входящее")
        self.outgoing_dir = os.path.join(self.base_dir, "Исходящее")
        self.executors_dir = os.path.join(self.base_dir, "Исполнители")
        
        os.makedirs(self.documents_dir, exist_ok=True)
        os.makedirs(self.incoming_dir, exist_ok=True)
        os.makedirs(self.outgoing_dir, exist_ok=True)
        os.makedirs(self.executors_dir, exist_ok=True)
        
        self.data_file = os.path.join(self.base_dir, "data.json")
        self.init_data()

        self.preview_manager = PreviewManager()

        self.preview_thread = None
        
        yandex_login = os.getenv('yandex_login')
        yandex_password = os.getenv('yandex_password')

        self.webdav_client = Client({
            'webdav_hostname': 'https://webdav.yandex.ru',
            'webdav_login': yandex_login,  
            'webdav_password': yandex_password      
        })
        
        self.init_ui()
        self.migrate_data()
        self.load_documents()
        self.showMaximized()

    def init_data(self):
        """Инициализация данных при первом запуске"""
        if not os.path.exists(self.data_file):
            data = {
                "documents": [],
                "senders": [],
                "executors": [],
                "current_user": None
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
    
    def load_data(self):
        """Загрузка данных из JSON"""
        with open(self.data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_data(self, data):
        """Сохранение данных в JSON"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    
    def update_preview(self, file_path):
        """Запускает генерацию превью в отдельном потоке"""
        try:
            if file_path.startswith('yadisk:'):
                self.clear_preview()
                return
            
            # Останавливаем предыдущий поток, если он запущен
            if self.preview_thread and self.preview_thread.isRunning():
                self.preview_thread.quit()
                self.preview_thread.wait()
            
            # Создаем и запускаем новый поток
            self.preview_thread = PreviewThread(file_path, self.preview_manager)
            self.preview_thread.preview_generated.connect(self.on_preview_generated)
            self.preview_thread.start()
            
            # Временно показываем сообщение о загрузке
            self.preview_widget.clear()
            self.preview_widget.setText("Генерация превью...")
                
        except Exception as e:
            print(f"Ошибка запуска потока превью: {e}")
            self.clear_preview()

    def on_preview_generated(self, file_path, pixmap):
        """Обработчик завершения генерации превью"""
        # Проверяем, что превью соответствует текущему документу
        current_item = self.documents_list.currentItem()
        if current_item and current_item.data(Qt.ItemDataRole.UserRole)["path"] == file_path:
            if pixmap and not pixmap.isNull():
                # Масштабируем превью под размер виджета
                scaled_pixmap = pixmap.scaled(
                    self.preview_widget.width() - 20, 
                    self.preview_widget.height() - 20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.preview_widget.setPixmap(scaled_pixmap)
            else:
                self.clear_preview()

    def clear_preview(self):
        """Очищает область превью"""
        self.preview_widget.clear()
        self.preview_widget.setText("Превью недоступно для этого формата ^_^")        

    def create_preview(pdf_path):
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap()
        output = "preview.png"
        pix.save(output)
        return output

    def check_remote_updates(self):
        """Проверка новых документов на Яндекс.Диске"""
        try:
            remote_docs = []
            base_dir = '/Документы/'
            
            # Проверяем папку Входящие
            incoming_dir = f'{base_dir}Входящие/'
            if self.webdav_client.check(incoming_dir):
                for item in self.webdav_client.list(incoming_dir):
                    if not item.endswith('/'):
                        remote_docs.append({
                            'path': incoming_dir + item,
                            'type': 'incoming',
                            'filename': item
                        })
                
                # Проверяем подпапки отправителей
                for sender in self.webdav_client.list(incoming_dir):
                    if sender.endswith('/'):
                        sender_dir = incoming_dir + sender
                        for item in self.webdav_client.list(sender_dir):
                            if not item.endswith('/'):
                                remote_docs.append({
                                    'path': sender_dir + item,
                                    'type': 'incoming',
                                    'sender': sender[:-1],
                                    'filename': item
                                })
            
            # Проверяем папку Исходящие
            outgoing_dir = f'{base_dir}Исходящие/'
            if self.webdav_client.check(outgoing_dir):
                for item in self.webdav_client.list(outgoing_dir):
                    if not item.endswith('/'):
                        remote_docs.append({
                            'path': outgoing_dir + item,
                            'type': 'outgoing',
                            'filename': item
                        })
            
            return remote_docs
            
        except Exception as e:
            print(f"Ошибка проверки обновлений: {e}")
            return []

    def sync_documents(self):
        """Ручная синхронизация с Яндекс.Диском"""
        try:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            
            remote_docs = self.check_remote_updates()
            data = self.load_data()
            updated = False
            
            # Создаем множество существующих документов для быстрой проверки
            existing_docs = {
                (d['filename'].lower(), 
                d['type'], 
                d.get('doc_number', '').lower(),
                d.get('sender', '').lower(),
                d.get('executor', '').lower())
                for d in data['documents']
            }
            
            for remote in remote_docs:
                # Проверяем дубликаты
                doc_key = (
                    remote['filename'].lower(),
                    remote['type'],
                    remote.get('doc_number', '').lower(),
                    remote.get('sender', '').lower(),
                    remote.get('executor', '').lower()
                )
                
                if doc_key not in existing_docs:
                    doc_data = {
                        'filename': remote['filename'],
                        'type': remote['type'],
                        'path': f"yadisk:{remote['path']}",
                        'remote_path': remote['path'],
                        'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'size': self.webdav_client.info(remote['path']).get('size', 0)
                    }
                    
                    if 'sender' in remote:
                        doc_data['sender'] = remote['sender']
                    if 'doc_number' in remote:
                        doc_data['doc_number'] = remote['doc_number']
                    
                    data['documents'].append(doc_data)
                    updated = True
            
            if updated:
                self.save_data(data)
                self.load_documents()
                QMessageBox.information(self, "Синхронизация", "Документы успешно синхронизированы")
            else:
                QMessageBox.information(self, "Синхронизация", "Новых документов для синхронизации не найдено")
                
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка синхронизации: {str(e)}")
        finally:
            QApplication.restoreOverrideCursor()

    def download_document(self, remote_path):
        """Загрузка документа с Яндекс.Диска"""
        try:
            filename = os.path.basename(remote_path)
            
            if 'Входящие' in remote_path:
                local_dir = self.incoming_dir
                if 'Входящие/' in remote_path:
                    sender = remote_path.split('Входящие/')[1].split('/')[0]
                    if sender:
                        local_dir = os.path.join(self.incoming_dir, sender)
                        os.makedirs(local_dir, exist_ok=True)
            else:
                local_dir = self.outgoing_dir
            
            local_path = os.path.join(local_dir, filename)
            
            self.webdav_client.download(remote_path, local_path)

            data = self.load_data()
            for doc in data['documents']:
                if doc.get('remote_path') == remote_path:
                    doc['path'] = local_path
                    doc.pop('remote_path', None)
                    break
            
            self.save_data(data)
            self.load_documents()
            QMessageBox.information(self, "Успех", f"Файл {filename} успешно загружен")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Основной layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Левая панель - кнопки управления
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Заголовок
        title_label = QLabel("Архив Local/Web")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                padding: 10px;
                background-color: rgba(0, 0, 0, 0.2);
                border-radius: 5px;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(title_label)
        
        buttons = [
            ("Загрузить документ", self.upload_document),
            ("Удалить документ", lambda: self.delete_document(remote=True)),
            ("Открыть документ", self.open_document_threaded),
            ("Открыть на Я.Диск", self.open_on_yadisk),
            ("Синхронизация", self.sync_documents)
        ]
        
        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: %s;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    margin-top: 10px;
                }
                QPushButton:hover {
                    background-color: %s;
                }
                QPushButton:pressed {
                    background-color: %s;
                }
            """ % (
                "#5a5a5a" if text == "Настройки" else "#4a6fa5",
                "#6a6a6a" if text == "Настройки" else "#5a7fb5",
                "#4a4a4a" if text == "Настройки" else "#3a5f95"
            ))
            btn.setFixedHeight(40)
            btn.clicked.connect(handler)
            left_layout.addWidget(btn)

        left_layout.addStretch()
        buttons = [
            ("Архиватор(тест)", self.open_settings),           ####ТЕСТОВЫЙ ВАРИАНТ НЕ БЕЙТЕ ПО ЛИЦУ
            ("Настройки", self.open_settings)
        ]
        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: %s;
                    color: white;
                    border: none;
                    padding: 10px;
                    border-radius: 5px;
                    font-weight: bold;
                    margin-top: 10px;
                }
                QPushButton:hover {
                    background-color: %s;
                }
                QPushButton:pressed {
                    background-color: %s;
                }
            """ % (
                "#5a5a5a" if text == "Настройки" or "Архиватор(тест)" or "Парсер Госпабликов(тест)" else "#4a6fa5",
                "#6a6a6a" if text == "Настройки" or "Архиватор(тест)" or "Парсер Госпабликов(тест)" else "#5a7fb5",
                "#4a4a4a" if text == "Настройки" or "Архиватор(тест)" or "Парсер Госпабликов(тест)" else "#3a5f95"
            ))
            btn.setFixedHeight(40)
            btn.clicked.connect(handler)
            left_layout.addWidget(btn)
        ######################
        #png-шка в левой панели, многовероятно удалю в конце, но пока что пусть будет
        logo_label = QLabel()
        logo_pixmap = QPixmap("name.png")

        if not logo_pixmap.isNull():
            logo_pixmap = logo_pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
            logo_label.setStyleSheet("background: transparent;")
            left_layout.addWidget(logo_label)

        ###########################
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        
        filter_panel = QWidget()
        filter_layout = QHBoxLayout(filter_panel)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Все", "Входящие", "Исходящие"])
        self.filter_combo.currentTextChanged.connect(self.apply_filters)
        
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self.apply_filters)
        
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addWidget(self.search_edit)
        
        center_layout.addWidget(filter_panel)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: 2px solid #4a6fa5;
                border-radius: 5px;
                background-color: rgba(255, 255, 255, 0.1);
            }
            QScrollBar:vertical {
                width: 15px;
                background: rgba(255, 255, 255, 0.1);
            }
            QScrollBar::handle:vertical {
                background: #4a6fa5;
                min-height: 20px;
                border-radius: 5px;
            }
        """)
        
        self.documents_list = QListWidget()
        self.documents_list.setStyleSheet("""
            QListWidget {
                background-color: rgba(255, 255, 255, 0.05);
                color: white;
                font-size: 14px;
                border: none;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            QListWidget::item:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
            QListWidget::item:selected {
                background-color: #4a6fa5;
            }
        """)
        self.documents_list.itemDoubleClicked.connect(self.open_document_threaded)
        self.documents_list.itemClicked.connect(self.show_document_info)
        scroll_area.setWidget(self.documents_list)
        
        center_layout.addWidget(scroll_area)
        
        right_panel = QWidget()
        right_panel.setFixedWidth(350)
        right_layout = QVBoxLayout(right_panel)
        self.preview_widget = QLabel()
        self.preview_widget.setFixedSize(300, 300)
        self.preview_widget.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid #4a6fa5;
                border-radius: 5px;
            }
        """)
        self.preview_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(self.preview_widget)
        
        info_title = QLabel("Информация о документе")
        info_title.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                padding: 10px;
                background-color: rgba(0, 0, 0, 0.2);
                border-radius: 5px;
            }
        """)
        info_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(info_title)
        
        # Область с информацией
        self.info_widget = QWidget()
        self.info_layout = QFormLayout(self.info_widget)
        self.info_layout.setVerticalSpacing(8)
        self.info_layout.setContentsMargins(15, 10, 10, 10)
        
        # ООООО ЗАЕБ, вечно лагал текст
        fields = [
            ("Название", "name_label"),
            ("Тип", "type_label"),
            ("Номер письма", "doc_number_label"),
            ("Дата письма", "doc_date_label"),
            ("Отправитель", "sender_label"),
            ("Исполнитель", "executor_label"),
            ("Размер", "size_label"),
            ("Путь", "path_label"),
            ("Дата добавления", "date_label")
        ]
        
        for field_name, field_var in fields:
            label = QLabel(field_name + ":")
            label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: white;
                    font-weight: bold;
                }
            """)
            
            value_label = QLabel("-")
            value_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    color: white;
                    margin: 2px;
                    padding: 2px;
                }
            """)
            value_label.setWordWrap(True)
            value_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            value_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
            
            setattr(self, field_var, value_label)
            self.info_layout.addRow(label, value_label)
        
        right_layout.addWidget(self.info_widget)
        right_layout.addStretch()
        
        main_layout.addWidget(left_panel)
        main_layout.addWidget(center_panel)
        main_layout.addWidget(right_panel)
        
        # Стиль главного окна
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                        stop:0 #614385, stop:1 #516395);
            }
            QLineEdit, QComboBox {
                background-color: rgba(255, 255, 255, 0.1);
                color: white;
                border: 1px solid #4a6fa5;
                border-radius: 3px;
                padding: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #516395;
                color: white;
                selection-background-color: #4a6fa5;
            }
        """)
    
    def open_settings(self):
        """Открытие диалога настроек"""
        dialog = SettingsDialog(self)
        dialog.exec()
        self.load_documents()
    
    def apply_filters(self):
        """фильтр поиска с учетом всех полей документа"""
        search_text = self.search_edit.text().lower()
        filter_type = self.filter_combo.currentText()
        
        for i in range(self.documents_list.count()):
            item = self.documents_list.item(i)
            widget = self.documents_list.itemWidget(item)
            doc = item.data(Qt.ItemDataRole.UserRole)
            visible = True
            
            # поиск по всем полям документа
            if search_text:
                search_fields = [
                    doc["filename"].lower(),
                    doc.get("sender", "").lower(),
                    doc.get("executor", "").lower(),
                    doc.get("doc_number", "").lower(),
                    doc.get("doc_date", "").lower(),
                    doc.get("description", "").lower()
                ]
                if not any(search_text in field for field in search_fields):
                    visible = False
            
            # Применяем фильтр по типу
            if visible and filter_type != "Все":
                if filter_type == "Входящие" and doc["type"] != "incoming":
                    visible = False
                
                elif filter_type == "Исходящие" and doc["type"] != "outgoing":
                    visible = False
                
                elif filter_type == "По исполнителям":
                    if not doc.get("executor"):
                        visible = False
                    elif search_text and search_text not in doc.get("executor", "").lower():
                        visible = False
                
                elif filter_type == "По отправителям":
                    if not doc.get("sender"):
                        visible = False
                    elif search_text and search_text not in doc.get("sender", "").lower():
                        visible = False
            
            item.setHidden(not visible)
            
            # Также скрываем/показываем виджет
            if widget:
                widget.setVisible(not visible)

    def load_documents(self):
        """Загрузка списка документов с кнопкой 'Загрузить' справа"""
        data = self.load_data()
        self.documents_list.clear()
        
        for doc in data["documents"]:
            # Создаем элемент списка без текста
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, doc)
            
            if doc['path'].startswith('yadisk:'):
                # Для удаленных файлов устанавливаем иконку и цвет
                item.setIcon(QIcon.fromTheme("cloud-download"))
                item.setForeground(Qt.GlobalColor.gray)
                
                # Создаем виджет с полной информацией
                widget = QWidget()
                layout = QHBoxLayout(widget)
                layout.setContentsMargins(5, 2, 5, 2)
                layout.setSpacing(10)
                
                # Добавляем метку с именем файла
                label = QLabel(doc["filename"])
                label.setStyleSheet("color: gray;")
                label.setWordWrap(False)  # перенос текста

                spacer = QWidget()
                spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
                
                btn = QPushButton("Загрузить")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4a6fa5;
                        color: white;
                        border: none;
                        padding: 3px 8px;
                        border-radius: 4px;
                        font-size: 12px;
                        min-width: 80px;
                    }
                    QPushButton:hover {
                        background-color: #5a7fb5;
                    }
                """)
                btn.clicked.connect(lambda _, p=doc['remote_path']: self.download_document(p))
                
                layout.addWidget(label)
                layout.addWidget(spacer)
                layout.addWidget(btn)
                
                self.documents_list.addItem(item)
                self.documents_list.setItemWidget(item, widget)
                
                # Устанавливаем высоту элемента в зависимости от содержимого
                height = label.sizeHint().height() + 10  # + отступы
                item.setSizeHint(QSize(item.sizeHint().width(), max(40, height)))
            else:
                # Для локальных файлов устанавливаем текст и иконку
                item.setText(doc["filename"])
                
                if doc['filename'].lower().endswith('.pdf'):
                    item.setIcon(QIcon.fromTheme("application-pdf"))
                elif doc['filename'].lower().endswith(('.png', '.jpg', '.jpeg')):
                    item.setIcon(QIcon.fromTheme("image-x-generic"))
                else:
                    item.setIcon(QIcon.fromTheme("text-x-generic"))
                
                self.documents_list.addItem(item)

    def sort_documents(self, key):
        """Сортировка документов по указанному ключу"""
        if hasattr(self, 'last_sort_key') and self.last_sort_key == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_reverse = False
        
        self.last_sort_key = key
        self.load_documents(sort_by=key, reverse=self.sort_reverse)
        
        for field_key, label in self.sort_labels.items():
            if field_key == key:
                label.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        color: #4a6fa5;
                        font-weight: bold;
                        text-decoration: underline;
                    }
                """)
            else:
                label.setStyleSheet("""
                    QLabel {
                        font-size: 12px;
                        color: white;
                        font-weight: bold;
                    }
                    QLabel:hover {
                        color: #4a6fa5;
                        text-decoration: underline;
                    }
                """)    

    def upload_document(self):
        """Загрузка нового документа"""
        type_dialog = QDialog(self)
        type_dialog.setWindowTitle("Выберите тип документа")
        type_dialog.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        type_dialog.setLayout(layout)
        
        label = QLabel("Выберите тип загружаемого документа:")
        incoming_btn = QPushButton("Входящее письмо")
        outgoing_btn = QPushButton("Исходящее письмо")
        
        incoming_btn.clicked.connect(lambda: self.process_document_upload("incoming", type_dialog))
        outgoing_btn.clicked.connect(lambda: self.process_document_upload("outgoing", type_dialog))
        
        layout.addWidget(label)
        layout.addWidget(incoming_btn)
        layout.addWidget(outgoing_btn)
        
        type_dialog.exec()
    
    def upload_to_yadisk(self, file_path, doc_type, doc_data):
        """Загрузка файла на Яндекс.Диск с автоматическим созданием структуры папок"""
        try:
            filename = os.path.basename(file_path)
            base_dir = '/Документы/'
            remote_path = None
            
            if not self.webdav_client.check(base_dir):
                self.webdav_client.mkdir(base_dir)

            if doc_type == "incoming": 
                remote_dir = f'{base_dir}Входящие/'

                if not self.webdav_client.check(remote_dir):
                    self.webdav_client.mkdir(remote_dir)
                
                sender = doc_data.get("sender")
                if sender:
                    sender_dir = f'{remote_dir}{sender}/'
                    if not self.webdav_client.check(sender_dir):
                        self.webdav_client.mkdir(sender_dir)
                    remote_path = f'{sender_dir}{filename}'
                else:
                    remote_path = f'{remote_dir}{filename}'
                    
            elif doc_type == "outgoing":
                remote_dir = f'{base_dir}Исходящие/'
                
                if not self.webdav_client.check(remote_dir):
                    self.webdav_client.mkdir(remote_dir)
                
                executor = doc_data.get("executor")
                if executor:
                    if not self.webdav_client.check(f'{base_dir}Исполнители/'):
                        self.webdav_client.mkdir(f'{base_dir}Исполнители/')
                    
                    executor_dir = f'{base_dir}Исполнители/{executor}/'
                    if not self.webdav_client.check(executor_dir):
                        self.webdav_client.mkdir(executor_dir)
                    
                    remote_path = f'{executor_dir}{filename}'
                else:
                    remote_path = f'{remote_dir}{filename}'
            
            if not remote_path:
                raise Exception("Не удалось определить путь для загрузки на Яндекс.Диск")
            
            if self.webdav_client.check(remote_path):
                raise Exception(f"Файл {filename} уже существует на Яндекс.Диске по пути {remote_path}")
            
            self.webdav_client.upload(remote_path=remote_path, local_path=file_path)

            doc_data['remote_path'] = remote_path
            
            # Для отладки. выводим информацию о загрузке
            print(f"Файл успешно загружен на Яндекс.Диск: {remote_path}")
            
            return True
        
        except Exception as e:
            print(f"Ошибка загрузки на Яндекс.Диск: {e}")
            if 'remote_path' in locals() and remote_path and self.webdav_client.check(remote_path):
                try:
                    self.webdav_client.clean(remote_path)
                except Exception as clean_error:
                    print(f"Ошибка при очистке частично загруженного файла: {clean_error}")
            
            # Пробрасываем исключение дальше
            raise Exception(f"Не удалось загрузить файл на Яндекс.Диск: {str(e)}")
    
    def process_document_upload(self, doc_type, type_dialog):
        """Полная обработка загрузки документа"""
        type_dialog.close()
        
        # 1. Выбор файла
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите документ",
            "",
            "Документы (*.pdf *.doc *.docx *.txt);;Изображения (*.png *.jpg *.jpeg);;Все файлы (*)"
        )
        
        if not file_path:
            return
        
        # 2. Запрос дополнительных данных
        upload_dialog = DocumentUploadDialog(doc_type, self)
        if upload_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        doc_details = upload_dialog.get_data()
        if not doc_details["doc_number"]:
            QMessageBox.warning(self, "Ошибка", "Номер письма обязателен")
            return
        
        filename = os.path.basename(file_path)
        data = self.load_data()
        
        # Проверка на дубликат
        for doc in data['documents']:
            if doc['filename'].lower() == filename.lower() and doc['type'] == doc_type:
                QMessageBox.warning(self, "Ошибка", "Документ с таким именем и типом уже существует")
                return
        
        # 3. Подготовка данных документа
        doc_data = {
            'filename': filename,
            'type': doc_type,
            'doc_number': doc_details['doc_number'],
            'doc_date': doc_details['doc_date'],
            'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'size': int(os.path.getsize(file_path))
        }

        try:
            # 4. Обработка в зависимости от типа документа
            if doc_type == "incoming":
                sender = self.select_or_create_entity("sender", "Выберите отправителя", "Создать нового отправителя")
                if not sender:
                    return
                
                doc_data['sender'] = sender
                doc_data['sender_id'] = next(s["id"] for s in data["senders"] if s["name"] == sender)
                
                # Создание папки отправителя локально
                sender_dir = os.path.join(self.incoming_dir, sender)
                os.makedirs(sender_dir, exist_ok=True)
                
                # Копирование файла
                local_path = os.path.join(sender_dir, filename)
                shutil.copy2(file_path, local_path)
                
            elif doc_type == "outgoing":
                executor = self.select_or_create_entity("executor", "Выберите исполнителя", "Создать нового исполнителя")
                if not executor:
                    return
                
                doc_data['executor'] = executor
                doc_data['executor_id'] = next(e["id"] for e in data["executors"] if e["name"] == executor)
                
                # Создание папки исполнителя локально
                executor_dir = os.path.join(self.executors_dir, executor)
                os.makedirs(executor_dir, exist_ok=True)
                
                # Копирование файла
                local_path = os.path.join(executor_dir, filename)
                shutil.copy2(file_path, local_path)
            
            # 5. Сохраняем локальный путь
            doc_data['path'] = local_path
            
            # 6. Загрузка на Яндекс.Диск
            if not self.upload_to_yadisk(local_path, doc_type, doc_data):
                raise Exception("Не удалось загрузить на Яндекс.Диск")
            
            # 7. Сохранение в базу данных
            data['documents'].append(doc_data)
            self.save_data(data)
            
            # 8. Обновление интерфейса
            self.load_documents()
            
            QMessageBox.information(
                self,
                "Успешно",
                f"Документ успешно загружен:\n"
                f"Номер: {doc_details['doc_number']}\n"
                f"Дата: {doc_details['doc_date']}\n"
                f"Размер: {doc_data['size']/1024:.1f} KB"
            )
            
        except Exception as e:
            # Удаляем временные файлы в случае ошибки
            if 'local_path' in locals() and os.path.exists(local_path):
                os.remove(local_path)
                
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить документ:\n{str(e)}"
            )
        
    def select_or_create_entity(self, entity_type, select_title, create_title):
        """Выбор или создание отправителя/исполнителя"""
        data = self.load_data()
        entities = data[f"{entity_type}s"]
        
        dialog = QDialog(self)
        dialog.setWindowTitle(select_title)
        dialog.setFixedSize(300, 200)
        
        layout = QVBoxLayout()
        dialog.setLayout(layout)
        
        entity_list = QListWidget()
        for entity in entities:
            entity_list.addItem(entity["name"])
        
        # Кнопочки
        btn_layout = QHBoxLayout()
        select_btn = QPushButton("Выбрать")
        create_btn = QPushButton(create_title)
        cancel_btn = QPushButton("Отмена")
        
        select_btn.clicked.connect(dialog.accept)
        create_btn.clicked.connect(lambda: self.create_new_entity(entity_type, dialog))
        cancel_btn.clicked.connect(dialog.reject)
        
        btn_layout.addWidget(select_btn)
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addWidget(entity_list)
        layout.addLayout(btn_layout)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if entity_list.currentItem():
                return entity_list.currentItem().text()
        
        return None
    
    def create_new_entity(self, entity_type, parent_dialog):
        parent_dialog.close()
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Создать нового {entity_type}")
        dialog.setFixedSize(300, 150)
        
        layout = QFormLayout()
        dialog.setLayout(layout)
        
        name_edit = QLineEdit()
        description_edit = QLineEdit()
        
        layout.addRow("Имя:", name_edit)
        layout.addRow("Описание:", description_edit)
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        
        layout.addRow(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip()
            if not name:
                QMessageBox.warning(self, "Ошибка", "Имя не может быть пустым")
                return None
            
            data = self.load_data()
            entities = data[f"{entity_type}s"]
            
            # Проверяем
            if any(e["name"].lower() == name.lower() for e in entities):
                QMessageBox.warning(self, "Ошибка", f"{entity_type} с таким именем уже существует")
                return None
            
            new_entity = {
                "id": len(entities) + 1,
                "name": name,
                "description": description_edit.text(),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            entities.append(new_entity)
            self.save_data(data)
            
            if entity_type == "executor":
                executor_dir = os.path.join(self.executors_dir, name)
                os.makedirs(executor_dir, exist_ok=True)
                
                # Создаем папку на Яндекс.Диске
                remote_executor_dir = f'/Документы/Исполнители/{name}'
                if not self.webdav_client.check(remote_executor_dir):
                    self.webdav_client.mkdir(remote_executor_dir)
            
            elif entity_type == "sender":
                sender_dir = os.path.join(self.incoming_dir, name)
                os.makedirs(sender_dir, exist_ok=True)
                
                # Создаем папку на Яндекс.Диске -_-
                remote_sender_dir = f'/Документы/Входящие/{name}'
                if not self.webdav_client.check(remote_sender_dir):
                    self.webdav_client.mkdir(remote_sender_dir)
            
            return name
        
        return None
    
    def delete_document(self, remote=False):
        """Удаление локально и полностью"""
        if not (selected_item := self.documents_list.currentItem()):
            QMessageBox.warning(self, "Ошибка", "Выберите файл для удаления")
            return
        
        doc = selected_item.data(Qt.ItemDataRole.UserRole)
        filename = doc["filename"]
        
        action = "локально и с Яндекс.Диска" if remote else "локально"
        reply = QMessageBox.question(
            self, 
            'Подтверждение', 
            f'Вы уверены что хотите удалить файл {filename} {action}?', 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            if os.path.exists(doc.get("path", "")):
                os.remove(doc["path"])
            
            if remote and "remote_path" in doc:
                try:
                    if self.webdav_client.check(doc["remote_path"]):
                        self.webdav_client.clean(doc["remote_path"])
                except Exception as e:
                    QMessageBox.warning(self, "Ошибка", f"Не удалось удалить с Яндекс.Диска: {str(e)}")
            
            data = self.load_data()
            data["documents"] = [
                d for d in data["documents"] 
                if not (d["filename"] == filename and 
                    d.get("type") == doc.get("type") and 
                    d.get("doc_number") == doc.get("doc_number"))
            ]
            self.save_data(data)
            
            self.load_documents()
            self.clear_document_info()
            QMessageBox.information(self, "Успешно", f"Файл успешно удален {action}")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить файл: {str(e)}")

    def delete_remote_document(self):
        """Удаление документа полностью (локально и с Яндекс.Диска)"""
        self.delete_document(remote=True)
    
    def open_document_threaded(self):
        """Открытие документа в отдельном потоке"""
        selected_item = self.documents_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, "Ошибка", "Выберите файл для открытия")
            return
        
        doc = selected_item.data(Qt.ItemDataRole.UserRole)
        file_path = doc["path"]
        self.open_thread = QThread()
        self.open_thread.run = lambda: self.open_file(file_path)
        self.open_thread.start()
    
    def open_file(self, file_path):
        """Открытие файла (вызывается в отдельном потоке)"""
        try:
            if sys.platform == 'win32':
                os.startfile(file_path)
            elif sys.platform == 'darwin':
                os.system(f'open "{file_path}"')
            else:
                os.system(f'xdg-open "{file_path}"')
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл: {str(e)}")

    def open_on_yadisk(self):
        """Открытие документа на Яндекс.Диске в браузере"""
        selected_item = self.documents_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, "Ошибка", "Выберите файл для открытия")
            return
        
        doc = selected_item.data(Qt.ItemDataRole.UserRole)
        
        if "remote_path" not in doc:
            QMessageBox.warning(self, "Ошибка", "Этот документ не находится на Яндекс.Диске")
            return
        
        try:
            # Формируем URL для открытия на Яндекс.Диске
            remote_path = doc["remote_path"]
            file_id = self.webdav_client.get_file_id(remote_path)
            url = f"https://disk.yandex.ru/client/disk{remote_path}"
            
            webbrowser.open(url)
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось открыть документ на Яндекс.Диске: {str(e)}")
    
    
    def calculate_text_height(self, text, width):
        fm = QFontMetrics(self.font())
        text_rect = fm.boundingRect(0, 0, width, 0, 
                                Qt.TextFlag.TextWordWrap, text)
        return text_rect.height()

    def show_document_info(self, item):
        """информация о документе и его превью"""
        if not item:
            return
            
        doc = item.data(Qt.ItemDataRole.UserRole)
        if not doc:
            return
        
        try:
            filename = doc.get("filename", "-")
            path = doc.get("path", "-")
            doc_type = doc.get("type", "")
            doc_number = doc.get("doc_number", "-")
            doc_date = doc.get("doc_date", "-")
            sender = doc.get("sender", "-")
            executor = doc.get("executor", "-")
            date_added = doc.get("date", "-")
            
            try:
                size_bytes = int(doc.get("size", 0))
                if size_bytes >= 1024 * 1024:  # Больше 1 MB
                    size_text = f"{size_bytes/(1024*1024):.2f} MB"
                elif size_bytes >= 1024:  # Больше 1 KB
                    size_text = f"{size_bytes/1024:.2f} KB"
                else:
                    size_text = f"{size_bytes} B"
            except (ValueError, TypeError):
                size_text = "0 B"

            self.name_label.setText(filename)
            self.path_label.setText(path)
            self.type_label.setText("Входящий" if doc_type == "incoming" else "Исходящий")
            self.doc_number_label.setText(doc_number)
            self.doc_date_label.setText(doc_date)
            self.sender_label.setText(sender)
            self.executor_label.setText(executor)
            self.size_label.setText(size_text)
            self.date_label.setText(date_added)
            
            max_width = max(self.info_widget.width() - 30, 100)
            font = self.font()
            
            def text_height(text):
                return QFontMetrics(font).boundingRect(
                    0, 0, max_width, 0,
                    Qt.TextFlag.TextWordWrap, text
                ).height() + 5
            
            self.name_label.setMinimumHeight(40)
            self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.path_label.setMinimumHeight(max(20, text_height(path)))
            self.name_label.setToolTip(filename)
            self.path_label.setToolTip(path)
            self.update_preview(path)
            self.info_widget.layout().activate()
            
        except Exception as e:
            print(f"Ошибка отображения информации: {str(e)}")
            for label in [self.name_label, self.path_label, self.type_label,
                        self.doc_number_label, self.doc_date_label,
                        self.sender_label, self.executor_label,
                        self.size_label, self.date_label]:
                label.setText("-")
                label.setMinimumHeight(20)
            self.clear_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'documents_list') and self.documents_list.currentItem():
            current_item = self.documents_list.currentItem()
            if current_item:
                doc = current_item.data(Qt.ItemDataRole.UserRole)
                if doc and "path" in doc:
                    # Обновляем размер существующего превью
                    pixmap = self.preview_widget.pixmap()
                    if pixmap and not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            self.preview_widget.width() - 20, 
                            self.preview_widget.height() - 20,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation
                        )
                        self.preview_widget.setPixmap(scaled_pixmap)

    def clear_document_info(self):
        self.name_label.setText("-")
        self.type_label.setText("-")
        self.sender_label.setText("-")
        self.executor_label.setText("-")
        self.size_label.setText("-")
        self.path_label.setText("-")
        self.date_label.setText("-")
        self.doc_number_label.setText("-")
        self.doc_date_label.setText("-")
        self.clear_preview()
                
    def show_full_path(self):
        if hasattr(self, 'documents_list') and self.documents_list.currentItem():
            doc = self.documents_list.currentItem().data(Qt.ItemDataRole.UserRole)
            QMessageBox.information(self, "Полный путь", doc["path"])
    def migrate_data(self):
        data = self.load_data()
        changed = False
        
        for doc in data["documents"]:
            if isinstance(doc.get("size"), str):
                try:
                    doc["size"] = int(doc["size"])
                    changed = True
                except (ValueError, TypeError):
                    doc["size"] = 0
                    changed = True
        if changed:
            self.save_data(data)
class SyncThread(QThread):
    update_progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, webdav_client, local_dir):
        super().__init__()
        self.webdav_client = webdav_client
        self.local_dir = local_dir
        self._is_running = True

    def run(self):
        try:
            self.sync_folder('Входящие')
            self.sync_folder('Исходящие')
            self.sync_executors()
            self.finished.emit(True, "Синхронизация завершена")
        except Exception as e:
            self.finished.emit(False, f"Ошибка: {str(e)}")

    def sync_folder(self, folder_type):
        remote_dir = f'/Документы/{folder_type}/'
        local_dir = os.path.join(self.local_dir, folder_type)
        
        if not self.webdav_client.check(remote_dir):
            return

        files = self.webdav_client.list(remote_dir)
        for file in files:
            if not self._is_running:
                break
                
            remote_path = f"{remote_dir}{file}"
            local_path = os.path.join(local_dir, file)
            
            if not os.path.exists(local_path):
                self.update_progress.emit(0, f"Загрузка {file}...")
                self.webdav_client.download(remote_path, local_path)
                self.update_progress.emit(1, f"Загружен {file}")

    def sync_executors(self):
        remote_base = '/Документы/Исполнители/'
        if not self.webdav_client.check(remote_base):
            return

        executors = self.webdav_client.list(remote_base)
        for executor in executors:
            if not self._is_running:
                break
                
            remote_dir = f"{remote_base}{executor}/"
            local_dir = os.path.join(self.local_dir, 'Executors', executor)
            os.makedirs(local_dir, exist_ok=True)
            
            self.sync_folder_contents(remote_dir, local_dir)

    def stop(self):
        self._is_running = False

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DocumentManager()
    window.show()
    sys.exit(app.exec())