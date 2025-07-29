import os
import shutil
import sqlite3
import webbrowser
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
                               QPushButton, QLabel, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
                               QStatusBar, QListWidget, QListWidgetItem, QLineEdit, QFileDialog, QCheckBox)
from PySide6.QtGui import (QPixmap, QImage, QWheelEvent, QPainter, QColor, QPen, QKeyEvent, 
                          QFont, QBrush, QPainterPath, QFontMetrics, QCursor)
from PySide6.QtCore import Qt, QRectF, QPointF, QEvent, QSizeF, QSettings

class ImageViewer(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = None
        self.current_scale = 1.0
        self.max_scale = 5.0 
        self.min_scale = 0.1  
        
    def set_image(self, pixmap):
        if self.pixmap_item:
            self.scene.removeItem(self.pixmap_item)
            self.pixmap_item = None

        if not pixmap.isNull():
            self.pixmap_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self.pixmap_item)
            self.pixmap_item.setZValue(0)
            
            self.reset_zoom()
        
    def reset_zoom(self):
        if self.pixmap_item:
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self.current_scale = self.transform().m11()
        
    def wheelEvent(self, event: QWheelEvent):
        zoom_factor = 1.15
        if event.angleDelta().y() > 0:
            new_scale = self.current_scale * zoom_factor
            if new_scale <= self.max_scale:
                self.scale(zoom_factor, zoom_factor)
                self.current_scale = new_scale
        else:
            new_scale = self.current_scale / zoom_factor
            if new_scale >= self.min_scale:
                self.scale(1 / zoom_factor, 1 / zoom_factor)
                self.current_scale = new_scale
                
        if self.parent() and hasattr(self.parent(), 'update_zoom_status'):
            self.parent().update_zoom_status()
                
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.position()
            self.dragging = True
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            delta = event.position() - self.drag_start_pos
            self.drag_start_pos = event.position()
            
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
        super().mouseMoveEvent(event)
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

class ImageTaggingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Label Management System")
        self.setGeometry(100, 100, 1200, 800)
        
        self.db_conn = sqlite3.connect('image_tags.db')
        self.create_database()
        
        self.image_folder = ""
        self.image_files = []
        self.current_index = -1
        self.current_image_name = "" 
        self.batch_size = 100
        self.loaded_count = 0
        self.operation_status = ""  
        
        self.settings = QSettings("Ka5fxt", "ImageTaggingApp")
        self.default_tag = self.settings.value("default_tag", "默认标签", type=str)
        
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        
        self.btn_open = QPushButton("打开图片文件夹")
        self.btn_open.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_open.clicked.connect(self.open_image_folder)
        left_layout.addWidget(self.btn_open)
        
        self.btn_load_more = QPushButton("继续加载 (100张)")
        self.btn_load_more.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_load_more.clicked.connect(self.load_more_images)
        self.btn_load_more.setEnabled(False)
        left_layout.addWidget(self.btn_load_more)
        
        left_layout.addWidget(QLabel("重命名操作"))
        self.rename_prefix = QLineEdit()
        self.rename_prefix.setStyleSheet("""
            QLineEdit {
                font-size: 14px;
                padding: 8px;
                border-radius: 5px;
                border: 1px solid #ccc;
            }
        """)
        self.rename_prefix.setPlaceholderText("输入文件名前缀")
        left_layout.addWidget(self.rename_prefix)
        
        self.btn_rename = QPushButton("批量重命名")
        self.btn_rename.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_rename.clicked.connect(self.batch_rename)
        self.btn_rename.setEnabled(False)
        left_layout.addWidget(self.btn_rename)
        
        left_layout.addWidget(QLabel("整理操作"))
        self.btn_organize = QPushButton("整理已标记图片")
        self.btn_organize.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_organize.clicked.connect(self.organize_images)
        self.btn_organize.setEnabled(False)
        left_layout.addWidget(self.btn_organize)
        
        self.btn_delete = QPushButton("删除未标记图片")
        self.btn_delete.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_delete.clicked.connect(self.delete_unlabeled)
        self.btn_delete.setEnabled(False)
        left_layout.addWidget(self.btn_delete)
        
        left_layout.addSpacing(20)
        left_layout.addWidget(QLabel("键盘快捷键:"))
        left_layout.addWidget(QLabel("A - 上一张图片"))
        left_layout.addWidget(QLabel("D - 下一张图片"))
        left_layout.addWidget(QLabel("+ - 放大图片"))
        left_layout.addWidget(QLabel("- - 缩小图片"))
        left_layout.addWidget(QLabel("R - 重置缩放"))
        
        left_layout.addStretch()
        
        self.image_viewer = ImageViewer(self)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        
        self.tag_list = QListWidget()
        self.tag_list.setStyleSheet("""
            QListWidget {
                font-size: 16px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
                background-color: #dbfaff;
                border-radius: 5px;
                padding: 5px;
                color: #ff7a30;
            }
            QListWidget::item {
                padding: 6px;
                color: #FF0000;
                background-color: #FFBC4C;
                border-bottom: 1px solid #fff;
            }
            QListWidget::item:checked {
                color: #FF0000; /* 选中项字体颜色 */
            }
        """)
        self.tag_list.itemClicked.connect(self.remove_tag)
        right_layout.addWidget(QLabel("当前标签:"))
        right_layout.addWidget(self.tag_list)
        
        default_tag_layout = QHBoxLayout()
        default_tag_layout.addWidget(QLabel("默认标签:"))
        self.default_tag_input = QLineEdit(self.default_tag)
        self.default_tag_input.setStyleSheet("""
            QLineEdit {
                font-size: 14px;
                padding: 8px;
                border-radius: 5px;
                border: 1px solid #ccc;
            }
        """)
        self.default_tag_input.textChanged.connect(self.update_default_tag)
        default_tag_layout.addWidget(self.default_tag_input)
        
        self.use_default_check = QCheckBox("使用默认标签")
        self.use_default_check.setChecked(False)
        self.use_default_check.stateChanged.connect(self.toggle_default_tag)
        default_tag_layout.addWidget(self.use_default_check)
        
        right_layout.addLayout(default_tag_layout)
        
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setStyleSheet("""
            QLineEdit {
                font-size: 14px;
                padding: 8px;
                border-radius: 5px;
                border: 1px solid #ccc;
            }
        """)
        self.new_tag_input.setPlaceholderText("输入新标签")
        self.new_tag_input.returnPressed.connect(self.add_tag)
        right_layout.addWidget(QLabel("输入新标签:"))
        right_layout.addWidget(self.new_tag_input)
        
        self.btn_add_tag = QPushButton("添加标签")
        self.btn_add_tag.setStyleSheet("""
            QPushButton {
                font-size: 14px;
                padding: 8px;
                background-color: #4CAF50;
                color: white;
                border-radius: 5px;
                border: none;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.btn_add_tag.clicked.connect(self.add_tag)
        right_layout.addWidget(self.btn_add_tag)
        
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("上一张 (A)")
        self.btn_prev.setStyleSheet("font-size: 14px; padding: 8px;")
        self.btn_prev.clicked.connect(self.show_prev_image)
        nav_layout.addWidget(self.btn_prev)
        
        self.btn_next = QPushButton("下一张 (D)")
        self.btn_next.setStyleSheet("font-size: 14px; padding: 8px;")
        self.btn_next.clicked.connect(self.show_next_image)
        nav_layout.addWidget(self.btn_next)
        right_layout.addLayout(nav_layout)
        
        zoom_layout = QHBoxLayout()
        self.btn_zoom_in = QPushButton("放大 (+)")
        self.btn_zoom_in.setStyleSheet("font-size: 14px; padding: 8px;")
        self.btn_zoom_in.clicked.connect(self.zoom_in)
        zoom_layout.addWidget(self.btn_zoom_in)
        
        self.btn_zoom_out = QPushButton("缩小 (-)")
        self.btn_zoom_out.setStyleSheet("font-size: 14px; padding: 8px;")
        self.btn_zoom_out.clicked.connect(self.zoom_out)
        zoom_layout.addWidget(self.btn_zoom_out)
        
        self.btn_reset_zoom = QPushButton("重置缩放 (R)")
        self.btn_reset_zoom.setStyleSheet("font-size: 14px; padding: 8px;")
        self.btn_reset_zoom.clicked.connect(self.reset_zoom)
        zoom_layout.addWidget(self.btn_reset_zoom)
        
        right_layout.addLayout(zoom_layout)
        
        right_layout.addStretch()
        
        splitter.addWidget(left_panel)
        splitter.addWidget(self.image_viewer)
        splitter.addWidget(right_panel)
        splitter.setSizes([200, 600, 200])
        
        main_layout.addWidget(splitter)
        self.setCentralWidget(main_widget)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        
        self.zoom_label = QLabel("缩放: 100%")
        self.status_bar.addWidget(self.zoom_label)
        
        self.operation_label = QLabel()
        self.status_bar.addPermanentWidget(self.operation_label)
        
        self.github_link = QLabel("<a href='https://github.com/ka5fxt' style='color: #1E90FF; text-decoration: none;'>ka5fxt : github.com/ka5fxt</a>")
        self.github_link.setOpenExternalLinks(False)  
        self.github_link.linkActivated.connect(self.open_github)
        self.github_link.setCursor(QCursor(Qt.PointingHandCursor))
        self.status_bar.addPermanentWidget(self.github_link)
        
        self.toggle_default_tag()
        
        self.installEventFilter(self)
        
    def update_default_tag(self):
        self.default_tag = self.default_tag_input.text()
        self.settings.setValue("default_tag", self.default_tag)
        
        if self.use_default_check.isChecked():
            self.new_tag_input.setText(self.default_tag)
    
    def toggle_default_tag(self):
        if self.use_default_check.isChecked():
            self.new_tag_input.setText(self.default_tag)
        else:
            self.new_tag_input.clear()
    
    def open_github(self, link):
        webbrowser.open(link)
        
    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_A:
                self.show_prev_image()
                return True
            elif key == Qt.Key_D:
                self.show_next_image()
                return True
            elif key == Qt.Key_Plus or key == Qt.Key_Equal:
                self.zoom_in()
                return True
            elif key == Qt.Key_Minus:
                self.zoom_out()
                return True
            elif key == Qt.Key_R:
                self.reset_zoom()
                return True
        return super().eventFilter(obj, event)
        
    def update_zoom_status(self):
        self.zoom_label.setText(f"缩放: {self.image_viewer.current_scale*100:.0f}%")
        
    def create_database(self):
        cursor = self.db_conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE,
                tags TEXT
            )
        ''')
        self.db_conn.commit()
        
    def open_image_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择图片文件夹")
        if folder:
            self.image_folder = folder
            self.image_files = [
                os.path.join(folder, f) for f in os.listdir(folder) 
                if os.path.isfile(os.path.join(folder, f)) and 
                f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))
            ]
            self.loaded_count = 0
            self.current_index = -1
            self.btn_load_more.setEnabled(len(self.image_files) > 0)
            self.set_operation_status(f"找到图片: {len(self.image_files)} 张")
            self.load_more_images()
            
    def load_more_images(self):
        if not self.image_files:
            return
            
        end_index = min(self.loaded_count + self.batch_size, len(self.image_files))
        batch_files = self.image_files[self.loaded_count:end_index]
        
        cursor = self.db_conn.cursor()
        for file_path in batch_files:
            try:
                cursor.execute(
                    "INSERT OR IGNORE INTO images (path, tags) VALUES (?, ?)",
                    (file_path, "")
                )
            except sqlite3.IntegrityError:
                pass  
        
        self.db_conn.commit()
        self.loaded_count = end_index
        
        if self.current_index == -1 and batch_files:
            self.current_index = self.loaded_count - len(batch_files)
            self.show_current_image()
            
        self.update_status()
        self.btn_load_more.setEnabled(self.loaded_count < len(self.image_files))
        self.btn_rename.setEnabled(True)
        self.btn_organize.setEnabled(True)
        self.btn_delete.setEnabled(True)
        
    def show_current_image(self):
        if 0 <= self.current_index < len(self.image_files):
            image_path = self.image_files[self.current_index]
            pixmap = QPixmap(image_path)
            
            if not pixmap.isNull():
                self.image_viewer.set_image(pixmap)
                
                self.current_image_name = os.path.basename(image_path)
                
                cursor = self.db_conn.cursor()
                cursor.execute("SELECT tags FROM images WHERE path = ?", (image_path,))
                result = cursor.fetchone()
                tags = result[0].split(',') if result and result[0] else []
                
                self.tag_list.clear()
                for tag in tags:
                    if tag:  
                        item = QListWidgetItem(tag)
                        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                        item.setCheckState(Qt.Unchecked)
                        self.tag_list.addItem(item)
                
                self.toggle_default_tag()
                self.update_status()
    
    def update_status(self):
        if self.image_files:
            self.status_label.setText(
                f"图片: {self.current_index + 1}/{len(self.image_files)} | "
                f"文件名: {self.current_image_name} | "
                f"已加载: {self.loaded_count}/{len(self.image_files)}"
            )
            self.update_zoom_status()
        else:
            self.status_label.setText("无图片")
    
    def set_operation_status(self, message):
        self.operation_status = message
        self.operation_label.setText(message)
    
    def show_next_image(self):
        if self.image_files and self.current_index < len(self.image_files) - 1:
            self.current_index += 1
            self.show_current_image()
    
    def show_prev_image(self):
        if self.image_files and self.current_index > 0:
            self.current_index -= 1
            self.show_current_image()
    
    def add_tag(self):
        tag = self.new_tag_input.text().strip()
        if not tag:
            if self.default_tag and self.use_default_check.isChecked():
                tag = self.default_tag
            else:
                return  
            
        if self.current_index >= 0:
            item = QListWidgetItem(tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.tag_list.addItem(item)
            
            image_path = self.image_files[self.current_index]
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT tags FROM images WHERE path = ?", (image_path,))
            result = cursor.fetchone()
            current_tags = result[0].split(',') if result and result[0] else []
            
            if tag not in current_tags:
                current_tags.append(tag)
                new_tags = ','.join(current_tags)
                cursor.execute(
                    "UPDATE images SET tags = ? WHERE path = ?",
                    (new_tags, image_path)
                )
                self.db_conn.commit()
            
            if self.use_default_check.isChecked():
                self.new_tag_input.setText(self.default_tag)
            else:
                self.new_tag_input.clear()
    
    def remove_tag(self, item):
        if item.checkState() == Qt.Checked:
            tag = item.text()
            row = self.tag_list.row(item)
            self.tag_list.takeItem(row)

            image_path = self.image_files[self.current_index]
            cursor = self.db_conn.cursor()
            cursor.execute("SELECT tags FROM images WHERE path = ?", (image_path,))
            result = cursor.fetchone()
            if result and result[0]:
                current_tags = result[0].split(',')
                if tag in current_tags:
                    current_tags.remove(tag)
                    new_tags = ','.join(current_tags)
                    cursor.execute(
                        "UPDATE images SET tags = ? WHERE path = ?",
                        (new_tags, image_path)
                    )
                    self.db_conn.commit()
    
    def batch_rename(self):
        prefix = self.rename_prefix.text().strip()
        if not prefix:
            return
            
        cursor = self.db_conn.cursor()
        renamed_count = 0
        
        for i, old_path in enumerate(self.image_files):
            ext = os.path.splitext(old_path)[1]
            new_name = f"{prefix}_{i+1:04d}{ext}"
            new_path = os.path.join(self.image_folder, new_name)
            
            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                renamed_count += 1
                
                cursor.execute(
                    "UPDATE images SET path = ? WHERE path = ?",
                    (new_path, old_path)
                )
                
                if old_path == self.image_files[self.current_index]:
                    self.current_image_name = new_name
                    self.update_status()
        
        self.db_conn.commit()
        self.image_files = [
            os.path.join(self.image_folder, f) for f in os.listdir(self.image_folder) 
            if os.path.isfile(os.path.join(self.image_folder, f)) and 
            f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))
        ]
        self.set_operation_status(f"批量重命名完成，共重命名 {renamed_count} 张图片")
    
    def organize_images(self):
        if not self.image_folder:
            return
            
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT path, tags FROM images WHERE tags != ''")
        tagged_images = cursor.fetchall()
        
        organized_count = 0
        for path, tags in tagged_images:
            if not os.path.exists(path):
                continue
                
            for tag in tags.split(','):
                if not tag:
                    continue
                    
                tag_folder = os.path.join(self.image_folder, tag)
                os.makedirs(tag_folder, exist_ok=True)
                
                dest_path = os.path.join(tag_folder, os.path.basename(path))
                if not os.path.exists(dest_path):
                    shutil.copy2(path, dest_path)
                    organized_count += 1
        
        self.set_operation_status(f"已整理 {organized_count} 张标记图片到对应文件夹")
    
    def delete_unlabeled(self):
        if not self.image_folder:
            return
            
        cursor = self.db_conn.cursor()
        cursor.execute("SELECT path FROM images WHERE tags = ''")
        unlabeled_images = [row[0] for row in cursor.fetchall()]
        
        deleted_count = 0
        for path in unlabeled_images:
            if os.path.exists(path):
                os.remove(path)
                deleted_count += 1
                
            cursor.execute("DELETE FROM images WHERE path = ?", (path,))
            
            if self.image_files and path == self.image_files[self.current_index]:
                self.current_image_name = ""
        
        self.db_conn.commit()
        
        self.image_files = [
            f for f in self.image_files if os.path.exists(f)
        ]
        
        if self.image_files:
            if self.current_index >= len(self.image_files):
                self.current_index = len(self.image_files) - 1
            self.show_current_image()
        else:
            self.image_viewer.scene.clear()
            self.tag_list.clear()
            self.status_label.setText("无图片")
            self.current_image_name = ""
        
        self.set_operation_status(f"已删除 {deleted_count} 张未标记图片")
        
    def zoom_in(self):
        if self.image_viewer.pixmap_item:
            zoom_factor = 1.15
            new_scale = self.image_viewer.current_scale * zoom_factor
            if new_scale <= self.image_viewer.max_scale:
                self.image_viewer.scale(zoom_factor, zoom_factor)
                self.image_viewer.current_scale = new_scale
                self.update_zoom_status()
    
    def zoom_out(self):
        if self.image_viewer.pixmap_item:
            zoom_factor = 1.15
            new_scale = self.image_viewer.current_scale / zoom_factor
            if new_scale >= self.image_viewer.min_scale:
                self.image_viewer.scale(1 / zoom_factor, 1 / zoom_factor)
                self.image_viewer.current_scale = new_scale
                self.update_zoom_status()
    
    def reset_zoom(self):
        self.image_viewer.reset_zoom()
        self.update_zoom_status()

if __name__ == "__main__":
    app = QApplication([])
    window = ImageTaggingApp()
    window.show()
    app.exec()
