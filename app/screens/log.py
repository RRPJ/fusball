from datetime import datetime
from functools import partial
import random
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from string import capwords
import subprocess
from pprint import pprint
import sys


class ScreenLog(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_log.png"), layer=0)
        
        # interface buttons:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (24, 700), (140,48), "Back", self.backHandler ))
        with open('logfile.log', 'r') as log:
            lines = log.readlines()
        for i,line in enumerate(lines):
            all_sprites.add(LcarsText(colours.WHITE, (100+i*22, 300), line[:-1], 20/19))
        

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())

    def handleEvents(self, event, fpsClock):
        pprint(event)
