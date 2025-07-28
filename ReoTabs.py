"""
================================================================================
ReoTabs - Asistente de Multicuentas para Dofus
================================================================================

Autor: Rodrigo
Fecha de última modificación: 28 de Julio de 2025

---
## ¿Qué es este programa?
ReoTabs es una herramienta de asistencia diseñada para jugadores de Dofus que
utilizan múltiples cuentas simultáneamente. Su objetivo es
facilitar el cambio rápido y ordenado entre las distintas ventanas del juego
mediante atajos de teclado y ratón totalmente personalizables.

---
## Funcionalidades Principales
1.  **Carrusel de Ventanas**: Permite navegar entre las ventanas de Dofus hacia
    adelante y hacia atrás usando atajos de teclado/ratón.

2.  **Configuración Gráfica**:
    - Detecta automáticamente todas las ventanas de Dofus abiertas.
    - Permite reordenar los personajes arrastrando y soltando para definir el
      orden del carrusel.
    - Permite definir de forma interactiva los atajos para "Siguiente",
      "Anterior" y "Pausar".

3.  **HUD "Always on Top"**: Muestra una pequeña ventana superpuesta que indica
    visualmente el personaje anterior, el actual y el siguiente en el orden,
    facilitando el seguimiento durante el combate.

4.  **Sincronización Automática**: El HUD se actualiza automáticamente si el
    juego cambia de ventana por sí mismo (por ejemplo, al inicio de un turno),
    manteniendo siempre la coherencia visual.

5.  **Pausa Inteligente**: Se puede pausar y reanudar la funcionalidad de los
    atajos con una tecla, lo que permite usar esas mismas teclas para otras
    funciones sin que el programa interfiera. El HUD cambia de color para
    indicar el estado (Blanco = Activo, Rojo = Pausado).

6.  **Persistencia**: La configuración de los atajos y la última posición del
    HUD se guardan automáticamente, por lo que no es necesario reconfigurar
    el programa cada vez que se inicia.

---
## ¿Cómo Funciona?
El programa se basa en una arquitectura de clases con PyQt6 para la interfaz
gráfica y utiliza varias librerías para interactuar con el sistema operativo:

- **PyQt6**: Para toda la interfaz gráfica, desde la ventana de configuración
  hasta el HUD personalizable.
- **pygetwindow**: Para encontrar las ventanas abiertas del juego por su título.
- **keyboard** y **mouse**: Para registrar los atajos globales que funcionan
  incluso cuando el programa no está en primer plano.
- **pywin32**: Para realizar el cambio de foco entre ventanas de forma
  instantánea y sin animaciones molestas.
- **threading**: Para ejecutar procesos en segundo plano, como la captura de
  teclas y el monitoreo de la ventana activa, sin congelar la interfaz.
- **json**: Para guardar y cargar la configuración del usuario en un archivo local.
"""

import os
import sys
import time
import threading
import json
import queue
from collections import Counter

# --- Librerías de la Interfaz Gráfica ---
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QListWidget, QListWidgetItem, QAbstractItemView, QLabel, QSizePolicy,
                             QLineEdit, QFormLayout)
from PyQt6.QtGui import QFont, QMouseEvent, QIcon, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

# --- Librerías ---
import keyboard
import mouse
import pygetwindow as gw
import win32gui
import win32com.client

# ## Función para encontrar archivos empaquetados en el .exe ##
def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para dev y para PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# (La clase KeyCaptureButton no cambia)
class KeyCaptureButton(QPushButton):
    key_captured = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__("Definir", parent)
        self.is_capturing = False
        self.clicked.connect(self.start_capture)
    def start_capture(self):
        if self.is_capturing: return
        self.is_capturing = True
        self.setText("Escuchando...")
        threading.Thread(target=self.capture_input_thread, daemon=True).start()
    def capture_input_thread(self):
        event_queue = queue.Queue()
        active_modifiers = set()
        def keyboard_callback(event: keyboard.KeyboardEvent):
            if event.event_type == keyboard.KEY_DOWN:
                if event.name == 'esc':
                    event_queue.put("")
                    return False
                if event.name in keyboard.all_modifiers:
                    active_modifiers.add(event.name)
                else:
                    parts = sorted(list(active_modifiers))
                    parts.append(event.name)
                    name = "+".join(parts)
                    event_queue.put(name)
                    return False
            elif event.event_type == keyboard.KEY_UP:
                if event.name in active_modifiers:
                    active_modifiers.remove(event.name)
        def mouse_callback(event):
            if isinstance(event, mouse.ButtonEvent) and event.event_type == 'down':
                name = f"{event.button} mouse"
                event_queue.put(name)
                return False
        keyboard_hook = keyboard.hook(keyboard_callback, suppress=True)
        mouse_hook = mouse.hook(mouse_callback)
        captured_event = event_queue.get()
        keyboard.unhook(keyboard_hook)
        mouse.unhook(mouse_hook)
        self.key_captured.emit(captured_event)
        self.setText("Definir")
        self.is_capturing = False

