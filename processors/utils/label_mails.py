import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class TextLabeler:
    def __init__(self, root):
        self.root = root
        self.root.title("Разметчик текстовых файлов")
        self.root.geometry("900x600")

        # Данные
        self.files = []  # список путей к файлам
        self.current_index = -1
        self.labels = {}  # словарь: путь_файла -> метка

        # Классы для разметки
        self.classes = ["request", "calculation", "question", "review"]

        # Создаем интерфейс
        self.create_widgets()

    def create_widgets(self):
        # Верхняя панель управления
        top_frame = ttk.Frame(self.root, padding="5")
        top_frame.pack(fill=tk.X)

        ttk.Button(
            top_frame, text="Открыть папку с файлами", command=self.open_folder
        ).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Сохранить разметку", command=self.save_labels).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(top_frame, text="Загрузить разметку", command=self.load_labels).pack(
            side=tk.LEFT, padx=5
        )

        # Информационная панель
        info_frame = ttk.Frame(self.root, padding="5")
        info_frame.pack(fill=tk.X)

        self.file_counter_label = ttk.Label(info_frame, text="Файл: 0/0")
        self.file_counter_label.pack(side=tk.LEFT, padx=5)

        self.current_file_label = ttk.Label(info_frame, text="Текущий файл: -")
        self.current_file_label.pack(side=tk.LEFT, padx=20)

        # Панель навигации
        nav_frame = ttk.Frame(self.root, padding="5")
        nav_frame.pack(fill=tk.X)

        ttk.Button(nav_frame, text="◀ Предыдущий", command=self.prev_file).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(nav_frame, text="Следующий ▶", command=self.next_file).pack(
            side=tk.LEFT, padx=5
        )

        # Основная область с текстом
        text_frame = ttk.LabelFrame(self.root, text="Содержимое файла", padding="5")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Добавляем scrollbar
        text_scroll = ttk.Scrollbar(text_frame)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.text_widget = tk.Text(
            text_frame, wrap=tk.WORD, yscrollcommand=text_scroll.set
        )
        self.text_widget.pack(fill=tk.BOTH, expand=True)
        text_scroll.config(command=self.text_widget.yview)

        # Панель разметки
        label_frame = ttk.Frame(self.root, padding="5")
        label_frame.pack(fill=tk.X)

        ttk.Label(label_frame, text="Класс:").pack(side=tk.LEFT, padx=5)

        self.class_var = tk.StringVar()
        self.class_combobox = ttk.Combobox(
            label_frame,
            textvariable=self.class_var,
            values=self.classes,
            state="readonly",
            width=20,
        )
        self.class_combobox.pack(side=tk.LEFT, padx=5)
        self.class_combobox.bind("<<ComboboxSelected>>", self.on_class_selected)

        self.save_button = ttk.Button(
            label_frame,
            text="Сохранить разметку файла",
            command=self.save_current_label,
        )
        self.save_button.pack(side=tk.LEFT, padx=20)

        # Статусная строка
        self.status_var = tk.StringVar(value="Готов к работе")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def open_folder(self):
        """Открыть папку с txt файлами"""
        folder_path = filedialog.askdirectory(title="Выберите папку с txt файлами")

        if folder_path:
            self.files = sorted([str(f) for f in Path(folder_path).glob("*.txt")])

            if not self.files:
                messagebox.showwarning(
                    "Предупреждение", "В выбранной папке нет txt файлов"
                )
                return

            self.current_index = 0
            self.labels.clear()
            self.update_display()
            self.status_var.set(f"Загружено {len(self.files)} файлов")

    def update_display(self):
        """Обновить отображение текущего файла"""
        if not self.files or self.current_index < 0:
            return

        # Обновляем счетчик
        self.file_counter_label.config(
            text=f"Файл: {self.current_index + 1}/{len(self.files)}"
        )

        # Обновляем имя файла
        current_file = self.files[self.current_index]
        self.current_file_label.config(
            text=f"Текущий файл: {os.path.basename(current_file)}"
        )

        # Загружаем содержимое файла
        try:
            with open(current_file, "r", encoding="utf-8") as f:
                content = f.read()

            self.text_widget.delete(1.0, tk.END)
            self.text_widget.insert(1.0, content)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл: {e}")
            return

        # Восстанавливаем метку, если она уже есть
        if current_file in self.labels:
            self.class_var.set(self.labels[current_file])
        else:
            self.class_var.set("")

    def prev_file(self):
        """Перейти к предыдущему файлу"""
        if self.current_index > 0:
            self.current_index -= 1
            self.update_display()

    def next_file(self):
        """Перейти к следующему файлу"""
        if self.current_index < len(self.files) - 1:
            self.current_index += 1
            self.update_display()

    def on_class_selected(self, event):
        """Обработчик выбора класса из выпадающего списка"""
        selected_class = self.class_var.get()
        if selected_class and self.files:
            current_file = self.files[self.current_index]
            self.labels[current_file] = selected_class
            self.status_var.set(f"Класс '{selected_class}' выбран для текущего файла")

    def save_current_label(self):
        """Сохранить метку для текущего файла"""
        if not self.files or self.current_index < 0:
            return

        selected_class = self.class_var.get()
        if not selected_class:
            messagebox.showwarning("Предупреждение", "Выберите класс из списка")
            return

        current_file = self.files[self.current_index]
        self.labels[current_file] = selected_class
        self.status_var.set(
            f"Метка сохранена: {os.path.basename(current_file)} -> {selected_class}"
        )

        # Автоматически переходим к следующему файлу
        self.next_file()

    def save_labels(self):
        """Сохранить все метки в файл"""
        if not self.labels:
            messagebox.showwarning("Предупреждение", "Нет размеченных файлов")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Сохранить разметку",
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("filename,label,class_index\n")
                    for file_path_item, label in self.labels.items():
                        f.write(
                            f"{os.path.basename(file_path_item)},{label},{self.classes.index(label)}\n"
                        )

                self.status_var.set(f"Разметка сохранена: {len(self.labels)} файлов")
                messagebox.showinfo("Успех", f"Разметка сохранена в {file_path}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить разметку: {e}")

    def load_labels(self):
        """Загрузить разметку из файла"""
        file_path = filedialog.askopenfilename(
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Загрузить разметку",
        )

        if file_path:
            try:
                loaded_labels = {}
                with open(file_path, "r", encoding="utf-8") as f:
                    next(f)  # пропускаем заголовок
                    for line in f:
                        parts = line.strip().split(",")
                        if len(parts) == 2:
                            filename, label = parts
                            # Ищем полный путь к файлу
                            for full_path in self.files:
                                if os.path.basename(full_path) == filename:
                                    loaded_labels[full_path] = label
                                    break

                self.labels = loaded_labels
                self.update_display()
                self.status_var.set(f"Загружено {len(self.labels)} меток")
                messagebox.showinfo("Успех", f"Загружено {len(self.labels)} меток")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось загрузить разметку: {e}")


def main():
    root = tk.Tk()
    app = TextLabeler(root)
    root.mainloop()


if __name__ == "__main__":
    main()
