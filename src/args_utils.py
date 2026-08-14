"""Command-line argument parsing and configuration."""

from argparse import ArgumentParser, Namespace

from .config import DEFAULT_CONNECTIONS, MAX_RETRIES, apply_config_file_defaults
from .version import get_version_string


def add_common_arguments(parser: ArgumentParser) -> None:
    """Add arguments shared across parsers."""
    parser.add_argument(
        "--custom-path",
        type=str,
        default=None,
        help="The directory where the downloaded content will be saved.",
    )
    parser.add_argument(
        "--no-download-folder",
        action="store_true",
        default=None,
        help="Save files without a 'Downloads' subfolder.",
    )
    parser.add_argument(
        "--no-album-folder",
        action="store_true",
        default=None,
        help=(
            "Save files without an 'ALBUM_TITLE (ALBUM_ID)' subfolder, "
            "directly into the download directory."
        ),
    )
    parser.add_argument(
        "--disable-ui",
        action="store_true",
        default=None,
        help="Disable the user interface.",
    )
    parser.add_argument(
        "--disable-disk-check",
        action="store_true",
        default=None,
        help="Disable the disk space check for available free space.",
    )
    parser.add_argument(
        "--disable-server-check",
        action="store_true",
        default=False,
        help=(
            "Disable the server status check and allow downloads from domains marked "
            "as offline."
        ),
    )
    parser.add_argument(
        "--clean-name",
        action="store_true",
        default=False,
        help="Keep the original filenames of downloaded files.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=(
            "Maximum number of retries for downloading a single media "
            f"(default: {MAX_RETRIES}).",
        ),
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=None,
        help=(
            "Number of parallel connections used for chunked downloads "
            f"(default: {DEFAULT_CONNECTIONS}). Set to 1 to disable chunked "
            "downloading."
        ),
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        metavar="KB/S",
        help=(
            "Maximum total download speed in KB/s, shared across all connections "
            "and concurrently downloading files (default: unlimited)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help=(
            "List the files that would be downloaded (with sizes and skip/filter "
            "status) without downloading or writing anything."
        ),
    )
    parser.add_argument(
        "--max-concurrent-urls",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Number of URLs from URLs.txt to process concurrently "
            "(default: 1 — sequential, same as before). Values above 1 disable the "
            "live progress UI (falls back to plain log lines) since the progress "
            "display only supports tracking one album at a time."
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "Path to a TOML config file providing default values for any "
            "of the above flags (default: looks for ./bunkr.toml). "
            "Explicit CLI flags always take precedence over the config file."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=get_version_string(),
        help="Show program's version and exit.",
    )


def setup_parser(
        *, include_url: bool = False, include_filters: bool = False,
    ) -> ArgumentParser:
    """Set up parser with optional argument groups."""
    parser = ArgumentParser(description="Command-line arguments.")

    if include_url:
        parser.add_argument("url", type=str, help="The URL to process")

    if include_filters:
        parser.add_argument(
            "--ignore",
            type=str,
            nargs="+",
            default=None,
            help="Skip files whose names contain any of these substrings.",
        )
        parser.add_argument(
            "--include",
            type=str,
            nargs="+",
            default=None,
            help="Only download files whose names contain these substrings.",
        )

    add_common_arguments(parser)
    return parser


def parse_arguments(*, common_only: bool = False) -> Namespace:
    """Full argument parser (including URL, filters, and common).

    After parsing, any flag left unset on the command line is filled in from bunkr.toml
    (if present) and finally from built-in defaults -- see apply_config_file_defaults.
    """
    parser = (
        setup_parser() if common_only
        else setup_parser(include_url=True, include_filters=True)
    )
    args = parser.parse_args()
    return apply_config_file_defaults(args)