class ConfigWindow(QWidget):
    launch_signal = pyqtSignal(list, dict)
    def __init__(self, initial_keybinds: dict):
        super().__init__()
        self.setWindowTitle('ReoTabs - Configuración')
        self.setGeometry(100, 100, 350, 500) # Ajusté el tamaño para que quepa todo bien
        # ## CAMBIO: Se usa resource_path para el icono de la ventana ##
        self.setWindowIcon(QIcon(resource_path('imagenes_dofus/ReoTabs.png')))
        main_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        main_layout.addWidget(self.list_widget)
        form_layout = QFormLayout()
        self.prev_key_input = QLineEdit(initial_keybinds.get("prev"))
        self.prev_key_input.setReadOnly(True)
        prev_key_button = KeyCaptureButton()
        prev_key_button.key_captured.connect(self.prev_key_input.setText)
        prev_layout = QHBoxLayout()
        prev_layout.addWidget(self.prev_key_input)
        prev_layout.addWidget(prev_key_button)
        form_layout.addRow("Ventana Anterior:", prev_layout)
        self.next_key_input = QLineEdit(initial_keybinds.get("next"))
        self.next_key_input.setReadOnly(True)
        next_key_button = KeyCaptureButton()
        next_key_button.key_captured.connect(self.next_key_input.setText)
        next_layout = QHBoxLayout()
        next_layout.addWidget(self.next_key_input)
        next_layout.addWidget(next_key_button)
        form_layout.addRow("Ventana Siguiente:", next_layout)
        self.pause_key_input = QLineEdit(initial_keybinds.get("pause"))
        self.pause_key_input.setReadOnly(True)
        pause_key_button = KeyCaptureButton()
        pause_key_button.key_captured.connect(self.pause_key_input.setText)
        pause_layout = QHBoxLayout()
        pause_layout.addWidget(self.pause_key_input)
        pause_layout.addWidget(pause_key_button)
        form_layout.addRow("Pausa/Reanudar:", pause_layout)
        main_layout.addLayout(form_layout)
        button_layout = QHBoxLayout()
        self.refresh_button = QPushButton("Actualizar Lista")
        self.refresh_button.clicked.connect(self.populate_character_list)
        button_layout.addWidget(self.refresh_button)
        self.launch_button = QPushButton("Lanzar")
        self.launch_button.clicked.connect(self.launch_app)
        button_layout.addWidget(self.launch_button)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
        self.populate_character_list()
    def launch_app(self):
        keybinds = {"prev": self.prev_key_input.text(), "next": self.next_key_input.text(), "pause": self.pause_key_input.text()}
        ordered_character_list = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            char_info = {"title": item_data["name"], "hwnd": item_data["hwnd"], "class": item_data["class"]}
            ordered_character_list.append(char_info)
        if ordered_character_list:
            self.launch_signal.emit(ordered_character_list, keybinds)
            self.close()
    def populate_character_list(self):
        self.list_widget.clear()
        try:
            dofus_windows = gw.getWindowsWithTitle('- Release')
            for win in dofus_windows:
                if not win.visible: continue
                parts = win.title.split(' - ')
                char_name, char_class = parts[0], parts[1]
                item = QListWidgetItem(char_name)
                # ## CAMBIO: Se usa resource_path para los iconos de la lista ##
                icon_path = resource_path(f"imagenes_dofus/{char_class}.png")
                item.setIcon(QIcon(icon_path))
                item_data = {"name": char_name, "class": char_class, "hwnd": win._hWnd}
                item.setData(Qt.ItemDataRole.UserRole, item_data)
                self.list_widget.addItem(item)
        except Exception as e:
            print(f"Error al buscar ventanas: {e}")

