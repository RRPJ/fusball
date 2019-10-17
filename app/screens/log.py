from datetime import datetime
from functools import partial
import random
import math
from ui.widgets.background import LcarsBackgroundImage, LcarsImage
from ui.widgets.gifimage import LcarsGifImage
from ui.widgets.lcars_widgets import *
from ui.widgets.screen import LcarsScreen
from string import capwords
import subprocess
from pprint import pprint
import sys
import time

LINES = 25

def pos(x,y):
    return (768-y-32+4, x+4)



class ScreenLog(LcarsScreen):
    def setup(self, all_sprites):
        # background image
        all_sprites.add(LcarsBackgroundImage("assets/bg_log.png"), layer=0)

        self.textlines = []
        self.page = 0
        for i in range(LINES):
            newline = LcarsText(colours.WHITE, pos(150, 550-20*i), '', 20/19)
            self.textlines.append(newline)
            all_sprites.add(newline)
        

        # interface buttons:
        all_sprites.add(LcarsButton2(colours.RED_BROWN, (360, 700), (140,48), "Back", self.backHandler ))
        all_sprites.add(LcarsButton2(colours.GREY_BLUE, ( 48, 620), (140,48), "Prev", self.prevHandler ))
        all_sprites.add(LcarsButton2(colours.GREY_BLUE, (192, 620), (140,48), "Next", self.nextHandler ))

        self.pageLabel = LcarsText(colours.WHITE, pos(346, 620), '', 20/19)
        all_sprites.add(self.pageLabel)
        
        self.page = 0
        self.showPage()

    def nextHandler(self, item, event, clock):
        self.page = min(self.maxpage-1, self.page+1)
        self.showPage()


    def prevHandler(self, item, event, clock):
        self.page = max(0,self.page-1)
        self.showPage()
        
    def showPage(self):
        with open('logfile.log', 'r') as log:
            lines = log.readlines()
        for i in range(LINES):
            self.textlines[i].setText('')
        for i,line in enumerate(lines[self.page*LINES:(self.page+1)*LINES]):
            self.textlines[i].setText(line[:-1]) # cut \n
        self.maxpage = math.ceil(len(lines)/LINES)
        self.pageLabel.setText('Page {} of {}'.format(self.page+1, self.maxpage))
            
        
        

        

    def backHandler(self, item, event, clock):
        from screens.main import ScreenMain
        self.loadScreen(ScreenMain())

            
