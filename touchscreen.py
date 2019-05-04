import serial
from pymouse import PyMouse

ser = serial.Serial('/dev/ttyS2', 9600)
m = PyMouse()
mousedown = False


while True:
    # determine event type
    b = ser.read()
    # packets start with 0x93 (touch down) or 0x83 (touch up)
    if b != b'\x93' and b != b'\x83':
        # try to get aligned again
        print("skipping until next packet")
        print(b)
        while ser.read() != b'\x93':
            pass
        # consume the remaining 4
        ser.read(4)
        continue
    # process next 4 bytes as 1 frame:
    x1 = ord(ser.read())
    x2 = ord(ser.read())
    y1 = ord(ser.read())
    y2 = ord(ser.read())
    #print("x1: {}\tx2: {}\ty1: {}\ty2: {}\t{}".format(x1, x2, y1, y2, "down" if b==b'\x93' else "up"))
    x = (x1<<4)+(x2>>3)
    y = (y1<<4)+(y2>>3)
    #print("x: {}\ty: {}".format(x, y))
    # scale to screen dimensions
    x = int(1024.0/2000.0 * x)
    y = int(768.0/2000.0 * y)
    # experimental offset
    x = x - 10
    y = y - 10

    if (not mousedown) and (b==b'\x93'):
        # process key down
        m.press(x, 768-y)
    elif mousedown and b==b'\x83':
        # process key up
        m.release(x,768-y)
    else:
        # process normal move
        m.move(x, 768-y)

    mousedown = b==b'\x93'
    
    
