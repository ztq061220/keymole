import sys, time, subprocess
time.sleep(float(sys.argv[1]))
subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.cz_blink", sys.argv[2], sys.argv[3]])
