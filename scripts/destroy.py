#!/usr/bin/env python3
"""Detiene el entorno. Uso: python3 scripts/destroy.py [--volumes]"""
import subprocess, sys, os
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
subprocess.run(["docker", "compose", "down"] + (["-v"] if "--volumes" in sys.argv else []), check=True)
