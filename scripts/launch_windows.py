import os
import sys
from pathlib import Path

import click
from streamlit.web.cli import main as streamlit_main


def main():
    os.chdir(Path(__file__).resolve().parents[1])
    os.environ["NO_COLOR"] = "1"
    os.environ["TERM"] = "dumb"
    os.environ["CLICOLOR"] = "0"
    os.environ.pop("FORCE_COLOR", None)
    os.environ.pop("CLICOLOR_FORCE", None)
    # Nested Click command contexts inherit the explicit color policy.
    with click.Context(streamlit_main, color=False):
        streamlit_main(args=["run", "ui/app.py", *sys.argv[1:]], prog_name="streamlit")


if __name__ == "__main__":
    main()
