# TODO : 
import os
import sys
import json
import fitz
import shutil
from PIL import Image
from datetime import datetime
from dotenv import load_dotenv
import webbrowser
import tempfile
import io
import requests
import urllib.parse
# весь наш интерфейс, сложно но можно
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QIcon, QFontMetrics
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QListWidget, 
                            QPushButton, QFileDialog, QMessageBox, QLabel, QHBoxLayout,
                            QScrollArea, QListWidgetItem, QSizePolicy, QComboBox, 
                            QLineEdit, QDialog, QFormLayout, QDialogButtonBox, QTabWidget,
                            QTableWidget, QTableWidgetItem, QHeaderView)
load_dotenv()

class TelegramStorage:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.test_connection()
    
    def test_connection(self):
        """Проверка подключения к Telegram API"""
        try:
            if not self.token:
                print("⚠️ TELEGRAM_BOT_TOKEN не установлен")
                return False
                
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('ok'):
                    print(f"✅ Бот подключен: {data['result']['first_name']}")
                    return True
                else:
                    print(f"❌ Ошибка бота: {data.get('description')}")
                    return False
            else:
                print(f"❌ Ошибка HTTP: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Ошибка подключения к Telegram: {e}")
            return False
    
    def upload_file(self, file_path, metadata=None):
        """Загрузка файла в Telegram канал с inline-кнопкой"""
        try:
            if not self.token or not self.chat_id:
                return {'success': False, 'error': 'Токен или chat_id не установлен'}
                
            url = f"https://api.telegram.org/bot{self.token}/sendDocument"
            
            # Подготавливаем метаданные для описания
            caption = self._format_caption(metadata) if metadata else "Документ из архива"

            
            with open(file_path, 'rb') as file:
                files = {'document': file}
                data = {
                    'chat_id': self.chat_id,
                    'caption': caption,
                    'parse_mode': 'HTML',
                }
                
                response = requests.post(url, files=files, data=data, timeout=60)
                result = response.json()
                
                if result.get('ok'):
                    message_id = result['result']['message_id']
                    file_id = result['result']['document']['file_id']
                    return {
                        'message_id': message_id,
                        'file_id': file_id,
                        'success': True
                    }
                else:
                    error_msg = result.get('description', 'Неизвестная ошибка')
                    print(f"❌ Ошибка Telegram: {error_msg}")
                    return {'success': False, 'error': error_msg}
                    
        except Exception as e:
            print(f"❌ Ошибка загрузки в Telegram: {e}")
            return {'success': False, 'error': str(e)}
    
    def _format_caption(self, metadata):
        """Форматирование описания для документа"""
        caption = f"📄 <b>{metadata.get('filename', 'Документ')}</b>\n"
        
        doc_type = metadata.get('type', '')
        if doc_type == 'incoming':
            caption += "📥 <b>Входящий документ</b>\n"
        elif doc_type == 'outgoing':
            caption += "📤 <b>Исходящий документ</b>\n"
        else:
            caption += "📋 Тип: Не указан\n"
        
        if metadata.get('doc_number'):
            caption += f"🔢 Номер: {metadata['doc_number']}\n"
        if metadata.get('doc_date'):
            caption += f"📅 Дата: {metadata['doc_date']}\n"
        if metadata.get('sender'):
            caption += f"👤 Отправитель: {metadata['sender']}\n"
        if metadata.get('executor'):
            caption += f"🛠️ Исполнитель: {metadata['executor']}\n"
            
        return caption
    
    def get_channel_files(self, limit=100):
        """Получение списка файлов из канала"""
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            response = requests.get(url)
            updates = response.json()
            
            files = []
            if updates.get('ok') and updates['result']:
                for update in updates['result']:
                    if 'message' in update and 'document' in update['message']:
                        doc = update['message']['document']
                        files.append({
                            'file_id': doc['file_id'],
                            'file_name': doc.get('file_name', 'unknown'),
                            'caption': update['message'].get('caption', ''),
                            'date': update['message']['date'],
                            'message_id': update['message']['message_id']
                        })
            return files
        except Exception as e:
            print(f"❌ Ошибка получения файлов из канала: {e}")
            return []

