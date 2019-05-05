import pygame
from pygame.font import Font
from pygame.locals import *

from ui.utils.sound import Sound
from ui.widgets.sprite import LcarsWidget
from ui import colours

class LcarsElbow(LcarsWidget):
    """The LCARS corner elbow - not currently used"""
    
    STYLE_BOTTOM_LEFT = 0
    STYLE_TOP_LEFT = 1
    STYLE_BOTTOM_RIGHT = 2
    STYLE_TOP_RIGHT = 3
    
    def __init__(self, colour, style, pos, handler=None):
        image = pygame.image.load("assets/elbow.png").convert_alpha()
        # alpha=255
        # image.fill((255, 255, 255, alpha), None, pygame.BLEND_RGBA_MULT)
        if (style == LcarsElbow.STYLE_BOTTOM_LEFT):
            image = pygame.transform.flip(image, False, True)
        elif (style == LcarsElbow.STYLE_BOTTOM_RIGHT):
            image = pygame.transform.rotate(image, 180)
        elif (style == LcarsElbow.STYLE_TOP_RIGHT):
            image = pygame.transform.flip(image, True, False)
        
        self.image = image
        size = (image.get_rect().width, image.get_rect().height)
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.applyColour(colour)

class LcarsTab(LcarsWidget):
    """Tab widget (like radio button) - not currently used nor implemented"""

    STYLE_LEFT = 1
    STYLE_RIGHT = 2
    
    def __init__(self, colour, style, pos, handler=None):
        image = pygame.image.load("assets/tab.png").convert()
        if (style == LcarsTab.STYLE_RIGHT):
            image = pygame.transform.flip(image, False, True)
        
        size = (image.get_rect().width, image.get_rect().height)
        LcarsWidget.__init__(self, colour, pos, size, handler)
        self.image = image
        self.applyColour(colour)


#class LcarsRectButton(LcarsWidget):
#    """ Rectangle, square corners, customizable size button """
#    def __init__(self, colour, pos, text, handler=None, 


#W = 36
#H = 32
W = 48
H = 40
buttonmap = [
    ['1','2','3','4','5','6','7','8','9','0'],
    ['q','w','e','r','t','y','u','i','o','p'],
    ['a','s','d','f','g','h','j','k','l', ''],
    ['z','x','c','v','b','n','m', '', '', '']]
        
class LcarsKeyboard(LcarsWidget):
    def __init__(self, pos, handler=None):
        self.pos = pos
        self.buttondown = ''
        #self.offsets = [40, 56, 64, 76]
        self.offsets = [50, 74, 82, 94]
        self.repaint()
        LcarsWidget.__init__(self, (0,0,0), pos, (600,200), handler)


    def repaint(self):
        image = pygame.Surface((600,200)).convert_alpha()
        # top row
        for i in range(10):
            image.fill(colours.BEIGE, (self.offsets[0]+(W+4)*i, 0*(H+4), W, H))
        for i in range(10):
            image.fill(colours.BEIGE, (self.offsets[1]+(W+4)*i, 1*(H+4), W, H))
        for i in range(9):
            image.fill(colours.BEIGE, (self.offsets[2]+(W+4)*i, 2*(H+4), W, H))
        for i in range(7):
            image.fill(colours.BEIGE, (self.offsets[3]+(W+4)*i, 3*(H+4), W, H))

        # draw the highlight
        if self.buttondown != '':
            hoffset = self.offsets[self.row]
            image.fill(colours.WHITE, (hoffset+(W+4)*self.col, self.row*(H+4), W, H))
            # for debugging:
            #image.fill((255,0,0), (self.relpos[0], 0, 1, 1000))
            #image.fill((255,0,0), (0, self.relpos[1], 1000, 1))
            

        # decorations:
        halfH = int(H/2)
        pygame.draw.circle(image, colours.ORANGE, (halfH, 0*(H+4)+halfH), halfH)
        pygame.draw.circle(image, colours.ORANGE, (halfH, 1*(H+4)+halfH), halfH)
        pygame.draw.circle(image, colours.ORANGE, (halfH, 2*(H+4)+halfH), halfH)
        pygame.draw.circle(image, colours.ORANGE, (halfH, 3*(H+4)+halfH), halfH)
        image.fill(colours.ORANGE, (halfH, 0*(H+4), self.offsets[0]-halfH-4, H))
        image.fill(colours.ORANGE, (halfH, 1*(H+4), self.offsets[1]-halfH-4, H))
        image.fill(colours.ORANGE, (halfH, 2*(H+4), self.offsets[2]-halfH-4, H))
        image.fill(colours.ORANGE, (halfH, 3*(H+4), self.offsets[3]-halfH-4, H))

        # draw glyphs:
        font = Font("assets/swiss911.ttf", 20)
        for row in range(4):
            for col in range(10):
                textImage = font.render(buttonmap[row][col].upper(), True, (0,0,0))
                image.blit(textImage,
                           (self.offsets[row] + (W+4)*col + 4, (H+4)*row)
                )

        # remember for later
        self.image = image

    def handleEvent(self, event, clock):
        if (event.type == MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos)):
            relx = event.pos[0] - self.pos[1]
            rely = event.pos[1] - self.pos[0]
            # subtract row offsets
            self.buttondown = ''
            
            self.row = int(rely / (H+4))
            self.col = int((relx-self.offsets[self.row]) / (W+4))
            # test for vertical border hit:
            if rely % (H+4) >= H:
                return
            # test for horizontal border hit:
            if (relx-self.offsets[self.row]) % (W+4) >= W:
                return
            # test for hit before first column:
            if relx-self.offsets[self.row] < 0:
                return

            
            if self.col < 10:
                self.buttondown = buttonmap[self.row][self.col]

            self.relpos = (relx, rely)
            self.repaint()
            
            if self.buttondown != '':
                self.handler(self, self.buttondown, clock)
                
                
            
                
            
            #self.beep.play()

        if (event.type == MOUSEBUTTONUP):
            self.buttondown = ''
            self.repaint()
           
        


