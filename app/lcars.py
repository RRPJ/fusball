from screens.authorize import ScreenAuthorize
from screens.main import ScreenMain
from ui.ui import UserInterface
import config
from startup import run_diagnostics

def main():
    # Run startup diagnostics
    if not run_diagnostics():
        print("Startup diagnostics failed. Aborting.", file=__import__('sys').stderr)
        return
    
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
