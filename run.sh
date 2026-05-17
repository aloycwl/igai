pkill -f "python3 -u -m igai.cli"
nohup python3 -u -m igai.cli > embedding.log 2>&1 &