class PreviewThread(QThread):
    preview_generated = pyqtSignal(str, object)
    
    def __init__(self, file_path, preview_manager):
        super().__init__()
        self.file_path = file_path
        self.preview_manager = preview_manager
    
    def run(self):
        """Генерация превью в отдельном потоке"""
        try:
            if not os.path.exists(self.file_path):
                self.preview_generated.emit(self.file_path, "missing")
                return
            
            # Получаем расширение файла
            ext = os.path.splitext(self.file_path)[1].lower()
            
            # Проверяем поддерживаемые форматы
            supported_formats = ['.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif']
            if ext not in supported_formats:
                self.preview_generated.emit(self.file_path, "unsupported")
                return
            
            # Генерируем превью
            preview_path = self.preview_manager.create_preview(self.file_path)
            if preview_path and os.path.exists(preview_path):
                pixmap = QPixmap(preview_path)
                self.preview_generated.emit(self.file_path, pixmap)
            else:
                self.preview_generated.emit(self.file_path, "error")
                
        except Exception as e:
            print(f"Ошибка генерации превью в потоке: {e}")
            self.preview_generated.emit(self.file_path, "error")


class PreviewManager:
    def __init__(self):
        # Создаем временную директорию для кэша превью
        self.cache_dir = os.path.join(tempfile.gettempdir(), 'document_archive_previews')
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def create_preview(self, file_path, output_path=None):
        """Создает превью для файла поддерживаемых форматов"""
        try:
            # Если файл не существует, возвращаем None
            if not os.path.exists(file_path):
                return None
            
            # Определяем расширение файла
            ext = os.path.splitext(file_path)[1].lower()
            
            # Создаем временный файл для превью, если не указан выходной путь
            if output_path is None:
                output_path = os.path.join(self.cache_dir, f"preview_{os.path.basename(file_path)}.png")
            
            # Генерируем превью в зависимости от формата
            if ext == '.pdf':
                # Для PDF используем PyMuPDF
                doc = fitz.open(file_path)
                page = doc.load_page(0)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                pix.save(output_path)
                doc.close()
                return output_path
                
            elif ext in ['.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif']:
                # Для изображений используем PIL
                img = Image.open(file_path)
                img.thumbnail((800, 600))  # Изменяем размер
                img.save(output_path, 'PNG')
                return output_path
                
            else:
                # Для других форматов превью не доступно
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
        self.setFixedSize(600, 500)
        
        self.parent = parent
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        tabs = QTabWidget()
        layout.addWidget(tabs)
        
        # Вкладка Telegram
        self.telegram_tab = QWidget()
        telegram_layout = QVBoxLayout(self.telegram_tab)
        
        telegram_info = QLabel(
            "Для работы с Telegram Archive:\n"
            "1. Создайте бота через @BotFather\n"
            "2. Создайте канал и добавьте бота как администратора\n"
            "3. Отправьте любое сообщение в канал\n"
            "4. Получите chat_id через @username_to_id_bot\n"
            "5. Введите данные ниже:"
        )
        telegram_info.setWordWrap(True)
        telegram_info.setStyleSheet("padding: 10px; background-color: #2b5278; border-radius: 5px; color: white;")
        telegram_layout.addWidget(telegram_info)
        
        telegram_form = QFormLayout()
        
        self.telegram_token_edit = QLineEdit()
        self.telegram_token_edit.setPlaceholderText("1234567890:ABCdefGHIjklMNOpqrsTUVwxyz")
        self.telegram_token_edit.setText(os.getenv('TELEGRAM_BOT_TOKEN', ''))
        
        self.telegram_chat_id_edit = QLineEdit()
        self.telegram_chat_id_edit.setPlaceholderText("@channel_name или -1001234567890")
        self.telegram_chat_id_edit.setText(os.getenv('TELEGRAM_CHAT_ID', ''))
        
        telegram_form.addRow("Bot Token:", self.telegram_token_edit)
        telegram_form.addRow("Chat ID:", self.telegram_chat_id_edit)
        
        test_telegram_btn = QPushButton("Проверить подключение")
        test_telegram_btn.clicked.connect(self.test_telegram_connection)
        
        telegram_layout.addLayout(telegram_form)
        telegram_layout.addWidget(test_telegram_btn)
        telegram_layout.addStretch()
        
        # Вкладки отправителей и исполнителей (остаются без изменений)
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
        
        tabs.addTab(self.telegram_tab, "Telegram Archive")
        tabs.addTab(self.senders_tab, "Отправители")
        tabs.addTab(self.executors_tab, "Исполнители")
        
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def test_telegram_connection(self):
        """Проверка подключения к Telegram"""
        token = self.telegram_token_edit.text().strip()
        chat_id = self.telegram_chat_id_edit.text().strip()
        
        if not token or not chat_id:
            QMessageBox.warning(self, "Ошибка", "Введите token и chat_id")
            return
        
        # Сохраняем временно в переменные окружения для теста
        os.environ['TELEGRAM_BOT_TOKEN'] = token
        os.environ['TELEGRAM_CHAT_ID'] = chat_id
        
        storage = TelegramStorage()
        if storage.test_connection():
            QMessageBox.information(self, "Успех", "✅ Подключение к Telegram установлено!")
        else:
            QMessageBox.warning(self, "Ошибка", "❌ Не удалось подключиться к Telegram")
    
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

    def accept(self):
        """Сохранение настроек Telegram при закрытии"""
        # Сохраняем настройки Telegram в .env файл
        token = self.telegram_token_edit.text().strip()
        chat_id = self.telegram_chat_id_edit.text().strip()
        
        if token and chat_id:
            # Обновляем .env файл
            env_lines = []
            if os.path.exists('.env'):
                with open('.env', 'r', encoding='utf-8') as f:
                    env_lines = f.readlines()
            
            # Обновляем или добавляем переменные
            updated = False
            for i, line in enumerate(env_lines):
                if line.startswith('TELEGRAM_BOT_TOKEN='):
                    env_lines[i] = f'TELEGRAM_BOT_TOKEN={token}\n'
                    updated = True
                elif line.startswith('TELEGRAM_CHAT_ID='):
                    env_lines[i] = f'TELEGRAM_CHAT_ID={chat_id}\n'
                    updated = True
            
            if not updated:
                env_lines.append(f'TELEGRAM_BOT_TOKEN={token}\n')
                env_lines.append(f'TELEGRAM_CHAT_ID={chat_id}\n')
            
            with open('.env', 'w', encoding='utf-8') as f:
                f.writelines(env_lines)
            
            # Обновляем переменные окружения
            os.environ['TELEGRAM_BOT_TOKEN'] = token
            os.environ['TELEGRAM_CHAT_ID'] = chat_id
        
        super().accept()


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

class SyncTelegramThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, telegram_storage, data_file, base_dir):
        super().__init__()
        self.telegram_storage = telegram_storage
        self.data_file = data_file
        self.base_dir = base_dir
    
    def run(self):
        """Синхронизация документов с Telegram архивом"""
        try:
            self.progress.emit("🔄 Начало синхронизации с Telegram...")
            
            # Загружаем текущие данные
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            local_docs = {doc['filename']: doc for doc in data['documents']}
            
            self.progress.emit("📡 Получение списка файлов из Telegram...")
            telegram_files = self.telegram_storage.get_channel_files()
            
            new_docs_count = 0
            for tg_file in telegram_files:
                filename = tg_file['file_name']
                
                # Проверяем, есть ли файл в локальной базе
                if filename not in local_docs:
                    self.progress.emit(f"📥 Загрузка нового файла: {filename}")
                    
                    # Создаем временный путь для загрузки
                    temp_path = os.path.join(self.base_dir, "temp", filename)
                    os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                    
                    # Скачиваем файл
                    if self.telegram_storage.download_file(tg_file['file_id'], temp_path):
                        # Определяем тип документа из caption
                        caption = tg_file.get('caption', '')
                        doc_type = 'incoming' if 'Входящий' in caption else 'outgoing'
                        
                        # Создаем запись документа
                        new_doc = {
                            'filename': filename,
                            'type': doc_type,
                            'path': temp_path,
                            'telegram_file_id': tg_file['file_id'],
                            'telegram_message_id': tg_file.get('message_id'),
                            'date': datetime.fromtimestamp(tg_file['date']).strftime("%Y-%m-%d %H:%M:%S"),
                            'size': os.path.getsize(temp_path)
                        }
                        
                        # Извлекаем метаданные из caption
                        if 'Номер:' in caption:
                            import re
                            number_match = re.search(r'Номер:\s*([^\n]+)', caption)
                            if number_match:
                                new_doc['doc_number'] = number_match.group(1).strip()
                        
                        if 'Отправитель:' in caption:
                            sender_match = re.search(r'Отправитель:\s*([^\n]+)', caption)
                            if sender_match:
                                new_doc['sender'] = sender_match.group(1).strip()
                        
                        if 'Исполнитель:' in caption:
                            executor_match = re.search(r'Исполнитель:\s*([^\n]+)', caption)
                            if executor_match:
                                new_doc['executor'] = executor_match.group(1).strip()
                        
                        data['documents'].append(new_doc)
                        new_docs_count += 1
            
            if new_docs_count > 0:
                # Сохраняем обновленные данные
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                
                self.finished.emit(True, f"✅ Синхронизация завершена! Добавлено {new_docs_count} новых документов")
            else:
                self.finished.emit(True, "ℹ️ Новых документов для синхронизации не найдено")
                
        except Exception as e:
            self.finished.emit(False, f"❌ Ошибка синхронизации: {str(e)}")

class DocumentManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Архив Telegram")
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
        
        # Инициализируем Telegram Storage
        self.telegram_storage = TelegramStorage()
        
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
            # Останавливаем предыдущий поток, если он запущен
            if self.preview_thread and self.preview_thread.isRunning():
                self.preview_thread.quit()
                self.preview_thread.wait()
            
            # Создаем и запускаем новый поток
            self.preview_thread = PreviewThread(file_path, self.preview_manager)
            self.preview_thread.preview_generated.connect(self.on_preview_generated)
            self.preview_thread.start()
            
            # Временно показываем сообщение о загрузке с нормальным размером шрифта
            self.preview_widget.clear()
            self.preview_widget.setText("Генерация превью...")
            self.preview_widget.setStyleSheet("""
                QLabel {
                    font-size: 14px;
                    background-color: rgba(255, 255, 255, 0.1);
                    border: 1px solid #4a6fa5;
                    border-radius: 5px;
                }
            """)
                
        except Exception as e:
            print(f"Ошибка запуска потока превью: {e}")
            self.clear_preview()

    def on_preview_generated(self, file_path, result):
        """Обработчик завершения генерации превью"""
        # Проверяем, что превью соответствует текущему документу
        current_item = self.documents_list.currentItem()
        if current_item and current_item.data(Qt.ItemDataRole.UserRole)["path"] == file_path:
            if isinstance(result, QPixmap) and not result.isNull():
                # Масштабируем превью под размер виджета
                scaled_pixmap = result.scaled(
                    self.preview_widget.width() - 20, 
                    self.preview_widget.height() - 20,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.preview_widget.setPixmap(scaled_pixmap)
                # Убираем текстовый стиль, так как теперь у нас изображение
                self.preview_widget.setStyleSheet("""
                    QLabel {
                        background-color: rgba(255, 255, 255, 0.1);
                        border: 1px solid #4a6fa5;
                        border-radius: 5px;
                    }
                """)
            else:
                # Устанавливаем смайлик для неподдерживаемых форматов
                self.preview_widget.clear()
                self.preview_widget.setText("📄")
                self.preview_widget.setStyleSheet("""
                    QLabel {
                        font-size: 100px;
                        background-color: rgba(255, 255, 255, 0.1);
                        border: 1px solid #4a6fa5;
                        border-radius: 5px;
                    }
                """)

    def clear_preview(self):
        """Очищает область превью и устанавливает смайлик"""
        self.preview_widget.clear()
        self.preview_widget.setText("📄")
        self.preview_widget.setStyleSheet("""
            QLabel {
                font-size: 100px;
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid #4a6fa5;
                border-radius: 5px;
            }
        """)    

    def sync_with_telegram(self):
        """Синхронизация с Telegram архивом"""
        if not self.telegram_storage.test_connection():
            QMessageBox.warning(self, "Ошибка", "❌ Не настроено подключение к Telegram")
            return
        
        # Создаем диалог прогресса
        progress_dialog = QDialog(self)
        progress_dialog.setWindowTitle("Синхронизация с Telegram")
        progress_dialog.setFixedSize(400, 150)
        
        layout = QVBoxLayout()
        progress_dialog.setLayout(layout)
        
        progress_label = QLabel("Начало синхронизации...")
        progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(progress_label)
        
        progress_dialog.show()
        
        # Запускаем поток синхронизации
        self.sync_thread = SyncTelegramThread(
            self.telegram_storage, 
            self.data_file, 
            self.base_dir
        )
        
        self.sync_thread.progress.connect(progress_label.setText)
        self.sync_thread.finished.connect(
            lambda success, msg: self.on_sync_finished(success, msg, progress_dialog)
        )
        self.sync_thread.start()

    def on_sync_finished(self, success, message, progress_dialog):
        """Обработчик завершения синхронизации"""
        progress_dialog.close()
        
        if success:
            QMessageBox.information(self, "Синхронизация", message)
            self.load_documents()
        else:
            QMessageBox.warning(self, "Ошибка синхронизации", message)

    def upload_to_telegram(self, file_path, doc_type, doc_data):
        """Загрузка файла в Telegram канал с кнопкой скачивания"""
        try:
            if not self.telegram_storage.test_connection():
                return False
            
            metadata = {
                'filename': doc_data['filename'],
                'type': doc_type,
                'doc_number': doc_data.get('doc_number', ''),
                'doc_date': doc_data.get('doc_date', ''),
                'sender': doc_data.get('sender', ''),
                'executor': doc_data.get('executor', '')
            }
            
            result = self.telegram_storage.upload_file(file_path, metadata)
            
            if result['success']:
                doc_data['telegram_file_id'] = result['file_id']
                doc_data['telegram_message_id'] = result['message_id']
                print(f"✅ Документ загружен в Telegram с кнопкой скачивания (message_id: {result['message_id']})")
                return True
            else:
                print(f"⚠️ Не удалось загрузить в Telegram: {result.get('error')}")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при загрузке в Telegram: {e}")
            return False

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

        ######################
        #png-шка в левой панели, многовероятно удалю в конце, но пока что пусть будет
        logo_label = QLabel()
        logo_pixmap = QPixmap("name.png")

        if not logo_pixmap.isNull():
            logo_pixmap = logo_pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter)
            logo_label.setStyleSheet("background: transparent;")
            left_layout.addWidget(logo_label)

        ###########################
        
        # Заголовок
        title_label = QLabel("Архив Telegram")
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
        
        # Статус Telegram
        self.telegram_status_label = QLabel()
        self.update_telegram_status()
        self.telegram_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.telegram_status_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                padding: 5px;
                border-radius: 3px;
                margin: 5px;
            }
        """)
        left_layout.addWidget(self.telegram_status_label)
        
        buttons = [
            ("Загрузить документ", self.upload_document),
            ("Удалить документ", self.delete_document),
            ("Синхронизация с Telegram", self.sync_with_telegram)
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
                "#5a5a5a" if text == "Настройки" else "#4a6fa5",
                "#6a6a6a" if text == "Настройки" else "#5a7fb5",
                "#4a4a4a" if text == "Настройки" else "#3a5f95"
            ))
            btn.setFixedHeight(40)
            btn.clicked.connect(handler)
            left_layout.addWidget(btn)

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
        
        fields = [
            ("Название", "name_label"),
            ("Тип", "type_label"),
            ("Номер письма", "doc_number_label"),
            ("Дата письма", "doc_date_label"),
            ("Отправитель", "sender_label"),
            ("Исполнитель", "executor_label"),
            ("Размер", "size_label"),
            ("Путь", "path_label"),
            ("Дата добавления", "date_label"),
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
    
    def update_telegram_status(self):
        """Обновление статуса подключения к Telegram"""
        if self.telegram_storage.test_connection():
            self.telegram_status_label.setText("✅ Telegram подключен")
            self.telegram_status_label.setStyleSheet("""
                QLabel {
                    background-color: #2d7d46;
                    color: white;
                    font-size: 12px;
                    padding: 5px;
                    border-radius: 3px;
                }
            """)
        else:
            self.telegram_status_label.setText("❌ Telegram отключен")
            self.telegram_status_label.setStyleSheet("""
                QLabel {
                    background-color: #c42b1c;
                    color: white;
                    font-size: 12px;
                    padding: 5px;
                    border-radius: 3px;
                }
            """)
    
    def open_settings(self):
        """Открытие диалога настроек"""
        dialog = SettingsDialog(self)
        dialog.exec()
        self.update_telegram_status()
        self.load_documents()
    
    def apply_filters(self):
        """фильтр поиска с учетом всех полей документа"""
        search_text = self.search_edit.text().lower()
        filter_type = self.filter_combo.currentText()
        
        for i in range(self.documents_list.count()):
            item = self.documents_list.item(i)
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
            
            item.setHidden(not visible)

    def load_documents(self):
        """Загрузка списка документов"""
        data = self.load_data()
        self.documents_list.clear()
        
        for doc in data["documents"]:
            item = QListWidgetItem(doc["filename"])
            item.setData(Qt.ItemDataRole.UserRole, doc)
            
            # Устанавливаем иконку в зависимости от типа и наличия в Telegram
            if doc.get('telegram_file_id'):
                item.setIcon(QIcon.fromTheme("cloud-upload"))  # Иконка облака если есть в Telegram
                item.setForeground(Qt.GlobalColor.green)
            else:
                item.setForeground(Qt.GlobalColor.white)
            
            if doc['filename'].lower().endswith('.pdf'):
                item.setIcon(QIcon.fromTheme("application-pdf"))
            elif doc['filename'].lower().endswith(('.png', '.jpg', '.jpeg')):
                item.setIcon(QIcon.fromTheme("image-x-generic"))
            else:
                item.setIcon(QIcon.fromTheme("text-x-generic"))
            
            self.documents_list.addItem(item)

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
            
            # 6. Загрузка в Telegram с кнопкой скачивания
            telegram_success = self.upload_to_telegram(local_path, doc_type, doc_data)
            if telegram_success:
                print("✅ Документ успешно загружен в Telegram")
            else:
                print("⚠️ Документ не был загружен в Telegram")
            
            # 7. Сохранение в базу данных
            data['documents'].append(doc_data)
            self.save_data(data)
            
            # 8. Обновление интерфейса
            self.load_documents()
            
            message = f"Документ успешно загружен:\nНомер: {doc_details['doc_number']}\nДата: {doc_details['doc_date']}\nРазмер: {doc_data['size']/1024:.1f} KB"
            if telegram_success:
                message += "\n✅ Загружено в Telegram"
            else:
                message += "\n⚠️ Не загружено в Telegram"
            
            QMessageBox.information(self, "Успешно", message)
            
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
            
            elif entity_type == "sender":
                sender_dir = os.path.join(self.incoming_dir, name)
                os.makedirs(sender_dir, exist_ok=True)
            
            return name
        
        return None
    
    def delete_document(self):
        """Удаление документа"""
        if not (selected_item := self.documents_list.currentItem()):
            QMessageBox.warning(self, "Ошибка", "Выберите файл для удаления")
            return
        
        doc = selected_item.data(Qt.ItemDataRole.UserRole)
        filename = doc["filename"]
        
        reply = QMessageBox.question(
            self, 
            'Подтверждение', 
            f'Вы уверены что хотите удалить файл {filename}?\n\n⚠️ Внимание: файл будет удален только локально, в Telegram он останется.', 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            if os.path.exists(doc.get("path", "")):
                os.remove(doc["path"])
            
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
            QMessageBox.information(self, "Успешно", f"Файл успешно удален")
            
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось удалить файл: {str(e)}")
    
    def open_document_threaded(self):
        """Открытие документа в отдельном потоке"""
        selected_item = self.documents_list.currentItem()
        if not selected_item:
            QMessageBox.warning(self, "Ошибка", "Выберите файл для открытия")
            return
        
        doc = selected_item.data(Qt.ItemDataRole.UserRole)
        file_path = doc["path"]
        
        # Проверяем существование файла
        if not os.path.exists(file_path):
            # Пытаемся скачать из Telegram если есть file_id
            if doc.get('telegram_file_id'):
                reply = QMessageBox.question(
                    self,
                    "Файл не найден",
                    f"Локальный файл {doc['filename']} не найден.\nХотите скачать его из Telegram?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    # Скачиваем из Telegram
                    temp_dir = os.path.join(self.base_dir, "temp")
                    os.makedirs(temp_dir, exist_ok=True)
                    temp_path = os.path.join(temp_dir, doc['filename'])
                    
                    if self.telegram_storage.download_file(doc['telegram_file_id'], temp_path):
                        # Обновляем путь в базе
                        data = self.load_data()
                        for d in data['documents']:
                            if (d['filename'] == doc['filename'] and 
                                d.get('type') == doc.get('type') and 
                                d.get('doc_number') == doc.get('doc_number')):
                                d['path'] = temp_path
                                break
                        
                        self.save_data(data)
                        file_path = temp_path
                    else:
                        QMessageBox.warning(self, "Ошибка", "Не удалось скачать файл из Telegram")
                        return
            else:
                QMessageBox.warning(self, "Ошибка", f"Файл {doc['filename']} не найден")
                return
        
        self.open_thread = OpenFileThread(file_path)
        self.open_thread.start()

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
            telegram_id = doc.get("telegram_file_id", "-")
            
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
            self.telegram_id_label.setText(telegram_id if telegram_id != "-" else "Не загружен")
            
            self.update_preview(path)
            
        except Exception as e:
            print(f"Ошибка отображения информации: {str(e)}")
            for label in [self.name_label, self.path_label, self.type_label,
                        self.doc_number_label, self.doc_date_label,
                        self.sender_label, self.executor_label,
                        self.size_label, self.date_label, self.telegram_id_label]:
                label.setText("-")
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
        self.telegram_id_label.setText("-")
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DocumentManager()
    window.show()
    sys.exit(app.exec())