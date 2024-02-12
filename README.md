# LCARS Kickers Interface

Welcome to the LCARS Kickers Interface! This Python repository provides a user-friendly application for registering foosball scores and maintaining a leaderboard. Leveraging Microsoft's TrueSkill algorithm, it tracks players' skills in both offense and defense, offering a comprehensive gaming experience.

## Getting Started

First install the required packages:
```Python
pip install -r requirements.txt
```

To launch the application, first navigate to the app directory
```Python
cd app
```

Then run the following command:
```Python
Python app/lcars.py
```

## Development Mode (Mouse Cursor)

Development Mode is now active by default. It enables a mouse cursor. This game was originally programmed for a machine with a touch-screen, which did not necessitate a cursor.
If you ever want to turn it off, set `DEV_MODE` to `False` in the `config.py` file. 

Enjoy the game and have fun competing with your friends!