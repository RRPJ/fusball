onboard &

cd ~/rpi_lcars
python touchscreen.py &

cd ~/rpi_lcars/app
#python lcars.py

#|| xfce4-terminal
#exec i3
exec xfce4-terminal -e '/usr/bin/zsh -c "/usr/bin/python3 lcars.py; /usr/bin/zsh"'

