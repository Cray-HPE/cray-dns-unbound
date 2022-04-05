#!/usr/bin/env python3
# Copyright 2014-2022 Hewlett Packard Enterprise Development LP

import subprocess

def run_command(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = p.stdout.decode('utf-8')
    print(output)
    if p.returncode != 0:
        raise SystemExit('Error running command')
    return output
