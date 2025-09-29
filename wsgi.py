#!/usr/bin/env python3
import os
import sys
from app import app
sys.path.insert(0, os.path.dirname(__file__))
if __name__ == "__main__":
    app.run()