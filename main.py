import sys
from pathlib import Path

from PySide6.QtCore import QDir, QRect, QRegularExpression, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeView,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()

        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)

        self.update_line_number_width(0)
        self.highlight_current_line()

        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont("Menlo", 13))

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                padding: 4px;
                selection-background-color: #264F78;
            }
        """)

    def line_number_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 18 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_width(self, _):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0,
                rect.y(),
                self.line_number_area.width(),
                rect.height()
            )

        if rect.contains(self.viewport().rect()):
            self.update_line_number_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        rect = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(
                rect.left(),
                rect.top(),
                self.line_number_width(),
                rect.height()
            )
        )

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#282828")
            selection.format.setBackground(line_color)
            selection.format.setProperty(
                QTextCharFormat.Property.FullWidthSelection, True
            )
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

    def paint_line_numbers(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#181818"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()

        top = int(
            self.blockBoundingGeometry(block)
            .translated(self.contentOffset())
            .top()
        )

        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if bottom >= event.rect().top():
                number = str(block_number + 1)

                painter.setPen(
                    QColor("#FFFFFF")
                    if block == self.textCursor().block()
                    else QColor("#858585")
                )

                painter.drawText(
                    0,
                    top,
                    self.line_number_area.width() - 8,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight,
                    number
                )

            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

        self.rules = []

        self.add_rule(
            r"\b(and|as|assert|async|await|break|case|class|continue|def|del|elif|else|except|False|finally|for|from|global|if|import|in|is|lambda|match|None|nonlocal|not|or|pass|raise|return|True|try|while|with|yield)\b",
            "#569CD6"
        )

        self.add_rule(
            r"\b(print|len|range|str|int|float|list|dict|set|tuple|sum|min|max|open|super|self|type|isinstance|enumerate|zip|map|filter)\b",
            "#4EC9B0"
        )

        self.add_rule(
            r"\b\d+(\.\d+)?\b",
            "#B5CEA8"
        )

        self.add_rule(
            r"@[A-Za-z_]\w*",
            "#DCDCAA"
        )

        self.add_rule(
            r"#[^\n]*",
            "#6A9955"
        )

        self.add_rule(
            r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
            "#CE9178"
        )

    def add_rule(self, pattern, color):
        text_format = QTextCharFormat()
        text_format.setForeground(QColor(color))

        self.rules.append(
            (QRegularExpression(pattern), text_format)
        )

    def highlightBlock(self, text):
        for expression, text_format in self.rules:
            iterator = expression.globalMatch(text)

            while iterator.hasNext():
                match = iterator.next()

                self.setFormat(
                    match.capturedStart(),
                    match.capturedLength(),
                    text_format
                )


class MyIDE(QMainWindow):
    def __init__(self):
        super().__init__()

        self.project_folder: Path | None = None
        self.current_file: Path | None = None

        self.setWindowTitle("myIDE")
        self.resize(1250, 800)

        self.create_ui()
        self.setup_shortcuts()

        # Auto-prompt folder selection after launch
        QTimer.singleShot(100, self.choose_project)

    def create_ui(self):
        container = QWidget()
        self.setCentralWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 6, 6, 6)

        self.open_folder_button = QPushButton("Open Folder")
        self.open_folder_button.clicked.connect(self.choose_project)
        toolbar.addWidget(self.open_folder_button)
        toolbar.addStretch()

        splitter = QSplitter()

        # --- EXPLORER SIDEBAR ---
        explorer = QWidget()
        explorer_layout = QVBoxLayout(explorer)
        explorer_layout.setContentsMargins(0, 0, 0, 0)
        explorer_layout.setSpacing(0)

        # Header Widget
        explorer_header = QWidget()
        explorer_header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        explorer_header.setStyleSheet("background-color: #252526; border-bottom: 1px solid #1E1E1E;")
        
        explorer_header_layout = QHBoxLayout(explorer_header)
        explorer_header_layout.setContentsMargins(10, 6, 10, 6)
        explorer_header_layout.setSpacing(6)

        title = QLabel("EXPLORER")
        title.setStyleSheet("color: #BBBBBB; font-size: 11px; font-weight: bold;")

        btn_style = """
            QPushButton {
                background-color: #333333;
                color: #FFFFFF;
                border: 1px solid #444444;
                border-radius: 3px;
                font-size: 12px;
                padding: 2px 6px;
            }
            QPushButton:hover {
                background-color: #007ACC;
                border-color: #007ACC;
            }
        """

        self.sidebar_new_file_btn = QPushButton("+ File")
        self.sidebar_new_file_btn.setToolTip("New File")
        self.sidebar_new_file_btn.setStyleSheet(btn_style)
        self.sidebar_new_file_btn.clicked.connect(self.create_file)

        self.sidebar_new_folder_btn = QPushButton("+ Folder")
        self.sidebar_new_folder_btn.setToolTip("New Folder")
        self.sidebar_new_folder_btn.setStyleSheet(btn_style)
        self.sidebar_new_folder_btn.clicked.connect(self.create_folder)

        explorer_header_layout.addWidget(title)
        explorer_header_layout.addStretch()
        explorer_header_layout.addWidget(self.sidebar_new_file_btn)
        explorer_header_layout.addWidget(self.sidebar_new_folder_btn)

        # File Tree
        self.file_model = QFileSystemModel()
        self.file_model.setFilter(
            QDir.Filter.AllDirs |
            QDir.Filter.NoDotAndDotDot |
            QDir.Filter.Files
        )
        # Fix for empty directory loading issue: wait until directory is loaded before setting index
        self.file_model.directoryLoaded.connect(self._on_directory_loaded)

        self.files = QTreeView()
        self.files.setModel(self.file_model)
        self.files.setHeaderHidden(True)
        self.files.setAnimated(True)
        self.files.setIndentation(18)
        self.files.setSortingEnabled(True)
        self.files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.files.hideColumn(1)
        self.files.hideColumn(2)
        self.files.hideColumn(3)

        self.files.doubleClicked.connect(self.open_item)
        self.files.customContextMenuRequested.connect(self.show_context_menu)

        explorer_layout.addWidget(explorer_header)
        explorer_layout.addWidget(self.files)

        # --- EDITOR PANEL ---
        self.editor = CodeEditor()
        self.editor.setPlaceholderText("Start coding here...")

        self.highlighter = PythonHighlighter(self.editor.document())
        self.editor.textChanged.connect(self.mark_unsaved)

        splitter.addWidget(explorer)
        splitter.addWidget(self.editor)
        splitter.setSizes([280, 970])

        layout.addLayout(toolbar)
        layout.addWidget(splitter)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #1E1E1E;
            }

            QPushButton {
                background-color: #2D2D30;
                color: #CCCCCC;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 6px 12px;
            }

            QPushButton:hover {
                background-color: #3E3E42;
            }

            QTreeView {
                background-color: #181818;
                color: #CCCCCC;
                border: none;
                outline: none;
            }

            QTreeView::item {
                padding: 4px;
            }

            QTreeView::item:selected {
                background-color: #37373D;
                color: white;
            }

            QTreeView::item:hover {
                background-color: #2A2D2E;
            }
        """)

    def setup_shortcuts(self):
        self.editor.addAction(self.create_save_action())

        new_file_action = QAction(self)
        new_file_action.setShortcut(QKeySequence("Ctrl+N"))
        new_file_action.triggered.connect(self.create_file)
        self.addAction(new_file_action)

    def create_save_action(self):
        action = QAction(self)
        action.setShortcut(QKeySequence("Ctrl+S"))
        action.triggered.connect(self.save_file)
        return action

    def choose_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder")

        if not folder:
            return

        self.project_folder = Path(folder)
        
        # Set system model root path (starts async directory scan)
        self.file_model.setRootPath(folder)

        # Set root index directly (and rely on directoryLoaded signal to update if needed)
        idx = self.file_model.index(folder)
        if idx.isValid():
            self.files.setRootIndex(idx)

        self.setWindowTitle(f"{self.project_folder.name} — myIDE")
        self.current_file = None
        self.editor.clear()

    def _on_directory_loaded(self, path):
        if self.project_folder and Path(path) == self.project_folder:
            idx = self.file_model.index(str(self.project_folder))
            if idx.isValid():
                self.files.setRootIndex(idx)

    def open_item(self, index):
        path = Path(self.file_model.filePath(index))

        if path.is_dir():
            return

        if not self.maybe_save():
            return

        try:
            code = path.read_text(encoding="utf-8")
        except Exception as error:
            QMessageBox.critical(self, "Open Error", str(error))
            return

        self.editor.blockSignals(True)
        self.editor.setPlainText(code)
        self.editor.blockSignals(False)

        self.current_file = path
        self.editor.document().setModified(False)
        self.setWindowTitle(f"{path.name} — myIDE")

    def get_selected_directory(self) -> Path | None:
        index = self.files.currentIndex()
        if index.isValid():
            path = Path(self.file_model.filePath(index))
            return path if path.is_dir() else path.parent
        return self.project_folder

    def create_file(self):
        if not self.project_folder:
            self.choose_project()
            if not self.project_folder:
                return

        directory = self.get_selected_directory()
        if directory is None:
            return

        name, ok = QInputDialog.getText(
            self,
            "New File",
            "File name (e.g. script.py):"
        )

        if not ok or not name.strip():
            return

        path = directory / name.strip()
        if path.exists():
            QMessageBox.warning(self, "File Exists", f"{path.name} already exists.")
            return

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        except OSError as error:
            QMessageBox.critical(self, "Create Error", str(error))
            return

        self.open_path(path)

    def create_folder(self):
        if not self.project_folder:
            self.choose_project()
            if not self.project_folder:
                return

        directory = self.get_selected_directory()
        if directory is None:
            return

        name, ok = QInputDialog.getText(
            self,
            "New Folder",
            "Folder name:"
        )

        if not ok or not name.strip():
            return

        path = directory / name.strip()
        if path.exists():
            QMessageBox.warning(self, "Folder Exists", f"{path.name} already exists.")
            return

        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            QMessageBox.critical(self, "Create Error", str(error))

    def open_path(self, path):
        if not path.is_file():
            return

        try:
            code = path.read_text(encoding="utf-8")
        except Exception as error:
            QMessageBox.critical(self, "Open Error", str(error))
            return

        self.editor.blockSignals(True)
        self.editor.setPlainText(code)
        self.editor.blockSignals(False)

        self.current_file = path
        self.editor.document().setModified(False)
        self.setWindowTitle(f"{path.name} — myIDE")

    def save_file(self):
        if not self.current_file:
            if not self.project_folder:
                return

            path, _ = QFileDialog.getSaveFileName(
                self,
                "Save File",
                str(self.project_folder),
                "All Files (*.*)"
            )

            if not path:
                return
            self.current_file = Path(path)

        try:
            self.current_file.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.critical(self, "Save Error", str(error))
            return

        self.editor.document().setModified(False)
        self.setWindowTitle(f"{self.current_file.name} — myIDE")

    def mark_unsaved(self):
        if not self.current_file:
            return

        if self.editor.document().isModified():
            self.setWindowTitle(f"* {self.current_file.name} — myIDE")

    def maybe_save(self):
        if not self.editor.document().isModified():
            return True

        result = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Save changes before continuing?",
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )

        if result == QMessageBox.StandardButton.Save:
            self.save_file()
            return not self.editor.document().isModified()

        if result == QMessageBox.StandardButton.Cancel:
            return False

        return True

    def rename_item(self, index):
        if not index.isValid():
            return

        old_path = Path(self.file_model.filePath(index))

        name, ok = QInputDialog.getText(
            self,
            "Rename",
            "New name:",
            text=old_path.name
        )

        if not ok or not name.strip():
            return

        new_path = old_path.parent / name.strip()

        if new_path.exists():
            QMessageBox.warning(self, "Already Exists", "Name already taken.")
            return

        try:
            old_path.rename(new_path)
        except OSError as error:
            QMessageBox.critical(self, "Rename Error", str(error))

        if self.current_file == old_path:
            self.current_file = new_path
            self.setWindowTitle(f"{new_path.name} — myIDE")

    def delete_item(self, index):
        if not index.isValid():
            return

        path = Path(self.file_model.filePath(index))

        result = QMessageBox.question(
            self,
            "Delete",
            f"Delete '{path.name}'?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as error:
            QMessageBox.critical(self, "Delete Error", str(error))
            return

        if self.current_file == path:
            self.current_file = None
            self.editor.clear()
            self.setWindowTitle("myIDE")

    def show_context_menu(self, position):
        index = self.files.indexAt(position)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #252526;
                color: #CCCCCC;
                border: 1px solid #3C3C3C;
            }
            QMenu::item:selected {
                background-color: #04395E;
                color: #FFFFFF;
            }
        """)

        new_file = menu.addAction("New File...")
        new_folder = menu.addAction("New Folder...")

        if index.isValid():
            menu.addSeparator()
            rename = menu.addAction("Rename...")
            delete = menu.addAction("Delete")
        else:
            rename = None
            delete = None

        action = menu.exec(self.files.viewport().mapToGlobal(position))

        if action == new_file:
            self.create_file()
        elif action == new_folder:
            self.create_folder()
        elif action == rename and index.isValid():
            self.rename_item(index)
        elif action == delete and index.isValid():
            self.delete_item(index)

    def closeEvent(self, event):
        if self.maybe_save():
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    window = MyIDE()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()