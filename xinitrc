#onboard &

cd ~/rpi_lcars
python touchscreen.py &

cd ~/rpi_lcars/app
exec xfce4-terminal -e '/usr/bin/zsh -c "/usr/bin/python3 lcars.py; /usr/bin/zsh"'

