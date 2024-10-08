"""
KudoMan
Copyright (C) 2024 Unit1208

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import datetime
import matplotlib.axes
import requests
import time
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import os
from pathlib import Path
import dotenv
import logging
import psutil
import coloredlogs
import gzip
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

dotenv.load_dotenv()


class Config(BaseSettings):
    LOGLEVEL: str = Field(default="INFO")
    API_KEY: str = Field()
    REQTIME: int = Field(default=60)
    SHOWMA: bool = Field(default=True)
    SHOWD1: bool = Field(default=True)
    SHOWMAD1: bool = Field(default=True)
    NUMBACKUPS: int = Field(default=10)
    # Default to averaging over 2 days (24 hours * 60 minutes * 2 days) for a REQTIME of 60s
    MAWINDOW: int = Field(default=24 * 60 * 2)

    @field_validator("LOGLEVEL")
    def check_loglevel(cls, v):
        levels = list(logging.getLevelNamesMapping().keys())
        if v in levels:
            return v
        else:
            logging.error(
                f"Logging level \"{v}\" is not supported. Must be one of {levels}. defaulting to 'INFO'"
            )
            return "INFO"

    @field_validator("REQTIME")
    def check_reqtime(cls, v):
        if v < 30:
            logging.warning(
                "REQTIME is < 30 seconds. This is a waste of server resources; kudos will not be updated this fast. Interval will be clamped to a minimum of 30 seconds."
            )
            return 30
        return v

    @field_validator("NUMBACKUPS")
    def check_backups_num(cls, v):
        if v < 0:
            logging.warning("NUMBACKUPS is less than zero. Defaulting to 10.")
            return 10
        return v

    @field_validator("API_KEY")
    def check_apikey(cls, v):
        if v is None:
            raise ValueError("User must supply their API key in .env. e.g. API_KEY=foo")
        if v.lower() == "foo":
            raise ValueError(
                "User must set their API key. `foo` is not a valid API_KEY."
            )
        return v


try:
    config = Config()
except Exception as e:
    err_logger = logging.getLogger(__name__)
    coloredlogs.install(level="INFO", logger=err_logger)
    err_logger.error(e)
    # It's okay to just exit at this point instead of doexit. The lockfile has neither been checked or deleted. We should probably preserve it rather than trying too hard to check it.
    exit()
# Setup logging
logger = logging.getLogger(__name__)
coloredlogs.install(level=config.LOGLEVEL, logger=logger)

# Define constant paths. *Maybe* it would be good to allow these to be configurable, but I don't see any real reason to. If someone was that fervent on their desire to move the output location, they could do a find and replace.

LOCKFILE = Path.cwd() / ".kudolock"
BACKUP_DIR = Path.cwd() / "bak.d"
OUTPUT_FILE = Path.cwd() / "out.csv"
ENV_FILE = Path.cwd() / ".env"
OUT_IMAGE_FILE = Path.cwd() / "out.png"


def doexit(code=1):
    """Remove the lockfile and exit the program."""
    LOCKFILE.unlink(missing_ok=True)
    exit(code)


def is_lockfile_stale():
    """Check if the system probably didn't delete the lockfile."""
    with open(LOCKFILE, "r") as f:
        llock = f.read().split(",")
        lstart = float(llock[1])
        lpid = int(llock[0])

    # If we've rebooted since the lockfile was created, it's probably a stale lockfile.
    rebooted = psutil.boot_time() < (time.time() - lstart)
    if rebooted:
        return True
    try:
        lproc = psutil.Process(lpid)
        if lproc.is_running():
            # if it's running in a different directory than the current one, it's probably not this program. This isn't perfect, but it might help.
            return not (Path.cwd()).resolve().samefile(lproc.cwd())
    except psutil.NoSuchProcess:
        return True
    return False


def setup_lockfile():
    """Setup the lockfile and handle stale lockfiles."""
    if LOCKFILE.exists():
        if is_lockfile_stale():
            LOCKFILE.unlink()
        else:
            logger.error(
                f"Another instance of KudoMan is probably running! Please stop the other instance to start a new one. If you are sure there is not, you may remove {LOCKFILE}"
            )
            with open(LOCKFILE, "rt") as f:
                values = f.read().split(",")
            logger.info(
                f"KudoMan is running on PID {values[0]}, started at {datetime.datetime.fromtimestamp(float(values[1])).isoformat()}"
            )
            doexit()
    pid = os.getpid()
    start_time = time.time()
    with open(LOCKFILE, "wt") as f:
        f.write(f"{pid},{start_time}")


def setup_backup_dir():
    """Setup the backup directory."""
    if not BACKUP_DIR.exists():
        logger.info("No backup folder, creating bak.d")
        BACKUP_DIR.mkdir()
    backups = sorted(
        BACKUP_DIR.iterdir(), key=lambda x: x.stat().st_ctime, reverse=True
    )

    # Keep only the most recent backups
    if len(backups) > config.NUMBACKUPS:
        for old_backup in backups[config.NUMBACKUPS :]:
            logger.info(f"Removing old backup: {old_backup}")
            old_backup.unlink()


def create_output_file():
    """Create the output CSV file if it doesn't exist."""
    if not OUTPUT_FILE.exists():
        logger.info("No output file, creating out.csv")
        with open(OUTPUT_FILE, "wt") as f:
            f.write("Time,Kudos\n")


