#!/usr/bin/env python3
"""Local desktop UI for PNG radiograph anonymization."""

from __future__ import annotations

import queue
import shutil
import tempfile
import threading
import webbrowser
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD

    BaseTk = TkinterDnD.Tk
    DND_AVAILABLE = True
except Exception:
    DND_FILES = None
    BaseTk = tk.Tk
    DND_AVAILABLE = False

from anonymize_radiograph import DEFAULT_CLASS_NAMES, DEFAULT_MODEL, process_image_selection
from ocr_rules import DEFAULT_RULES_PATH, load_ocr_rules, new_rule, normalize_rule, save_ocr_rules
from paths import bundled_path


APP_TITLE = "AnonRad AI"
BRAND_NAME = "AnonRad AI"
LOGO_PATH = bundled_path("resources", "logo.png")
DEFAULT_CONFIDENCE = 0.25
DEFAULT_PADDING = 0.10
FIELD_LABELS = {
    "name": "Nombre",
    "id": "Identificador",
    "age": "Edad",
    "date": "Fecha",
    "time": "Hora",
}


class AnonymizerApp(BaseTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1080x760")
        self.minsize(960, 680)

        self.selected_images: list[Path] = []
        self.ocr_rules = load_ocr_rules()
        self.padding = tk.DoubleVar(value=DEFAULT_PADDING)
        self.field_vars = {field: tk.BooleanVar(value=True) for field in DEFAULT_CLASS_NAMES}
        self.advanced_visible = tk.BooleanVar(value=False)
        self.is_processing = False
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.temp_workdir: tempfile.TemporaryDirectory | None = None
        self.logo_image = self._load_logo()

        self._configure_style()
        self._build_ui()
        self.after(100, self._poll_messages)

    def _load_logo(self) -> ImageTk.PhotoImage | None:
        if not LOGO_PATH.exists():
            return None
        image = Image.open(LOGO_PATH).convert("RGBA")
        image.thumbnail((82, 82), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(image)

    def _configure_style(self) -> None:
        # Light, minimal palette built around the logo's teal accent.
        self.col_bg = "#ffffff"
        self.col_surface = "#f5f7f9"
        self.col_border = "#e8edf1"
        self.col_text = "#11222c"
        self.col_muted = "#6b7c89"
        self.col_accent = "#0f766e"
        self.col_accent_dark = "#0b5f59"
        self.col_accent_soft = "#e7f5f3"

        self.configure(bg=self.col_bg)
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=self.col_bg)
        style.configure("Surface.TFrame", background=self.col_bg)
        style.configure("TLabel", background=self.col_bg, foreground=self.col_text)
        style.configure("Surface.TLabel", background=self.col_bg, foreground=self.col_text)
        style.configure("Muted.TLabel", background=self.col_bg, foreground=self.col_muted)
        style.configure("Eyebrow.TLabel", background=self.col_bg, foreground=self.col_muted, font=("TkDefaultFont", 9, "bold"))
        style.configure("Header.TLabel", background=self.col_bg, foreground=self.col_text, font=("TkDefaultFont", 22, "bold"))
        style.configure("Section.TLabel", background=self.col_bg, foreground=self.col_text, font=("TkDefaultFont", 12, "bold"))

        style.configure("Primary.TButton", background=self.col_accent, foreground="#ffffff", borderwidth=0, focusthickness=0, padding=(22, 12), font=("TkDefaultFont", 11, "bold"))
        style.map("Primary.TButton", background=[("active", self.col_accent_dark), ("disabled", "#a9c2bd")])
        style.configure("Secondary.TButton", background=self.col_accent_soft, foreground=self.col_accent_dark, borderwidth=0, padding=(13, 8))
        style.map("Secondary.TButton", background=[("active", "#d6ece8")])
        style.configure("Danger.TButton", background="#fdecec", foreground="#a12525", borderwidth=0, padding=(11, 7))
        style.map("Danger.TButton", background=[("active", "#f8dada")])
        style.configure("Ghost.TButton", background=self.col_bg, foreground=self.col_muted, borderwidth=0, padding=(9, 6))
        style.map("Ghost.TButton", background=[("active", self.col_surface)])
        style.configure("TButton", padding=(10, 7))
        style.configure("TCheckbutton", background=self.col_bg, foreground=self.col_text, padding=(0, 5))
        style.map("TCheckbutton", background=[("active", self.col_bg)])
        style.configure("TSpinbox", arrowsize=12)
        style.configure("Horizontal.TProgressbar", troughcolor=self.col_surface, background=self.col_accent, bordercolor=self.col_surface, lightcolor=self.col_accent, darkcolor=self.col_accent)
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=self.col_text, borderwidth=0, rowheight=27)
        style.configure("Treeview.Heading", background=self.col_surface, foreground=self.col_muted, relief="flat", font=("TkDefaultFont", 9, "bold"), padding=(6, 5))
        style.map("Treeview", background=[("selected", self.col_accent_soft)], foreground=[("selected", self.col_text)])
        style.map("Treeview.Heading", background=[("active", self.col_surface)])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=(28, 22))
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # ---- Header ----
        header = ttk.Frame(root, style="Surface.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        if self.logo_image is not None:
            tk.Label(header, image=self.logo_image, bg=self.col_bg).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        else:
            tk.Label(
                header, text="AI", bg=self.col_accent, fg="#ffffff", width=4, height=2, font=("TkDefaultFont", 16, "bold")
            ).grid(row=0, column=0, rowspan=2, padx=(0, 14))
        ttk.Label(header, text=BRAND_NAME, style="Header.TLabel").grid(row=0, column=1, sticky="sw")
        ttk.Label(header, text="Anonimización local de radiografías", style="Muted.TLabel").grid(
            row=1, column=1, sticky="nw", pady=(2, 0)
        )
        tk.Label(
            header, text="  LOCAL  ", bg=self.col_accent_soft, fg=self.col_accent_dark, font=("TkDefaultFont", 9, "bold")
        ).grid(row=0, column=2, rowspan=2, sticky="e")

        tk.Frame(root, height=1, bg=self.col_border).grid(row=1, column=0, sticky="ew", pady=(16, 20))

        # ---- Content: two airy columns, no heavy cards ----
        content = ttk.Frame(root)
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=3, uniform="cols")
        content.columnconfigure(1, weight=2, uniform="cols")
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 28))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(7, weight=1)

        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        # ---- Left: input + action + activity ----
        ttk.Label(left, text="IMÁGENES", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.drop_zone = tk.Frame(left, bg=self.col_surface, highlightbackground="#cfe3df", highlightthickness=1, height=134)
        self.drop_zone.grid(row=1, column=0, sticky="ew")
        self.drop_zone.columnconfigure(0, weight=1)
        self.drop_zone.grid_propagate(False)

        badge = tk.Label(
            self.drop_zone, text="+", bg=self.col_accent_soft, fg=self.col_accent, font=("TkDefaultFont", 17, "bold"), padx=11
        )
        badge.grid(row=0, column=0, pady=(24, 8))
        self.drop_title = tk.Label(
            self.drop_zone,
            text="Arrastra o haz clic para añadir",
            bg=self.col_surface,
            fg=self.col_text,
            font=("TkDefaultFont", 14, "bold"),
        )
        self.drop_title.grid(row=1, column=0)
        hint = "Imágenes, DICOM, ZIP o una carpeta"
        if not DND_AVAILABLE:
            hint += " · arrastrar requiere tkinterdnd2"
        self.drop_hint = tk.Label(self.drop_zone, text=hint, bg=self.col_surface, fg=self.col_muted)
        self.drop_hint.grid(row=2, column=0, pady=(3, 24))

        def _drop_enter(_event):
            for widget in (self.drop_zone, self.drop_title, self.drop_hint):
                widget.configure(bg="#eef7f5")

        def _drop_leave(_event):
            for widget in (self.drop_zone, self.drop_title, self.drop_hint):
                widget.configure(bg=self.col_surface)

        for widget in (self.drop_zone, self.drop_title, self.drop_hint, badge):
            widget.bind("<Button-1>", lambda _event: self._open_input_menu())
        self.drop_zone.bind("<Enter>", _drop_enter)
        self.drop_zone.bind("<Leave>", _drop_leave)

        if DND_AVAILABLE:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._handle_drop)

        selection_bar = ttk.Frame(left)
        selection_bar.grid(row=2, column=0, sticky="ew", pady=(12, 6))
        selection_bar.columnconfigure(0, weight=1)
        self.selection_label = ttk.Label(selection_bar, text="0 elementos seleccionados", style="Muted.TLabel")
        self.selection_label.grid(row=0, column=0, sticky="w")
        ttk.Button(selection_bar, text="Limpiar", style="Ghost.TButton", command=self._clear_selection).grid(
            row=0, column=1, sticky="e"
        )

        self.selection_list = tk.Listbox(
            left,
            height=4,
            relief=tk.FLAT,
            bg=self.col_surface,
            fg=self.col_text,
            highlightthickness=1,
            highlightbackground=self.col_border,
            selectbackground=self.col_accent_soft,
            selectforeground=self.col_text,
            activestyle="none",
            borderwidth=0,
        )
        self.selection_list.grid(row=3, column=0, sticky="ew")

        action = ttk.Frame(left)
        action.grid(row=4, column=0, sticky="ew", pady=(16, 0))
        action.columnconfigure(1, weight=1)
        self.process_button = ttk.Button(action, text="Anonimizar", style="Primary.TButton", command=self._start_processing)
        self.process_button.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(action, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=(14, 0))

        ttk.Label(left, text="Redacción irreversible · método blur_then_black", style="Muted.TLabel").grid(
            row=5, column=0, sticky="w", pady=(10, 18)
        )

        ttk.Label(left, text="ACTIVIDAD", style="Eyebrow.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 8))
        self.log = tk.Text(
            left,
            height=7,
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief=tk.FLAT,
            bg=self.col_surface,
            fg=self.col_muted,
            highlightthickness=1,
            highlightbackground=self.col_border,
            borderwidth=0,
            padx=12,
            pady=10,
            font=("TkDefaultFont", 10),
        )
        self.log.grid(row=7, column=0, sticky="nsew")
        self._append_log("Listo. Selecciona imágenes o un ZIP para empezar.")

        # ---- Right: fields + extra text + advanced ----
        ttk.Label(right, text="CAMPOS A OCULTAR", style="Eyebrow.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Label(right, text="Detectados por IA · todos activos por defecto.", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(0, 10)
        )
        fields_frame = ttk.Frame(right)
        fields_frame.grid(row=2, column=0, sticky="ew")
        fields_frame.columnconfigure(0, weight=1)
        fields_frame.columnconfigure(1, weight=1)
        for index, field in enumerate(DEFAULT_CLASS_NAMES):
            ttk.Checkbutton(
                fields_frame,
                text=FIELD_LABELS.get(field, field),
                variable=self.field_vars[field],
            ).grid(row=index // 2, column=index % 2, sticky="w", padx=(0, 16), pady=(0, 4))

        tk.Frame(right, height=1, bg=self.col_border).grid(row=3, column=0, sticky="ew", pady=(20, 18))

        ttk.Label(right, text="TEXTO ADICIONAL A OCULTAR", style="Eyebrow.TLabel").grid(row=4, column=0, sticky="w", pady=(0, 4))
        ttk.Label(
            right,
            text="Tapa texto escrito en la imagen que coincida con una regex (p. ej. PORTABLE).",
            style="Muted.TLabel",
            wraplength=360,
            justify=tk.LEFT,
        ).grid(row=5, column=0, sticky="w", pady=(0, 10))

        self.ocr_tree = ttk.Treeview(right, columns=("enabled", "name", "pattern"), show="headings", height=4)
        self.ocr_tree.heading("enabled", text="Usar")
        self.ocr_tree.heading("name", text="Nombre")
        self.ocr_tree.heading("pattern", text="Regex")
        self.ocr_tree.column("enabled", width=52, stretch=False, anchor=tk.CENTER)
        self.ocr_tree.column("name", width=120, stretch=False)
        self.ocr_tree.column("pattern", width=180, stretch=True, anchor=tk.CENTER)
        self.ocr_tree.grid(row=6, column=0, sticky="ew", pady=(0, 10))

        ocr_buttons = ttk.Frame(right)
        ocr_buttons.grid(row=7, column=0, sticky="ew")
        ttk.Button(ocr_buttons, text="Añadir", style="Secondary.TButton", command=self._add_ocr_rule).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(ocr_buttons, text="Editar", style="Ghost.TButton", command=self._edit_ocr_rule).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(ocr_buttons, text="Activar", style="Ghost.TButton", command=self._toggle_ocr_rule).grid(row=0, column=2, padx=(0, 6))
        ttk.Button(ocr_buttons, text="Eliminar", style="Danger.TButton", command=self._delete_ocr_rule).grid(row=0, column=3)
        ttk.Label(right, text="El texto reconocido nunca se guarda.", style="Muted.TLabel").grid(
            row=8, column=0, sticky="w", pady=(10, 0)
        )
        self._refresh_ocr_rules()

        self.advanced_container = ttk.Frame(right)
        self.advanced_container.grid(row=9, column=0, sticky="ew", pady=(18, 0))
        self.advanced_container.columnconfigure(0, weight=1)
        ttk.Button(
            self.advanced_container, text="Ajustes avanzados", style="Ghost.TButton", command=self._toggle_advanced
        ).grid(row=0, column=0, sticky="w")

        self.advanced_frame = ttk.Frame(self.advanced_container)
        self.advanced_frame.columnconfigure(1, weight=1)
        ttk.Label(self.advanced_frame, text="Padding", style="Surface.TLabel").grid(row=0, column=0, sticky="w", pady=(12, 0))
        ttk.Spinbox(self.advanced_frame, from_=0.0, to=0.5, increment=0.05, textvariable=self.padding, width=8).grid(
            row=0, column=1, sticky="w", padx=(10, 0), pady=(12, 0)
        )
        ttk.Label(
            self.advanced_frame,
            text="Amplía ligeramente cada zona detectada antes de taparla.",
            style="Muted.TLabel",
            wraplength=360,
            justify=tk.LEFT,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _open_input_menu(self) -> None:
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Seleccionar archivo(s)", command=self._choose_files)
        menu.add_command(label="Seleccionar carpeta", command=self._choose_input_dir)
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _choose_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Seleccionar archivos",
            filetypes=[
                ("Imagenes y ZIP soportados", "*.png *.jpg *.jpeg *.dcm *.dicom *.zip"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if paths:
            self._add_paths([Path(path) for path in paths])

    def _choose_input_dir(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta")
        if path:
            self._add_paths([Path(path)])

    def _handle_drop(self, event) -> None:
        raw_paths = self.tk.splitlist(event.data)
        self._add_paths([Path(path) for path in raw_paths])

    def _add_paths(self, paths: list[Path]) -> None:
        inputs = self._resolve_inputs(paths)
        if not inputs:
            messagebox.showwarning("Sin archivos seleccionados", "No se encontraron archivos en la seleccion.")
            return
        known = {path.resolve() for path in self.selected_images}
        for item in inputs:
            resolved = item.resolve()
            if resolved not in known:
                self.selected_images.append(resolved)
                known.add(resolved)
        self._refresh_selection()

    def _resolve_inputs(self, paths: list[Path]) -> list[Path]:
        inputs: list[Path] = []
        supported = {".png", ".jpg", ".jpeg", ".dcm", ".dicom", ".zip"}
        for path in paths:
            path = path.expanduser()
            if path.is_dir():
                inputs.append(path)
            elif path.is_file() and path.suffix.lower() in supported:
                inputs.append(path)
            elif path.is_file():
                inputs.append(path)
        return inputs

    def _count_selected_candidates(self) -> int:
        supported = {".png", ".jpg", ".jpeg", ".dcm", ".dicom", ".zip"}
        count = 0
        for path in self.selected_images:
            if path.is_dir():
                count += sum(1 for child in path.rglob("*") if child.is_file() and child.suffix.lower() in supported)
            elif path.is_file() and path.suffix.lower() in supported:
                count += 1
            elif path.is_file():
                count += 1
        return count

    def _refresh_selection(self) -> None:
        self.selection_label.configure(
            text=f"{len(self.selected_images)} elemento(s), {self._count_selected_candidates()} archivo(s) candidato(s)"
        )
        self.selection_list.delete(0, tk.END)
        for image in self.selected_images:
            self.selection_list.insert(tk.END, str(image))

    def _clear_selection(self) -> None:
        self.selected_images.clear()
        self._refresh_selection()

    def _toggle_advanced(self) -> None:
        if self.advanced_visible.get():
            self.advanced_frame.grid_remove()
            self.advanced_visible.set(False)
        else:
            self.advanced_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
            self.advanced_visible.set(True)

    def _start_processing(self) -> None:
        if self.is_processing:
            return
        if not self.selected_images:
            messagebox.showerror("Entrada no valida", "Selecciona al menos una imagen, DICOM, ZIP o carpeta.")
            return

        if not DEFAULT_MODEL.exists():
            messagebox.showerror("Modelo no encontrado", f"No se encontro el modelo:\n{DEFAULT_MODEL}")
            return

        try:
            padding = float(self.padding.get())
        except ValueError:
            messagebox.showerror("Parametros no validos", "Padding debe ser numerico.")
            return
        if padding < 0:
            messagebox.showerror("Padding no valido", "El padding debe ser mayor o igual a 0.")
            return
        selected_fields = self._selected_fields()
        if not selected_fields:
            messagebox.showerror("Campos no validos", "Selecciona al menos un campo para anonimizar.")
            return
        active_ocr_rules = self._enabled_ocr_rules()

        self._cleanup_tempdir()
        self.temp_workdir = tempfile.TemporaryDirectory(prefix="radiograph_anonymizer_")
        temp_output = Path(self.temp_workdir.name) / "processed"

        self.is_processing = True
        self.process_button.configure(state=tk.DISABLED)
        self.progress.start(12)
        self._append_log("Cargando modelo y procesando imagenes en un espacio temporal privado...")

        worker = threading.Thread(
            target=self._process_worker,
            args=(list(self.selected_images), temp_output, padding, selected_fields, active_ocr_rules),
            daemon=True,
        )
        worker.start()

    def _selected_fields(self) -> list[str]:
        return [field for field, enabled in self.field_vars.items() if enabled.get()]

    def _enabled_ocr_rules(self) -> list[dict]:
        return [rule for rule in self.ocr_rules if rule.get("enabled")]

    def _process_worker(
        self,
        images: list[Path],
        output_path: Path,
        padding: float,
        selected_fields: list[str],
        active_ocr_rules: list[dict],
    ) -> None:
        try:
            result = process_image_selection(
                image_paths=images,
                output_path=output_path,
                conf=DEFAULT_CONFIDENCE,
                padding=padding,
                save_preview=False,
                device="cpu",
                write_metadata=False,
                selected_class_names=selected_fields,
                ocr_rules=active_ocr_rules,
                progress_callback=lambda index, total, image_path, summary: self.messages.put(
                    (
                        "progress",
                        f"[{index}/{total}] {image_path.name}: "
                        f"{len(summary['detections']) + len(summary['ocr_matches'])} ocultacion(es)",
                    )
                ),
            )
            self.messages.put(("done", result))
        except Exception as exc:
            self.messages.put(("error", exc))

    def _poll_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "progress":
                    self._append_log(str(payload))
                elif kind == "done":
                    result = payload
                    summaries = result["processed"]
                    skipped = result["skipped"]
                    total = len(summaries)
                    redactions = sum(len(summary["detections"]) + len(summary["ocr_matches"]) for summary in summaries)
                    ocr_matches = sum(len(summary["ocr_matches"]) for summary in summaries)
                    self._append_log(f"Completado: {total} imagen(es), {redactions} ocultacion(es).")
                    if ocr_matches:
                        self._append_log(f"Texto adicional: {ocr_matches} coincidencia(s) por patrones activos.")
                    if skipped:
                        self._append_log(f"Omitidos: {len(skipped)} archivo(s).")
                        for item in skipped[:10]:
                            self._append_log(f"  - {item['path']}: {item['reason']}")
                        if len(skipped) > 10:
                            self._append_log(f"  ... y {len(skipped) - 10} mas.")
                    self._finish_processing()
                    self._save_processed_outputs(summaries, skipped)
                elif kind == "error":
                    self._append_log(f"Error: {payload}")
                    self._finish_processing()
                    self._cleanup_tempdir()
                    messagebox.showerror("Error", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._poll_messages)

    def _finish_processing(self) -> None:
        self.is_processing = False
        self.progress.stop()
        self.process_button.configure(state=tk.NORMAL)

    def _save_processed_outputs(self, summaries: list[dict], skipped: list[dict]) -> None:
        if not summaries:
            self._cleanup_tempdir()
            detail = "\n".join(f"- {item['path']}: {item['reason']}" for item in skipped[:8])
            messagebox.showwarning("Sin resultados", "No se pudo procesar ninguna imagen valida.\n\n" + detail)
            return

        try:
            force_zip = any(path.is_dir() or path.suffix.lower() == ".zip" for path in self.selected_images)
            if len(summaries) == 1 and not force_zip:
                source = Path(summaries[0]["output"])
                target = filedialog.asksaveasfilename(
                    title="Guardar PNG anonimizado",
                    defaultextension=".png",
                    initialfile=source.name,
                    filetypes=[("PNG image", "*.png")],
                )
                if target:
                    shutil.copy2(source, target)
                    self._append_log(f"Imagen guardada: {target}")
                else:
                    self._append_log("Guardado cancelado. No se conservo ningun archivo temporal.")
            else:
                target = filedialog.asksaveasfilename(
                    title="Guardar ZIP con imagenes anonimizadas",
                    defaultextension=".zip",
                    initialfile="radiographs_anonymized.zip",
                    filetypes=[("ZIP archive", "*.zip")],
                )
                if target:
                    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                        for summary in summaries:
                            source = Path(summary["output"])
                            archive.write(source, arcname=source.name)
                    self._append_log(f"ZIP guardado: {target}")
                else:
                    self._append_log("Guardado cancelado. No se conservo ningun archivo temporal.")
        finally:
            self._cleanup_tempdir()

    def _cleanup_tempdir(self) -> None:
        if self.temp_workdir is not None:
            self.temp_workdir.cleanup()
            self.temp_workdir = None

    def _refresh_ocr_rules(self) -> None:
        for item in self.ocr_tree.get_children():
            self.ocr_tree.delete(item)
        for rule in self.ocr_rules:
            self.ocr_tree.insert(
                "",
                tk.END,
                iid=rule["id"],
                values=("Si" if rule.get("enabled") else "No", rule["name"], rule["pattern"]),
            )

    def _selected_ocr_rule_id(self) -> str | None:
        selection = self.ocr_tree.selection()
        if not selection:
            messagebox.showwarning("Selecciona una regex", "Selecciona primero una regex.")
            return None
        return str(selection[0])

    def _rule_index(self, rule_id: str) -> int | None:
        for index, rule in enumerate(self.ocr_rules):
            if rule["id"] == rule_id:
                return index
        return None

    def _save_ocr_rules(self) -> None:
        save_ocr_rules(self.ocr_rules)
        self._refresh_ocr_rules()

    def _add_ocr_rule(self) -> None:
        self._open_ocr_rule_dialog()

    def _edit_ocr_rule(self) -> None:
        rule_id = self._selected_ocr_rule_id()
        if rule_id is None:
            return
        index = self._rule_index(rule_id)
        if index is not None:
            self._open_ocr_rule_dialog(self.ocr_rules[index])

    def _toggle_ocr_rule(self) -> None:
        rule_id = self._selected_ocr_rule_id()
        if rule_id is None:
            return
        index = self._rule_index(rule_id)
        if index is None:
            return
        self.ocr_rules[index]["enabled"] = not self.ocr_rules[index].get("enabled")
        self._save_ocr_rules()

    def _delete_ocr_rule(self) -> None:
        rule_id = self._selected_ocr_rule_id()
        if rule_id is None:
            return
        index = self._rule_index(rule_id)
        if index is None:
            return
        if not messagebox.askyesno("Eliminar regex", "¿Quieres eliminar esta regex?"):
            return
        del self.ocr_rules[index]
        self._save_ocr_rules()

    def _open_ocr_rule_dialog(self, rule: dict | None = None) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Regla OCR")
        dialog.configure(bg=self.col_bg)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        name_var = tk.StringVar(value=rule["name"] if rule else "")
        pattern_var = tk.StringVar(value=rule["pattern"] if rule else "")
        enabled_var = tk.BooleanVar(value=bool(rule.get("enabled", True)) if rule else True)

        frame = ttk.Frame(dialog, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Nombre").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        ttk.Entry(frame, textvariable=name_var, width=48).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text="Regex").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        regex_entry = ttk.Entry(frame, textvariable=pattern_var, width=48, justify=tk.CENTER)
        regex_entry.grid(row=1, column=1, sticky="ew", pady=(0, 4))
        regex_help = tk.Label(
            frame,
            text="Ayuda para crear regex",
            bg=self.col_bg,
            fg=self.col_accent,
            cursor="hand2",
            font=("TkDefaultFont", 10, "underline"),
        )
        regex_help.grid(row=2, column=1, sticky="w", pady=(0, 8))
        regex_help.bind("<Button-1>", lambda _: webbrowser.open("https://www.autoregex.xyz/"))
        ttk.Checkbutton(frame, text="Usar esta regex", variable=enabled_var).grid(row=3, column=1, sticky="w", pady=(0, 12))

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")

        def save_rule() -> None:
            candidate = {
                "id": rule["id"] if rule else new_rule()["id"],
                "name": name_var.get(),
                "pattern": pattern_var.get(),
                "enabled": enabled_var.get(),
            }
            try:
                normalized = normalize_rule(candidate)
            except ValueError as exc:
                messagebox.showerror("Regex no valida", str(exc), parent=dialog)
                return
            if rule:
                index = self._rule_index(rule["id"])
                if index is not None:
                    self.ocr_rules[index] = normalized
            else:
                self.ocr_rules.append(normalized)
            self._save_ocr_rules()
            dialog.destroy()

        ttk.Button(buttons, text="Cancelar", command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Guardar", command=save_rule).grid(row=0, column=1)
        dialog.bind("<Return>", lambda _: save_rule())
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        dialog.wait_window()

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)


def main() -> None:
    app = AnonymizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