class HudWindow(QWidget):
    return_to_config_signal = pyqtSignal()
    moved_and_released_signal = pyqtSignal(QPoint)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.size_current, self.size_adjacent = 45, 30
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(10)
        self.prev_icon_label, self.current_icon_label, self.next_icon_label = QLabel(), QLabel(), QLabel()
        self.prev_icon_label.setFixedSize(self.size_adjacent, self.size_adjacent)
        self.current_icon_label.setFixedSize(self.size_current, self.size_current)
        self.next_icon_label.setFixedSize(self.size_adjacent, self.size_adjacent)
        self.prev_name_label, self.current_name_label, self.next_name_label = QLabel(self.prev_icon_label), QLabel(self.current_icon_label), QLabel(self.next_icon_label)
        name_font, name_style = QFont("Arial", 10, QFont.Weight.Bold), ("color: white; background-color: rgba(0, 0, 0, 0.6); border-radius: 3px; padding: 0px 2px;")
        for name_label in [self.prev_name_label, self.current_name_label, self.next_name_label]:
            name_label.setFont(name_font)
            name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            name_label.setStyleSheet(name_style)
        main_layout.addWidget(self.prev_icon_label)
        main_layout.addWidget(self.current_icon_label)
        main_layout.addWidget(self.next_icon_label)
        self.setLayout(main_layout)
        self.drag_pos = QPoint()
        self.show()
    def update_display(self, character_list, current_index, class_counts):
        count = len(character_list)
        char_positions = {"prev": (self.prev_icon_label, self.prev_name_label, self.size_adjacent, character_list[(current_index - 1) % count]), "current": (self.current_icon_label, self.current_name_label, self.size_current, character_list[current_index]), "next": (self.next_icon_label, self.next_name_label, self.size_adjacent, character_list[(current_index + 1) % count])}
        for pos_name, (icon_label, name_label, size, char_data) in char_positions.items():
            # ## CAMBIO: Se usa resource_path para los iconos del HUD ##
            pixmap = QPixmap(resource_path(f'imagenes_dofus/{char_data["class"]}.png'))
            icon_label.setPixmap(pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            name_label.adjustSize()
            x_pos, y_pos = (icon_label.width() - name_label.width()) // 2, icon_label.height() - name_label.height()
            name_label.move(x_pos, y_pos)
            if class_counts[char_data["class"]] > 1:
                name_label.setText(char_data["title"][0].upper())
                name_label.show()
            else:
                name_label.setText("")
                name_label.hide()
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton: self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept()
        elif event.button() == Qt.MouseButton.RightButton: self.return_to_config_signal.emit(); event.accept()
    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton: self.move(event.globalPosition().toPoint() - self.drag_pos); event.accept()
    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton: self.moved_and_released_signal.emit(self.pos()); event.accept()

class ReoTabsApp:
    def __init__(self):
        self.character_list, self.class_counts = [], {}
        self.current_index, self.is_paused, self.tracking_active = 0, False, False
        self.shell = win32com.client.Dispatch("WScript.Shell")
        # ## CAMBIO: Se usa resource_path para el archivo de configuración ##
        self.settings_file = resource_path('reotabs_settings.json')
        self.keybinds, hud_pos = self.load_settings()
        self.app = QApplication(sys.argv)
        self.config_window = ConfigWindow(self.keybinds)
        self.hud = HudWindow()
        if hud_pos: self.hud.move(QPoint(hud_pos['x'], hud_pos['y']))
        self.hud.hide()
        self.config_window.launch_signal.connect(self.start_hotkey_mode)
        self.hud.return_to_config_signal.connect(self.show_config_view)
        self.hud.moved_and_released_signal.connect(self.save_settings)
        self.config_window.show()
    def load_settings(self):
        try:
            with open(self.settings_file, 'r') as f:
                settings = json.load(f)
                keybinds, hud_pos = settings.get("keybinds", {}), settings.get("hud_pos")
                print("Configuración cargada.")
                return keybinds, hud_pos
        except (FileNotFoundError, json.JSONDecodeError):
            print("No se encontró archivo de configuración. Usando valores por defecto.")
            return {"prev": "alt+1", "next": "alt+2", "pause": "middle mouse"}, None
    def save_settings(self):
        try:
            current_keybinds = {"prev": self.config_window.prev_key_input.text(), "next": self.config_window.next_key_input.text(), "pause": self.config_window.pause_key_input.text()}
            pos = self.hud.pos(); hud_pos = {"x": pos.x(), "y": pos.y()}
            settings = {"keybinds": current_keybinds, "hud_pos": hud_pos}
            with open(self.settings_file, 'w') as f:
                json.dump(settings, f, indent=4)
                print(f"Configuración guardada: {settings}")
        except Exception as e: print(f"No se pudo guardar la configuración: {e}")
    def start_hotkey_mode(self, ordered_list, keybinds):
        self.keybinds = keybinds
        self.save_settings()
        self.character_list = ordered_list
        all_classes = [char['class'] for char in self.character_list]
        self.class_counts = Counter(all_classes)
        self.current_index, self.is_paused = 0, False
        self.hud.setWindowOpacity(1.0)
        self.hud.update_display(self.character_list, self.current_index, self.class_counts)
        self.hud.show()
        print(f"Registrando atajos: {self.keybinds}")
        prev_key, next_key, pause_key = self.keybinds.get('prev'), self.keybinds.get('next'), self.keybinds.get('pause')
        if prev_key: keyboard.add_hotkey(prev_key, self.switch_to_previous_window); print(f"- Anterior: {prev_key}")
        if next_key: keyboard.add_hotkey(next_key, self.switch_to_next_window); print(f"- Siguiente: {next_key}")
        if pause_key:
            print(f"- Pausa: {pause_key}")
            if "mouse" in pause_key:
                if "middle" in pause_key: mouse.on_middle_click(self.toggle_pause)
            else: keyboard.add_hotkey(pause_key, self.toggle_pause)
        self.tracking_active = True
        self.tracking_thread = threading.Thread(target=self.track_active_window, daemon=True)
        self.tracking_thread.start()
        print("Atajos y tracking de ventana activados.")
    def show_config_view(self):
        print("Volviendo a la ventana de configuración..."); self.save_settings()
        self.tracking_active = False
        keyboard.unhook_all_hotkeys(); mouse.unhook_all()
        self.hud.hide(); self.config_window.populate_character_list(); self.config_window.show()
    def toggle_pause(self):
        self.is_paused = not self.is_paused
        status = "Pausado" if self.is_paused else "Reanudado"; print(f"Script {status}.")
        self.hud.setWindowOpacity(0.5 if self.is_paused else 1.0)
    def track_active_window(self):
        while self.tracking_active:
            try:
                current_hwnd = win32gui.GetForegroundWindow()
                for i, char_info in enumerate(self.character_list):
                    if char_info["hwnd"] == current_hwnd and i != self.current_index:
                        self.current_index = i; self.hud.update_display(self.character_list, self.current_index, self.class_counts); break
            except Exception: pass
            time.sleep(0.25)
    _update_window_focus_lock = threading.Lock()
    def update_window_focus(self, direction):
        if self.is_paused or not self.character_list: return
        with self._update_window_focus_lock:
            new_index = (self.current_index + direction) % len(self.character_list)
            self.current_index = new_index
            try:
                target_char = self.character_list[self.current_index]
                hwnd = target_char["hwnd"]
                self.shell.SendKeys('%'); win32gui.SetForegroundWindow(hwnd)
                print(f"Cambiando a: {target_char['title']}")
                self.hud.update_display(self.character_list, self.current_index, self.class_counts)
            except Exception as e: print(f"Error al cambiar de ventana: {e}")
    def switch_to_next_window(self): self.update_window_focus(1)
    def switch_to_previous_window(self): self.update_window_focus(-1)

if __name__ == '__main__':
    app_controller = ReoTabsApp()
    sys.exit(app_controller.app.exec())
