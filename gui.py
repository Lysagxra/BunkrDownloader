import customtkinter as ctk
from downloader import main as downloader_main
import threading
import asyncio
import sys
from contextlib import redirect_stdout
import io
import os
import platform

class DownloaderUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Bunkr Downloader")
        self.geometry("500x400")

        self.grid_columnconfigure(0, weight=1)

        self.url_label = ctk.CTkLabel(self, text="Bunkr URL:")
        self.url_label.grid(row=0, column=0, padx=20, pady=(20, 5), sticky="w")

        self.url_entry = ctk.CTkEntry(self, placeholder_text="Enter Bunkr URL")
        self.url_entry.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        self.download_button = ctk.CTkButton(self, text="Download", command=self.start_download)
        self.download_button.grid(row=2, column=0, padx=20, pady=20)

        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        
        self.status_textbox = ctk.CTkTextbox(self, height=150)
        self.status_textbox.grid(row=4, column=0, padx=20, pady=(10, 5), sticky="nsew")
        self.status_textbox.configure(state="disabled")

        self.info_label = ctk.CTkLabel(self, text="GUI v2025.08.29 by ZeroHackz")
        self.info_label.grid(row=5, column=0, padx=20, pady=(5, 20), sticky="s")

        # Redirect stdout to the textbox
        sys.stdout = self.redirect_stdout_to_textbox()


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
        self.status_textbox.insert("end", f"Received URL: {url}\\n")
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
