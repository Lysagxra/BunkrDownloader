"""
This module contains the graphical user interface for the Bunkr Downloader.
"""
import asyncio
import io
import os
import platform
import sys
import threading
from tkinter import filedialog
import customtkinter as ctk
from downloader import main as downloader_main

GUI_VERSION = "2025.09.14"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class DownloaderUI(ctk.CTk):
    """
    A class to represent the Downloader UI.
    """
    def __init__(self):
        super().__init__()

        self.title("Bunkr Downloader")
        self.geometry("550x550")

        try:
            # Set window icon
            icon_path = resource_path(os.path.join("misc", "gui", "icons", "icon.ico"))
            self.after(200, lambda: self.iconbitmap(icon_path))
        except ctk.TclError as e:
            # Use original stdout if icon loading fails, as sys.stdout is redirected
            print(f"Error loading icon: {e}", file=sys.__stdout__)

        self.grid_columnconfigure(0, weight=1)

        # --- Download Mode ---
        self.mode_frame = ctk.CTkFrame(self)
        self.mode_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.mode_label = ctk.CTkLabel(self.mode_frame, text="Download Mode:")
        self.mode_label.pack(side="left", padx=10, pady=10)

        self.download_mode = ctk.StringVar(value="url")
        self.radio_url = ctk.CTkRadioButton(self.mode_frame,
                                              text="Single URL",
                                              variable=self.download_mode,
                                              value="url",
                                              command=self.toggle_mode)
        self.radio_url.pack(side="left", padx=10, pady=10)
        self.radio_file = ctk.CTkRadioButton(self.mode_frame,
                                               text="Load URLs from file",
                                               variable=self.download_mode,
                                               value="file",
                                               command=self.toggle_mode)
        self.radio_file.pack(side="left", padx=10, pady=10)

        # --- URL Input Frame ---
        self.url_input_frame = ctk.CTkFrame(self)
        self.url_input_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.url_input_frame.grid_columnconfigure(0, weight=1)

        self.url_label = ctk.CTkLabel(self.url_input_frame, text="Bunkr URL:")
        self.url_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        self.url_entry = ctk.CTkEntry(self.url_input_frame, placeholder_text="Enter Bunkr URL")
        self.url_entry.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

        self.paste_button = ctk.CTkButton(self.url_input_frame,
                                              text="Paste",
                                              command=self.paste_from_clipboard,
                                              width=50,
                                              fg_color="red",
                                              hover_color="#CC0000")
        self.paste_button.grid(row=1, column=1, padx=(0, 10), pady=10)

        # --- File Input Frame ---
        self.file_input_frame = ctk.CTkFrame(self)
        self.file_input_frame.grid_columnconfigure(0, weight=1)

        self.file_label = ctk.CTkLabel(self.file_input_frame, text="Path to URLs text file:")
        self.file_label.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 0), sticky="w")

        self.file_entry = ctk.CTkEntry(self.file_input_frame, placeholder_text="Select a .txt file")
        self.file_entry.grid(row=1, column=0, padx=10, pady=10, sticky="ew")

        self.browse_button = ctk.CTkButton(self.file_input_frame,
                                             text="Browse",
                                             command=self.browse_file,
                                             width=50)
        self.browse_button.grid(row=1, column=1, padx=(0, 10), pady=10)

        # --- Common UI Elements ---
        self.download_button = ctk.CTkButton(self, text="Download", command=self.start_download)
        self.download_button.grid(row=2, column=0, padx=20, pady=20)

        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        self.status_textbox = ctk.CTkTextbox(self, height=200)
        self.status_textbox.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="nsew")
        self.status_textbox.configure(state="disabled")

        self.info_label = ctk.CTkLabel(self, text=f"GUI v{GUI_VERSION} by ZeroHackz")
        self.info_label.grid(row=5, column=0, padx=20, pady=(5, 20), sticky="s")

        # Initial setup
        self.toggle_mode()

        # Redirect stdout to the textbox
        sys.stdout = self.redirect_stdout_to_textbox()

    def toggle_mode(self):
        """Toggles the UI between URL input and file input modes."""
        if self.download_mode.get() == "url":
            self.url_input_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
            self.file_input_frame.grid_forget()
        else:
            self.file_input_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
            self.url_input_frame.grid_forget()

    def browse_file(self):
        """Opens a file dialog to select a file containing URLs."""
        file_path = filedialog.askopenfilename(
            title="Select a URL file",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )
        if file_path:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, file_path)

    def paste_from_clipboard(self):
        """Pastes content from the clipboard into the URL entry field."""
        try:
            clipboard_content = self.clipboard_get()
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, clipboard_content)
        except ctk.TclError:
            self.status_textbox.configure(state="normal")
            self.status_textbox.delete("1.0", "end")
            self.status_textbox.insert("end", "Could not get text from clipboard.")
            self.status_textbox.configure(state="disabled")

    def redirect_stdout_to_textbox(self):
        """Redirects stdout to the status textbox."""
        class IORedirector(io.StringIO):
            """A class to redirect stdout to a textbox."""
            def __init__(self, textbox):
                super().__init__()
                self.textbox = textbox

            def write(self, text):
                self.textbox.configure(state="normal")
                self.textbox.insert("end", text)
                self.textbox.see("end")
                self.textbox.configure(state="disabled")

            def flush(self):
                pass

        return IORedirector(self.status_textbox)

    def start_download(self):
        """Starts the download process."""
        self.download_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_textbox.configure(state="normal")
        self.status_textbox.delete("1.0", "end")
        self.status_textbox.configure(state="disabled")

        mode = self.download_mode.get()
        if mode == "url":
            url = self.url_entry.get()
            if not url:
                self.status_textbox.configure(state="normal")
                self.status_textbox.insert("end", "Please enter a URL.")
                self.status_textbox.configure(state="disabled")
                self.download_button.configure(state="normal")
                return
            urls = [url]
        else: # mode == "file"
            file_path = self.file_entry.get()
            if not file_path:
                self.status_textbox.configure(state="normal")
                self.status_textbox.insert("end", "Please select a file.")
                self.status_textbox.configure(state="disabled")
                self.download_button.configure(state="normal")
                return
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip()]
                if not urls:
                    self.status_textbox.configure(state="normal")
                    self.status_textbox.insert("end", "File is empty or contains no valid URLs.")
                    self.status_textbox.configure(state="disabled")
                    self.download_button.configure(state="normal")
                    return
            except (IOError, OSError) as e:
                self.status_textbox.configure(state="normal")
                self.status_textbox.insert("end", f"Error reading file: {e}")
                self.status_textbox.configure(state="disabled")
                self.download_button.configure(state="normal")
                return

        # Run the downloader in a separate thread
        download_thread = threading.Thread(target=self.run_downloader_batch, args=(urls,))
        download_thread.start()

    def run_downloader_batch(self, urls):
        """Runs the downloader for a batch of URLs."""
        total_urls = len(urls)
        for i, url in enumerate(urls):
            self.status_textbox.configure(state="normal")
            self.status_textbox.insert("end", f"'\n--- Starting download for: {url} "
                                                  f"({i+1}/{total_urls}) ---\n")
            self.status_textbox.configure(state="disabled")
            try:
                # Mock downloader arguments for each URL
                sys.argv = ['downloader.py', url]
                download_path = asyncio.run(downloader_main())

                self.status_textbox.configure(state="normal")
                self.status_textbox.insert("end", f"\n--- Finished download for: {url} ---\n\n")
                self.status_textbox.configure(state="disabled")

                # Open folder only after the last download
                if i == total_urls - 1 and download_path and platform.system() == "Windows":
                    os.startfile(download_path)

            except Exception as e:
                self.status_textbox.configure(state="normal")
                self.status_textbox.insert("end", f"\nAn error occurred with {url}: {e}\n\n")
                self.status_textbox.configure(state="disabled")
        self.status_textbox.configure(state="normal")
        self.status_textbox.insert("end", "\nAll downloads finished!")
        self.status_textbox.configure(state="disabled")
        self.download_button.configure(state="normal")
        self.progress_bar.set(1)


if __name__ == "__main__":
    app = DownloaderUI()
    app.mainloop()