def backup_output_file():
    """Backup the current output CSV file."""
    backup_file = BACKUP_DIR / f"out-{int(time.time())}.csv.gz"
    with gzip.GzipFile(backup_file, "wb") as o, OUTPUT_FILE.open("rt") as i:
        o.write(i.read().encode("utf-8"))


def check_user(api_key):
    response = requests.get(
        "https://aihorde.net/api/v2/find_user", headers={"apikey": api_key}
    )
    if response.status_code == 404:
        logger.error(
            "User not found. Are you sure you entered the correct `API_KEY` into `.env`?"
        )
        doexit()

    response.raise_for_status()
    return True


def fetch_kudos(api_key):
    """Fetch kudos from the API."""
    response = requests.get(
        "https://aihorde.net/api/v2/find_user", headers={"apikey": api_key}
    )
    response.raise_for_status()  # Ensure we handle HTTP errors
    return response.json()["kudos"]


def log_kudos(kudos):
    """Log kudos to the CSV file."""
    with OUTPUT_FILE.open("at") as f:
        timestamp = time.time()
        f.write(f"{timestamp:.2f},{int(kudos)}\n")
        logger.info(f"{int(kudos)} Kudos")


def read_output_file_in_chunks(chunk_size=10000):
    """Read the output file in chunks to handle large datasets efficiently."""
    return pd.read_csv(OUTPUT_FILE, chunksize=chunk_size, skipinitialspace=True)


def update_secondary_stats():
    """Update secondary stats efficiently by processing data in chunks."""
    df_chunks = read_output_file_in_chunks()
    results = []
    for chunk in df_chunks:
        chunk["MA"] = (
            chunk["Kudos"].rolling(window=config.MAWINDOW, min_periods=0).mean()
        )
        chunk["D1"] = chunk["Kudos"].diff()
        chunk["MAD1"] = chunk["D1"].rolling(window=15, min_periods=0).mean()
        results.append(chunk)
    final_df = pd.concat(results, ignore_index=True)
    final_df.to_csv(OUTPUT_FILE, index=False)


def plot_kudos():
    """Plot kudos over time."""
    # Load dataframe
    df = pd.read_csv(OUTPUT_FILE, skipinitialspace=True)
    # Get time and Kudos
    t = df["Time"]
    ku = df["Kudos"]
    ma = df["MA"]
    d1 = df["D1"]
    mad1 = df["MAD1"]
    # Calculate the time as being relative to the first measurement
    tn = t.to_numpy() - t.to_numpy()[0]
    # Make a figure
    fig, kax = plt.subplots()
    fig.set_size_inches((10, 10 * 9 / 16))
    kax: matplotlib.axes.Axes = kax
    # Plot the data
    handles = [kax.plot(tn, ku, "b", label="Kudos")[0]]
    if config.SHOWMA:
        handles.append(kax.plot(tn, ma, "r", label="Kudos (Moving Average)")[0])

    dkax = kax.twinx() if config.SHOWD1 or config.SHOWMAD1 else None
    if config.SHOWD1:
        handles.append(dkax.plot(tn, d1, "g--", label="Kudos 1st difference")[0])
    if config.SHOWMAD1:
        handles.append(
            dkax.plot(tn, mad1, "y--", label="Kudo 1st difference (M.A.)")[0]
        )

    kax.set(
        xlabel="Time (Unix seconds)",
        title=f"Kudos plot",
    )
    kax.tick_params(axis="y")
    kax.set_ylabel("Kudos")
    if dkax is not None:
        dkax.tick_params(axis="y")
        dkax.set_ylabel("\u0394Kudos/\u0394Time")

    kax.legend(handles=handles)
    fig.tight_layout()  # otherwise the right y-label is slightly clipped

    # Turn on grid
    kax.grid()
    # Save and close figure
    fig.savefig(OUT_IMAGE_FILE)
    plt.close(fig)


def enabled_disabled(s):
    return "Enabled" if s else "Disabled"


def main():
    """Main function to run the script."""
    setup_lockfile()
    check_user(config.API_KEY)

    TIME = config.REQTIME
    logger.info(f"Fetching every {TIME} seconds")
    logger.info(f"Keeping {config.NUMBACKUPS} backups")
    logger.info(f"Moving average window of {config.MAWINDOW} samples")
    setup_backup_dir()
    create_output_file()
    backup_output_file()
    logger.info("Moving average : " + enabled_disabled(config.SHOWMA))
    logger.info("First difference : " + enabled_disabled(config.SHOWD1))
    logger.info("M.a. F.d. : " + enabled_disabled(config.SHOWMAD1))

    while True:
        try:
            kudos = fetch_kudos(config.API_KEY)
            log_kudos(kudos)
            update_secondary_stats()
            plot_kudos()
        except KeyboardInterrupt:
            logger.info("Removing lockfile during processing, then exiting.")
            doexit()
        except requests.RequestException as e:
            logger.warning(f"Exception caught: {e}")
        except Exception as e:
            logger.error(f"Unexpected exception: {e}")
        try:
            time.sleep(TIME)
        except KeyboardInterrupt:
            logger.info("Removing lockfile during delay, then exiting")
            doexit()


if __name__ == "__main__":
    main()
