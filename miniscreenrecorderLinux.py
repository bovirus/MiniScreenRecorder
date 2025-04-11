import platform
import sys

if __name__ == "__main__":
    if platform.system() != 'Linux':
        print("This script is for Linux only. Please use miniscreenrecorder.py on Windows systems.")
        sys.exit(1)
    
    from app import main
    main()