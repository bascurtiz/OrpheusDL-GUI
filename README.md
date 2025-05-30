# OrpheusDL GUI

## Trailer
[![Watch trailer](https://i.imgur.com/CxG3Bkw.png)](https://youtu.be/RAXsW67SjGU)

## How to install:

1. Make sure you have OrpheusDL installed already, see YouTube video:
https://youtu.be/AGsYTQuO7nk


### Windows/macOS:
2. Download the compiled exe/app from the [Releases page](https://github.com/bascurtiz/OrpheusDL-GUI/releases).
3. Unzip the downloaded file and place it in the same folder where your `orpheus.py` is located.
4. Double-click `OrpheusDL_GUI` (or make a shortcut to desktop)

### Linux (or if you prefer running from source):
1. Clone this repository (`git clone https://github.com/bascurtiz/OrpheusDL-GUI.git`) or download the ZIP file.
2. Ensure all files from this repository are placed in the same folder where your `orpheus.py` is located.
3. Update your package list: `sudo apt update`
4. Install the Python virtual environment package: `sudo apt install python3-venv`
5. Create a virtual environment: `python3 -m venv venv`
6. Activate the virtual environment: `source venv/bin/activate`
7. Install the required dependencies: `pip3 install -r requirements-gui.txt`
8. Run the GUI: `python3 gui.py`

## Compatibility

### Operating Systems

| OS            | Tested |
|---------------|--------|
| Windows 10    | ✅     |
| Windows 11    | ✅     |
| macOS 13.6+   | ✅     |
| Linux Ubuntu 24 | ✅     |

### Platforms

| Platform     | Tested | Platform     | Tested | Platform     | Tested |
|--------------|--------| --------------|--------|--------------|--------|
| Apple Music  | \*     | Beatport     | ✅     | Beatsource   | ✅     |
| Bugs         | \*     | Deezer       | ✅     | Genius       | \*     |
| Idagio       | \*     | JioSaavn     | ✅     | KKBOX        | \*     |
| Musixmatch   | \*     | Napster      | \*     | Nugs.net     | \*     |
| Qobuz        | ✅     | SoundCloud   | ✅     | Spotify      | ✅     |
| Tidal        | ✅     |              |        |              |        |

\* *If this platform isn't working properly and you have a valid subscription you can share, please open an issue or contact me. I'm willing to debug!* 
