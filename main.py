import datetime
import requests
import time
import matplotlib.pyplot as plt
import pandas as pd
import os
from pathlib import Path
import dotenv
import logging
import psutil
import coloredlogs

# Setup logging
logger = logging.getLogger(__name__)
coloredlogs.install(level="DEBUG", logger=logger)

# Cross-platform path handling
LOCKFILE = Path.cwd() / ".kudolock"
BACKUP_DIR = Path.cwd() / "bak.d"
OUTPUT_FILE = Path.cwd() / "out.csv"
ENV_FILE = Path.cwd() / ".env"


def doexit(code=1):
    """Remove the lockfile and exit the program."""
    LOCKFILE.unlink(missing_ok=True)
    exit(code)


def probably_didnt_delete():
    """Check if the system probably didn't delete the lockfile."""
    with open(LOCKFILE, "r") as f:
        lstart = float(f.read().split(",")[1])
    # If we've rebooted since the lockfile was created, it's probably a stale lockfile.
    return psutil.boot_time() < (time.time() - lstart)


def setup_lockfile():
    """Setup the lockfile and handle stale lockfiles."""
    if LOCKFILE.exists():
        if probably_didnt_delete():
            LOCKFILE.unlink()
        else:
            logger.warning(
                f"Another instance of Kudoman is probably running! Please stop the other instance to start a new one. If you are sure there is not, you may remove {LOCKFILE}"
            )
            with open(LOCKFILE, "rt") as f:
                values = f.read().split(",")
            logger.info(
                f"KudoMan is running on PID {values[0]}, started at {datetime.datetime.fromtimestamp(float(values[1])).isoformat()}"
            )
            doexit(2)
    pid = os.getpid()
    start_time = time.time()
    with open(LOCKFILE, "wt") as f:
        f.write(f"{pid},{start_time}")


def load_api_key():
    """Load the API key from the environment file."""
    dotenv.load_dotenv()
    api_key = os.getenv("API_KEY")
    if not api_key:
        if not ENV_FILE.exists():
            with open(ENV_FILE, "wt") as f:
                f.write("API_KEY=foo")
        logger.error("User must supply their API key in .env. e.g. API_KEY=foo")
        doexit(3)
    if api_key.lower() == "foo":
        logger.error("Make sure to set your API key in .env.")
        doexit(3)
    return api_key


def setup_backup_dir():
    """Setup the backup directory."""
    if not BACKUP_DIR.exists():
        logger.info("No backup folder, creating bak.d")
        BACKUP_DIR.mkdir()
    backups = sorted(BACKUP_DIR.iterdir())
    if len(backups) > 10:
        for old_backup in backups[:-10]:
            logger.info(f"Removing old backup: {old_backup}")
            old_backup.unlink()


def create_output_file():
    """Create the output CSV file if it doesn't exist."""
    if not OUTPUT_FILE.exists():
        logger.info("No output file, creating out.csv")
        with open(OUTPUT_FILE, "wt") as f:
            f.write("Time,Kudos")


def backup_output_file():
    """Backup the current output CSV file."""
    backup_file = BACKUP_DIR / f"out-{int(time.time())}.csv"
    with backup_file.open("wt") as o, OUTPUT_FILE.open("rt") as i:
        o.write(i.read())


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


def plot_kudos():
    """Plot kudos over time."""
    df = pd.read_csv(OUTPUT_FILE, skipinitialspace=True)
    t = df["Time"]
    ku = df["Kudos"]
    tn = t.to_numpy() - t.to_numpy()[0]
    fig, ax = plt.subplots()
    ax.plot(tn, ku)
    ax.set(
        xlabel="Time (Unix seconds)",
        ylabel="Kudos",
        title=f"Kudos plot ({int(ku.iloc[-1])}@{int(time.time())})",
    )
    ax.grid()
    fig.savefig("out.png")
    plt.close(fig)


def main():
    """Main function to run the script."""
    setup_lockfile()
    api_key = load_api_key()
    setup_backup_dir()
    create_output_file()
    backup_output_file()

    while True:
        try:
            kudos = fetch_kudos(api_key)
            log_kudos(kudos)
            plot_kudos()
        except KeyboardInterrupt:
            logger.info("Removing lockfile during processing, then exiting.")
            doexit(1)
        except requests.RequestException as e:
            logger.warning(f"Exception caught: {e}")
        except Exception as e:
            logger.warning(f"Unexpected exception: {e}")
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Removing lockfile during delay, then exiting")
            doexit(1)


if __name__ == "__main__":
    main()
