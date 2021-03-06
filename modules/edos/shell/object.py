# Copyright 2022 iiPython

# Modules
import os
import sys
import copy
import shlex
import traceback
from iipython import color
from magic import from_file
from iipython.iikp import readchar, keys

from edos import fs, __version__
from edos.shell.path import PathHandler
from edos.shell.macros import MacroLoader

# Shell class
class Shell(object):
    def __init__(self, root: str, zombie: bool = False) -> None:
        self.root = root
        self.env, self.history = {"vs": __version__}, []

        # Load filesystem
        if not zombie:
            self.fs = fs.Filesystem(os.path.join(root, "disk.edos"))
            os.chdir(self.fs.disk_location)

        self.path = PathHandler()
        self.macros = MacroLoader().as_dict()

    def autocomplete(self, value: str) -> str:
        def check_path_for_match(path: str) -> str | None:
            for file in os.listdir(path):
                if file.lower().startswith(value.lower().split("/")[-1]):
                    if not value.startswith("/"):
                        return os.path.join(path, file).replace(os.getcwd(), "").lstrip("/")

                    fp = fs.clean(os.path.abspath(os.path.join(path, file)))
                    return fp if " " not in fp else f"\"{fp}\""

        value = value.strip("\"")
        if value.startswith("/"):
            path = fs.resolve("/".join(value.split("/")[:-1]) or "/")

        else:
            path = os.getcwd()
            if "/" in value:
                path = os.path.join(path, "/".join(value.split("/")[:-1]))

        if os.path.isdir(path):
            return check_path_for_match(path)

    def readline(self, prompt: str) -> str:
        command, last_size, history = "", 0, {"i": 0, "s": None}
        while True:
            prefix = f"{' ' * os.get_terminal_size()[0]}\r" if len(command) < last_size else ""
            print(f"\r{prefix}{prompt}{command}", end = "")
            last_size = len(command)

            # Handle keypress
            kp = readchar()
            if kp == "\t":
                try:
                    chunks = shlex.split(command, posix = False)

                except ValueError:
                    try:
                        chunks = shlex.split(command + "\"", posix = False)

                    except Exception:
                        chunks = None

                if chunks is not None:
                    chunks[-1] = self.autocomplete(chunks[-1])
                    if chunks[-1] is not None:
                        command = " ".join(chunks)

            elif isinstance(kp, str):
                if history["s"] is not None:
                    history["s"] = None
                    history["i"] = 0

                command += kp

            elif kp == keys.ENTER:
                if command.strip():
                    self.history.append(command)

                print()
                return command

            elif kp == keys.CTRL_C:
                raise KeyboardInterrupt

            elif kp == keys.BACKSPACE and command:
                command = command[:-1]

            elif kp == keys.UP:
                if history["s"] is None:
                    history["s"] = copy.copy(command)

                history["i"] += 1
                if history["i"] > len(self.history):
                    history["i"] -= 1

                if self.history:
                    command = self.history[-history["i"]]

            elif kp == keys.DOWN:
                history["i"] -= 1
                if history["i"] <= 0:
                    if history["s"] is not None:
                        command = copy.copy(history["s"])
                        history["s"] = None

                    history["i"] = 0

                else:
                    command = self.history[-history["i"]]

    def format_env(self, text: str) -> str:
        for k, v in self.env.items():
            text = text.replace(f"${k}", v)

        return text

    def fetch_prompt(self) -> str:
        return self.format_env(fs.open("/System/Settings/prompt", "r").read() if fs.isfile("/System/Settings/prompt") else r"%dir $")

    def execute(self, line: str) -> None:
        command = self.format_env(line).split(" ")
        raw, args = command[0], command[1:]

        # Find item on path
        if raw in self.macros:
            try:
                self.macros[raw](self, shlex.split(" ".join(args)))

            except Exception as e:
                if isinstance(e, ValueError) and "quotation" in str(e):
                    print(f"edos: {e}")

                else:
                    print(f"Python exception occured in macro '{raw}':")
                    print(traceback.format_exc())

            return

        cmd = self.path.resolve(raw)
        if cmd is None:
            return print(f"{raw}: command not found")

        # Check how we should run it
        built_command, file_guess = None, from_file(cmd).lower()
        if "python script" in file_guess:
            built_command = f"PYTHONPATH=\"{os.path.join(self.root, 'modules')}\" EDOS_ROOT=\"{self.root}\" {sys.executable} {cmd}"

        elif "elf 64-bit lsb executable" in file_guess:
            built_command = cmd

        # Launch file
        if file_guess is None:
            return print("File is not an eDOS-compatible executable.")

        os.system(f"{built_command} {' '.join(args)}")

    def handle_input(self) -> None:
        print(color(f"\n\t[yellow]Emulated Disk Operating System (eDOS) v{__version__}[/]\n\t    [lblack]Copyright (c) 2022-present iiPython[/]\n"))
        while True:
            self.env["dir"] = fs.getcwd()

            # Process command input
            command = self.readline(color(self.fetch_prompt()))
            if not command:
                continue

            self.execute(command)
