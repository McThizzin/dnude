import os
import sys
import json
import threading
import mammoth
import xml.etree.ElementTree as ET
import pdfplumber
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import customtkinter as ctk
from tkinter import filedialog, messagebox


def load_tags_config():
    config_file = 'tags_config.json'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {"default_tags": ["document"], "tag_map": {"1": "urgent", "2": "draft"}}
    return {"default_tags": ["document"], "tag_map": {"1": "urgent"}}


def create_frontmatter(filename, tags, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fm = "---\n"
    fm += f"source: {filename}\n"
    fm += f"converted_date: {timestamp}\n"
    fm += f"tags: [{', '.join(tags)}]\n"
    fm += "---\n\n"
    return fm


def docx_to_md(docx_path):
    with open(docx_path, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        return result.value


def xml_to_md(xml_content):
    root = ET.fromstring(xml_content)
    md_content = []
    stack = [(root, 0)]
    while stack:
        element, depth = stack.pop()
        indent = "  " * depth
        if depth == 0:
            md_content.append(f"# {element.tag}")
        else:
            md_content.append(f"{indent}**{element.tag}**")
        if element.text and element.text.strip():
            md_content.append(f"{indent}  - {element.text.strip()}")
        for child in reversed(list(element)):
            stack.append((child, depth + 1))
    return "\n".join(md_content)


def pdf_to_md(pdf_path):
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            content = f"## Page {i + 1}\n\n{text if text else '*(No text found)*'}"
            pages.append((i + 1, content))
    return pages


def process_single_file(path, output_dir, active_tags, timestamp):
    filename = os.path.basename(path)
    clean_name = os.path.splitext(filename)[0]
    folder_path = os.path.join(output_dir, clean_name)
    os.makedirs(folder_path, exist_ok=True)

    if filename.lower().endswith('.docx'):
        md_content = docx_to_md(path)
        final_content = create_frontmatter(filename, active_tags, timestamp) + md_content
        out_path = os.path.join(folder_path, f"{clean_name}.md")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(final_content)

    elif filename.lower().endswith('.xml'):
        with open(path, 'r', encoding='utf-8') as f:
            md_content = xml_to_md(f.read())
        final_content = create_frontmatter(filename, active_tags, timestamp) + md_content
        out_path = os.path.join(folder_path, f"{clean_name}.md")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(final_content)

    elif filename.lower().endswith('.pdf'):
        pages = pdf_to_md(path)
        for page_num, page_content in pages:
            frontmatter = create_frontmatter(
                f"{filename} (page {page_num})", active_tags, timestamp
            )
            out_path = os.path.join(folder_path, f"{clean_name}_p{page_num:03d}.md")
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(frontmatter + page_content)
    else:
        raise ValueError(f"Unsupported file type: {filename}")

    return filename


class DocConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("strip")
        self.geometry("650x700")
        ctk.set_appearance_mode("dark")

        self._set_window_icon()

        self.config = load_tags_config()
        self.selected_files = []
        self.tag_vars = {}

        font_family = "Hack Nerd Font" if sys.platform.startswith("linux") else "Consolas"
        self.label = ctk.CTkLabel(
            self, text="-strip-",
            font=ctk.CTkFont(family=font_family, size=24, weight="bold"),
            text_color="#ff6b35"
        )
        self.label.pack(pady=20)

        self.btn_select = ctk.CTkButton(self, text="1. Select Files", command=self.select_files)
        self.btn_select.pack(pady=5)

        self.file_info = ctk.CTkLabel(self, text="No files selected", text_color="gray")
        self.file_info.pack(pady=5)

        self.tag_frame = ctk.CTkScrollableFrame(self, label_text="2. Select Tags", width=400, height=180)
        self.tag_frame.pack(pady=15, padx=20, fill="x")
        self.setup_tag_checkboxes()

        self.btn_convert = ctk.CTkButton(
            self, text="3. Start Conversion",
            fg_color="#2c6e49", hover_color="#1e4a32",
            command=self.start_conversion
        )
        self.btn_convert.pack(pady=10)

        self.progress = ctk.CTkProgressBar(self, width=500)
        self.progress.set(0)
        self.progress.pack(pady=10)

        self.textbox = ctk.CTkTextbox(self, width=550, height=150)
        self.textbox.pack(pady=10, padx=20)

    def _set_window_icon(self):
        try:
            if sys.platform.startswith("linux"):
                icon_path = "icon.ico"
                if os.path.exists(icon_path):
                    img = ctk.CTkImage(light_image=None, dark_image=None, size=(32, 32))
                    self.iconphoto(False, img)
                    self.tk.call("wm", "iconphoto", self._w, img)
            else:
                self.iconbitmap("icon.ico")
        except Exception:
            pass

    def setup_tag_checkboxes(self):
        all_tags = set(self.config.get("tag_map", {}).values())
        all_tags.update(self.config.get("default_tags", []))
        for tag in sorted(all_tags):
            var = ctk.BooleanVar(value=False)
            cb = ctk.CTkCheckBox(self.tag_frame, text=tag, variable=var)
            cb.pack(anchor="w", padx=10, pady=2)
            self.tag_vars[tag] = var

    def log(self, message):
        self.textbox.insert("end", f"{message}\n")
        self.textbox.see("end")

    def select_files(self):
        self.selected_files = filedialog.askopenfilenames(
            filetypes=[("Docs", "*.docx *.xml *.pdf")]
        )
        if self.selected_files:
            self.file_info.configure(
                text=f"{len(self.selected_files)} files loaded",
                text_color="cyan"
            )
            self.progress.set(0)

    def start_conversion(self):
        if not self.selected_files:
            messagebox.showwarning("Error", "Select files first!")
            return

        output_dir = filedialog.askdirectory(title="Select Output Folder")
        if not output_dir:
            return

        active_tags = [tag for tag, var in self.tag_vars.items() if var.get()]
        if not active_tags:
            active_tags = self.config.get("default_tags", ["document"])

        self.btn_convert.configure(state="disabled", text="Converting...")
        self.progress.set(0)
        self.textbox.delete("0.0", "end")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        threading.Thread(
            target=self._run_conversion,
            args=(output_dir, active_tags, timestamp),
            daemon=True
        ).start()

    def _run_conversion(self, output_dir, active_tags, timestamp):
        total = len(self.selected_files)
        completed = 0
        max_workers = min(8, os.cpu_count() or 4)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    process_single_file, path, output_dir, active_tags, timestamp
                ): path for path in self.selected_files
            }

            for future in as_completed(futures):
                path = futures[future]
                filename = os.path.basename(path)
                try:
                    future.result()
                    self.after(0, self.log, f"  Success: {filename}")
                except Exception as e:
                    self.after(0, self.log, f"  Failed: {filename} - {e}")

                completed += 1
                self.after(0, self.progress.set, completed / total)

        self.after(0, self._conversion_done)

    def _conversion_done(self):
        self.btn_convert.configure(state="normal", text="3. Start Conversion")
        messagebox.showinfo("Done", "All files have been processed!")


if __name__ == "__main__":
    app = DocConverterApp()
    app.mainloop()