class LcarsButton(LcarsWidget):
    def __init__(self, colour, pos, size, text, handler=None, glyph=False, glyphoffset=(0,0)):
        self.image = pygame.Surface(size)
        self.colour = colour
        self.text = text
        self.glyph = glyph
        self.glyphoffset = glyphoffset

        self.applyColour(colour)
        LcarsWidget.__init__(self, colour, pos, size, handler)
        
        self.highlighted = False
        self.beep = Sound("assets/audio/panel/202.wav")

    def applyColour(self, colour):
        # just re-render
        self.image.fill(colour)
        if self.glyph:
            glyphimage = pygame.image.load("assets/"+self.text+".png")
            x = int(self.image.get_rect().width/2 - glyphimage.get_rect().width/2 + self.glyphoffset[0])
            y = int(self.image.get_rect().height/2- glyphimage.get_rect().height/2 + self.glyphoffset[1])
            #print("button size: {}\nglyph size: {}\noffset: {}\nblit at: {}".format(self.image.get_rect(), glyphimage.get_rect(), self.glyphoffset, (x,y)))
            self.image.blit(glyphimage, (x, y))

        else:
            font = Font("assets/swiss911.ttf", 20)
            textImage = font.render(self.text, True, (0,0,0))
            self.image.blit(textImage, 
                            (self.image.get_rect().width  - textImage.get_rect().width  - 10,
                             self.image.get_rect().height - textImage.get_rect().height - 5))

    def handleEvent(self, event, clock):
        if (event.type == MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos) and self.visible == True):
            self.applyColour(colours.WHITE)
            self.highlighted = True
            self.beep.play()

        if (event.type == MOUSEBUTTONUP and self.highlighted and self.visible == True):
            self.applyColour(self.colour)
           
        return LcarsWidget.handleEvent(self, event, clock)



class LcarsButton2(LcarsButton):
    """wrapper that align to lower left and has y coordinate flipped"""
    def __init__(self, colour, pos, size, text, handler=None, glyph=False, glyphoffset=(0,0)):
        x = pos[0]
        y = pos[1] + size[1]
        #x = x - size[0]/2
        #y = y - size[1]/2
        y = 768 - y
        LcarsButton.__init__(self, colour, (y, x), size, text, handler, glyph, glyphoffset)


        
class LcarsText(LcarsWidget):
    """Text that can be placed anywhere"""

    def __init__(self, colour, pos, message, size=1.0, background=None, handler=None, otherfont=False):
        self.colour = colour
        self.background = background
        if otherfont:
            self.font = Font("assets/swiss2.ttf", int(19.0 * size))
        else:
            self.font = Font("assets/swiss911.ttf", int(19.0 * size))
        
        self.renderText(message)
        # center the text if needed 
        if (pos[1] < 0):
            pos = (pos[0], 400 - self.image.get_rect().width / 2)
            
        LcarsWidget.__init__(self, colour, pos, None, handler)

    def renderText(self, message):        
        if (self.background == None):
            self.image = self.font.render(message, True, self.colour)
        else:
            self.image = self.font.render(message, True, self.colour, self.background)
        
    def setText(self, newText):
        self.renderText(newText)

class LcarsBlockLarge(LcarsButton):
    """Left navigation block - large version"""

    def __init__(self, colour, pos, text, handler=None):
        size = (98, 147)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

class LcarsBlockMedium(LcarsButton):
   """Left navigation block - medium version"""

   def __init__(self, colour, pos, text, handler=None):
        size = (98, 62)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

class LcarsBlockSmall(LcarsButton):
   """Left navigation block - small version"""

   def __init__(self, colour, pos, text, handler=None):
        size = (98, 34)
        LcarsButton.__init__(self, colour, pos, text, handler, size)

    
