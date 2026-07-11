import subprocess
import os
import sys
import time
import webbrowser

def main():
    print("Launching Triage Assist AI processes...")
    bat_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'run_all.bat')
    
    if not os.path.exists(bat_path):
        print(f"Error: {bat_path} not found.")
        sys.exit(1)
        
    subprocess.Popen([bat_path], shell=True)
    print("Backend and Frontend have been launched in separate windows.")
    
    print("Waiting a few seconds for the servers to boot up before opening the browser...")
    time.sleep(5)
    
    webbrowser.open("http://localhost:8501")
    
    print("You can now safely close this terminal.")

if __name__ == "__main__":
    main()
