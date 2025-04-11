import platform
import sys

if __name__ == "__main__":
    if platform.system() != 'Windows':
        print("This script is for Windows only. Please use miniscreenrecorderLinux.py on Linux systems.")
        sys.exit(1)
    
    from app import main
    main()