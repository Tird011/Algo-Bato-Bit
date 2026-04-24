import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "engine"))

from scenes.game import main

if __name__ == "__main__":
    main()