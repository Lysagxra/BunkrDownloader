# Bunkr Downloader - GUI Edition

This project is a fork of the original [BunkrDownloader by Lysagxra](https://github.com/Lysagxra/BunkrDownloader). Huge thanks to her for creating and maintaining the powerful core of this application!

This version focuses on providing a user-friendly **Graphical User Interface (GUI)** for Windows users and includes other features to make downloading from Bunkr as simple as possible.

![Screenshot of the new GUI](TODO)
> *Note: The GIF above shows the CLI version. A new GIF for the GUI is coming soon!*

## ✨ Features

This fork includes all the powerful core features from the original, plus:

*   **Graphical User Interface (GUI):** A simple and intuitive interface for downloading. No command line needed!
*   **Portable Windows Executable:** Download and run the application directly without needing to install Python or any dependencies.
*   **Easy URL Pasting:** A convenient "Paste" button to quickly insert a Bunkr URL from your clipboard.
*   **Automatic Folder Opening:** Once your download is complete, the folder containing the files will automatically open.
*   **Build & Setup Scripts:** Comes with `.bat` scripts to easily set up the environment and build the executable from source.

### Core Features

- Downloads multiple files from an album concurrently.
- Supports batch downloading via a list of URLs.
- Supports selective file downloading based on filename criteria.
- Provides progress indication during downloads.
- Automatically creates a directory structure for organized storage.
- Logs URLs that encounter errors for troubleshooting.

## 💻 How to Use (Easy Way)

1.  Go to the [**Releases**](https://github.com/ZeroHackz/BunkrDownloader-Portable/releases) page.
2.  Download the latest `BunkrDownloaderGUI.exe` file.
3.  Run the application, paste your Bunkr URL, and click **Download**. That's it!

## 🛠️ For Developers (Building from Source)

If you want to build the application yourself:

1.  Clone this repository:
    ```bash
    git clone https://github.com/ZeroHackz/BunkrDownloader.git
    ```
2.  Navigate to the project directory:
    ```bash
    cd BunkrDownloader
    ```
3.  Run the setup script. This will create a virtual environment and install the required dependencies.
    ```bat
    setup_launcher.bat
    ```
4.  To build the executable, run the build script:
    ```bat
    build.bat
    ```
    The `.exe` will be available in the `dist` folder.

## CLI Usage

The original command-line interface is still available and fully functional.

### Single Download

```bash
python3 downloader.py <bunkr_url>
```

### Selective & Batch Downloads

All the original flags like `--ignore`, `--include`, and batch downloading via `URLs.txt` are still supported. For more details, please refer to the [original README](https://github.com/Lysagxra/BunkrDownloader/blob/main/README.md).

## Logging

The application logs any issues encountered during the download process in a file named `session_log.txt`. Check this file for any URLs that may have been blocked or had errors.
