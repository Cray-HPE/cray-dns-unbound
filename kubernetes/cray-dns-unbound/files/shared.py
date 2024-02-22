#!/usr/bin/env python3
# Copyright 2014-2022 Hewlett Packard Enterprise Development LP

import subprocess

def run_command(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output = p.stdout.decode('utf-8')
    err = p.stderr.decode('utf-8')
    print("Stdout:\n" + output)
    print("Stderr:\n" + err)
    if p.returncode != 0:
        raise SystemExit('Error running command')
    return output
