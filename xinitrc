
# onscreen keyboard:
#onboard &

# touchscreen 'driver':
cd ~/rpi_lcars
python touchscreen.py &

cd ~/rpi_lcars/app
while true; do
      /usr/bin/python lcars.py &>>! /home/kickers/kickers.log
done
      
#exec xfce4-terminal

# old method: start in terminal for recovery
#exec xfce4-terminal -e '/usr/bin/zsh -c "/usr/bin/python3 lcars.py; /usr/bin/zsh"'

