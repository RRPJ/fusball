
cd ~/rpi_lcars/
exec python ~/touchscreen.py &

cd ~/rpi_lcars/app
exec python lcars.py || xfce4-terminal
#exec i3
#exec xfce4-terminal

