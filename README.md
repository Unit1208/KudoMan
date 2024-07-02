# KudoMan
[GPL-3.0-or-later](LICENSE)  
KudoMan is a script designed to periodically fetch, log, and visualize Kudos from the Stable Horde API.


> [!WARNING]
> This script has only been tested on Linux. It has been written to be cross-platform, but no idea if it works on Windows or MacOS. 

## Features

- Fetches Kudos from the API every 60 seconds.
- Logs Kudos data to a CSV file.
- Creates visual plots of Kudos over time.
- Manages lockfiles to prevent concurrent runs.
- Backs up old CSV files.
- Handles environment variables for configuration.

## Requirements

- Python 3.x
- package requirements in `requirements.txt`

## Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/Unit1208/KudoMan.git
    cd KudoMan
    ```

2. **Install the required Python packages:**

    ```bash
    python -m venv venv
    source venv/bin/activate 
    pip install -r requirements.txt
    ```

3. **Set up the environment file:**

    Create a `.env` file in the root directory and add your API key:

    ```plaintext
    API_KEY=your_api_key_here
    ```

## Usage

To run the script, simply run:

```bash
python kudoman.py
```

