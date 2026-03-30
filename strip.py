import os
import json
import mammoth
import xml.etree.ElementTree as ET
import pdfplumber
from datetime import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox

# --- Logic from strip.py ---

def load_tags_config():
    config_file = 'tags_config.json'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"default_tags": ["document"], "tag_map": {"1": "urgent", "2": "draft"}}
    return {"default_tags": ["document"], "tag_map": {"1": "urgent"}}

def create_frontmatter(filename, tags):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fm = "---\n"
    fm += f"source: {filename}\n"
    fm += f"converted_date: {now}\n"
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
    def process_element(element, depth=0):
        indent = "  " * depth
        if depth == 0: md_content.append(f"# {element.tag}")
        else: md_content.append(f"{indent}**{element.tag}**")
        if element.text and element.text.strip():
            md_content.append(f"{indent}  - {element.text.strip()}")
        for child in element: process_element(child, depth + 1)
    process_element(root)
    return "\n".join(md_content)

def pdf_to_md(pdf_path):
    """Returns a list of (page_number, markdown_string) tuples."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            content = f"## Page {i + 1}\n\n{text if text else '*(No text found)*'}"
            pages.append((i + 1, content))
    return pages

# --- GUI Application ---

class DocConverterApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("strip")
        self.geometry("650x700")
        ctk.set_appearance_mode("dark")
        try:
            self.after(200, lambda: self.iconbitmap("icon.ico"))
        except:
            pass

        self.config = load_tags_config()
        self.selected_files = []
        self.tag_vars = {}

        # 1. Header
        self.label = ctk.CTkLabel(self, text="-strip-", font=("Consolas", 24, "bold"), text_color="#ff6b35")
        self.label.pack(pady=20)

        # 2. File Selection
        self.btn_select = ctk.CTkButton(self, text="1. Select Files", command=self.select_files)
        self.btn_select.pack(pady=5)

        self.file_info = ctk.CTkLabel(self, text="No files selected", text_color="gray")
        self.file_info.pack(pady=5)

        # 3. Tags (Checkboxes)
        self.tag_frame = ctk.CTkScrollableFrame(self, label_text="2. Select Tags", width=400, height=180)
        self.tag_frame.pack(pady=15, padx=20, fill="x")
        self.setup_tag_checkboxes()

        # 4. Conversion Action
        self.btn_convert = ctk.CTkButton(self, text="3. Start Conversion", fg_color="#2c6e49", hover_color="#1e4a32", command=self.process_files)
        self.btn_convert.pack(pady=10)

        # 5. Progress Bar
        self.progress = ctk.CTkProgressBar(self, width=500)
        self.progress.set(0)
        self.progress.pack(pady=10)

        # 6. Logs
        self.textbox = ctk.CTkTextbox(self, width=550, height=150)
        self.textbox.pack(pady=10, padx=20)

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
        self.update_idletasks()

    def select_files(self):
        self.selected_files = filedialog.askopenfilenames(filetypes=[("Docs", "*.docx *.xml *.pdf")])
        if self.selected_files:
            self.file_info.configure(text=f"{len(self.selected_files)} files loaded", text_color="cyan")
            self.progress.set(0)

    def process_files(self):
        if not self.selected_files:
            messagebox.showwarning("Error", "Select files first!")
            return

        output_dir = filedialog.askdirectory(title="Select Output Folder")
        if not output_dir: return

        active_tags = [tag for tag, var in self.tag_vars.items() if var.get()]
        if not active_tags: active_tags = self.config.get("default_tags", ["document"])

        total = len(self.selected_files)

        for i, path in enumerate(self.selected_files):
            filename = os.path.basename(path)
            clean_name = os.path.splitext(filename)[0]

            try:
                folder_path = os.path.join(output_dir, clean_name)
                os.makedirs(folder_path, exist_ok=True)

                if filename.lower().endswith('.docx'):
                    md_content = docx_to_md(path)
                    final_content = create_frontmatter(filename, active_tags) + md_content
                    with open(os.path.join(folder_path, f"{clean_name}.md"), 'w', encoding='utf-8') as f:
                        f.write(final_content)

                elif filename.lower().endswith('.xml'):
                    with open(path, 'r', encoding='utf-8') as f:
                        md_content = xml_to_md(f.read())
                    final_content = create_frontmatter(filename, active_tags) + md_content
                    with open(os.path.join(folder_path, f"{clean_name}.md"), 'w', encoding='utf-8') as f:
                        f.write(final_content)

                elif filename.lower().endswith('.pdf'):
                    pages = pdf_to_md(path)
                    for page_num, page_content in pages:
                        frontmatter = create_frontmatter(f"{filename} (page {page_num})", active_tags)
                        out_path = os.path.join(folder_path, f"{clean_name}_p{page_num:03d}.md")
                        with open(out_path, 'w', encoding='utf-8') as f:
                            f.write(frontmatter + page_content)

                self.log(f"✅ Success: {filename}")

            except Exception as e:
                self.log(f"❌ Failed: {filename} - {str(e)}")

            self.progress.set((i + 1) / total)

        messagebox.showinfo("Done", "All files have been processed!")

if __name__ == "__main__":
    app = DocConverterApp()
    app.mainloop()
