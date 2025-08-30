from contextlib import redirect_stdout
from downloader import main as downloader_main
import asyncio
import customtkinter as ctk
import io
import os
import platform
import sys
import threading

GUI_VERSION = "2025.08.30"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class DownloaderUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Bunkr Downloader")
        self.geometry("500x450")

        try:
            # Set window icon
            self.after(200, lambda: self.iconbitmap(resource_path("icon.ico")))
        except Exception as e:
            # Use original stdout if icon loading fails, as sys.stdout is redirected
            print(f"Error loading icon: {e}", file=sys.__stdout__)

        self.grid_columnconfigure(0, weight=1)

        self.url_label = ctk.CTkLabel(self, text="Bunkr URL:")
        self.url_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        self.url_frame = ctk.CTkFrame(self)
        self.url_frame.grid(row=1, column=0, padx=20, pady=5, sticky="ew")
        self.url_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(self.url_frame, placeholder_text="Enter Bunkr URL")
        self.url_entry.grid(row=0, column=0, sticky="ew")

        self.paste_button = ctk.CTkButton(self.url_frame, text="Paste", command=self.paste_from_clipboard, width=50, fg_color="red", hover_color="#CC0000")
        self.paste_button.grid(row=0, column=1, padx=(10, 0))

        self.download_button = ctk.CTkButton(self, text="Download", command=self.start_download)
        self.download_button.grid(row=2, column=0, padx=20, pady=20)

        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        self.status_textbox = ctk.CTkTextbox(self, height=150)
        self.status_textbox.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="nsew")
        self.status_textbox.configure(state="disabled")

        self.info_label = ctk.CTkLabel(self, text=f"GUI v{GUI_VERSION} by ZeroHackz")
        self.info_label.grid(row=5, column=0, padx=20, pady=(5, 20), sticky="s")

        # Redirect stdout to the textbox
        sys.stdout = self.redirect_stdout_to_textbox()

    def paste_from_clipboard(self):
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
        class IORedirector(io.StringIO):
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
        url = self.url_entry.get()
        if not url:
            self.status_textbox.configure(state="normal")
            self.status_textbox.delete("1.0", "end")
            self.status_textbox.insert("end", "Please enter a URL.")
            self.status_textbox.configure(state="disabled")
            return

        self.download_button.configure(state="disabled")
        self.progress_bar.set(0)
        self.status_textbox.configure(state="normal")
        self.status_textbox.delete("1.0", "end")
        self.status_textbox.insert("end", f"Received URL: {url}\n")
        self.status_textbox.configure(state="disabled")

        # Run the downloader in a separate thread to avoid blocking the UI
        download_thread = threading.Thread(target=self.run_downloader, args=(url,))
        download_thread.start()

    def run_downloader(self, url):
        try:
            # It's tricky to run asyncio code in a separate thread when the main thread is not async.
            # A simple approach is to run the async main function using asyncio.run()
            # This will block the thread until the download is complete.
            
            # Mock downloader arguments
            sys.argv = ['downloader.py', url]
            
            download_path = asyncio.run(downloader_main())

            self.status_textbox.configure(state="normal")
            self.status_textbox.insert("end", "\nDownload finished!")
            self.status_textbox.configure(state="disabled")

            if download_path and platform.system() == "Windows":
                os.startfile(download_path)

        except Exception as e:
            self.status_textbox.configure(state="normal")
            self.status_textbox.insert("end", f"\nAn error occurred: {e}")
            self.status_textbox.configure(state="disabled")
        finally:
            self.download_button.configure(state="normal")
            self.progress_bar.set(1)


if __name__ == "__main__":
    app = DownloaderUI()
    app.mainloop()
