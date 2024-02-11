from screens.authorize import ScreenAuthorize
from screens.main import ScreenMain
from ui.ui import UserInterface
import config

def main():
    # Initialize the first screen
    first_screen = ScreenMain()

    # Initialize the User Interface
    ui = UserInterface(
        first_screen,
        config.RESOLUTION,
        config.UI_PLACEMENT_MODE,
        config.FPS,
        config.DEV_MODE,
        config.SOUND
    )

    # Start the main loop
    while True:
        ui.tick()

if __name__ == "__main__":
    main()
